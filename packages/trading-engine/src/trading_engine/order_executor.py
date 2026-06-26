"""Order lifecycle: place, pending, fills, retries."""

from __future__ import annotations

import datetime
import threading

from trading_engine.core.audit.exec_audit import ExecAudit, format_exec_audit
from trading_engine.core.audit.signal_audit import format_signal_audit
from trading_engine.core.order_events import is_futures_deal, is_futures_order
from trading_engine.core.trading_state import PendingIntent
from trading_engine.core.types import OrderSignal, QueryStatusTask
from trading_engine.logging_setup import get_logger
from trading_engine.order_errors import OrderErrorCategory, classify_order_error, should_retry_order

logger = get_logger()

# P0-5: exit reasons that are hard/loss stops and therefore MUST get out (escalate
# a missed IOC to a market order). Profit-taking / trailing exits are not urgent
# and keep their limit-IOC retry semantics.
_STOP_LOSS_REASONS = frozenset({"stop_loss", "stop_loss_vwap"})


class OrderExecutorMixin:
    def _validate_order_signal(self, signal: OrderSignal) -> bool:
        """Reject invalid strategy/kernel signals before arming pending."""
        if signal.qty <= 0:
            logger.warning("拒絕 OrderSignal: qty=%s 必須 > 0", signal.qty)
            return False
        if signal.intent not in ("entry", "exit"):
            logger.warning("拒絕 OrderSignal: 非法 intent=%r", signal.intent)
            return False
        if signal.action not in ("Buy", "Sell"):
            logger.warning("拒絕 OrderSignal: 非法 action=%r", signal.action)
            return False
        if self.is_pending:
            logger.warning(
                "拒絕 OrderSignal: 已有 pending (intent=%s)",
                self.pending_intent,
            )
            return False
        # P0-5: while the previous order's outcome is UNKNOWN (settling) or the
        # broker position is unconfirmed (HALT), freeze BOTH entry and exit.
        # The strategy must never re-issue here; the kernel owns convergence via
        # _settle_via_reconcile + _maybe_converge_flatten. ``_kernel_converging``
        # lets kernel-owned convergence flatten bypass this freeze.
        if (self._settling or self._position_unconfirmed) and not getattr(
            self, "_kernel_converging", False
        ):
            logger.warning(
                "拒絕 OrderSignal: 部位未確認/結算中 (settling=%s unconfirmed=%s intent=%s)",
                self._settling,
                self._position_unconfirmed,
                signal.intent,
            )
            return False
        if signal.intent == "entry":
            if self.block_new_entry:
                logger.warning("拒絕 entry OrderSignal: block_new_entry=True")
                return False
            if self.position_qty > 0:
                logger.warning(
                    "拒絕 entry OrderSignal: 已有持倉 qty=%s",
                    self.position_qty,
                )
                return False
            # P0-4: hard position ceiling. ``is_pending`` is already rejected
            # above, so pending_qty is 0 here; guard held + requested qty.
            ceiling = self._cfg.max_position_qty
            if ceiling > 0 and self.position_qty + signal.qty > ceiling:
                logger.warning(
                    "拒絕 entry OrderSignal: 超過部位上限 | 持倉=%d + 委託=%d > max=%d",
                    self.position_qty,
                    signal.qty,
                    ceiling,
                )
                return False
        if signal.intent == "exit" and self.position_qty <= 0:
            logger.warning("拒絕 exit OrderSignal: 無持倉")
            return False
        return True

    def _arm_pending(self, signal: OrderSignal) -> None:
        """P2-2: lock 內同步設 pending，堵住雙 tick 雙單。"""
        self.is_pending = True
        # Bump generation so any in-flight Layer-2 query for a prior pending is stale.
        self._pending_generation += 1
        self.pending_intent = signal.intent
        self.pending_exchange_ts = signal.exchange_ts
        self.pending_qty = signal.qty
        self.pending_signal_price = signal.ref_price
        self.pending_market = bool(getattr(signal, "market", False))
        self.pending_ioc_slippage = (
            signal.slippage_points
            if signal.slippage_points is not None
            else self._cfg.ioc_slippage_points
        )
        self._pending_action = signal.action
        is_buy = signal.action == "Buy"
        if self.pending_market:
            # Market order: no limit gate. Track 0 for audit; fill is whatever the
            # venue gives (guaranteed fill is the point).
            self.pending_ioc_slippage = 0
            self.pending_limit_price = 0.0
        else:
            self.pending_limit_price = self._telemetry.compute_limit_price(
                signal.ref_price,
                is_buy=is_buy,
                ioc_slippage=self.pending_ioc_slippage,
            )
        self.pending_exit_reason = (
            signal.audit.reason
            if signal.audit is not None and signal.intent == PendingIntent.EXIT
            else ""
        )
        self.pending_episode_id = ""
        self.pending_signal_id = ""
        if signal.signal_id:
            self.pending_signal_id = signal.signal_id
        if signal.audit is not None:
            self.pending_episode_id = getattr(signal.audit, "episode_id", "") or ""
            if not self.pending_signal_id:
                self.pending_signal_id = getattr(signal.audit, "signal_id", "") or ""
        if signal.intent == PendingIntent.EXIT:
            self.exit_pending = True

        # Set pending_since early (at arm time) to avoid premature timeout window
        # when place_order takes time or order_id population is delayed.
        # Always use internal _clock() (wall time) for consistent comparison in _check_pending_timeout.
        self.pending_since = self._clock()

        # Note: pending_armed EXEC is emitted from place_order after order_id is known (to satisfy SPEC order_id MUST).
        # See place_order below.

        # Defensive guard (logs only). Permanent invariant check.
        try:
            from trading_engine.core.trading_state import validate_pending_consistency

            validate_pending_consistency(
                is_pending=self.is_pending,
                pending_intent=self.pending_intent,
                exit_pending=self.exit_pending,
                position_qty=self.position_qty,
                position_dir=self.position_dir,
                logger=logger,
            )
        except Exception:
            pass  # never let guard break hot path

    @staticmethod
    def _log_signal_audit(signal: OrderSignal) -> None:
        if signal.audit is None:
            return
        logger.info("SIGNAL_AUDIT %s", format_signal_audit(signal.audit))

    def _update_trailing_peak(self, price: float):
        """持倉後 trailing stop 用 peak，僅在 manage_exit 邏輯內使用。"""
        if self.position_dir == "Long":
            self.trailing_peak = max(self.trailing_peak, price)
        elif self.position_dir == "Short":
            self.trailing_peak = min(self.trailing_peak, price)

    def is_trading_session(self, dt: datetime.datetime) -> bool:
        return self._calendar.is_trading_session(dt, self._cfg.session_start, self._cfg.session_end)

    def _maybe_reset_daily_state(self, dt: datetime.datetime) -> None:
        """P0-8: 交易日變更時重置日內風控（日盤 = 日曆日，見 exchange_time）。"""
        trade_date = self._calendar.trading_day_for_daily_reset(dt)
        if self._trading_date is None:
            self._trading_date = trade_date
            return
        if trade_date == self._trading_date:
            return
        logger.info(
            "交易日切換 %s → %s，重置日內風控",
            self._trading_date,
            trade_date,
        )
        self._emit_daily_summary(self._trading_date)
        self._reset_daily_state()
        self._telemetry.reset()
        self._tick_type_counts = {0: 0, 1: 0, 2: 0}
        self._tick_type_inferred_counts = {1: 0, 2: 0}
        self._trading_date = trade_date

    def _reset_daily_state(self) -> None:
        self.daily_pnl = 0.0
        self.block_new_entry = False
        self.consecutive_loss = 0
        self._disconnect_count_today = 0
        # P0-5: lift HALT on trading-day rollover (operator-equivalent reset).
        self._position_unconfirmed = False
        self._converge_flatten_at = 0.0
        self._consecutive_missed_entries = 0

    def _emit_daily_summary(self, trade_date: datetime.date) -> None:
        self._telemetry.snapshot_tick_types(self._tick_type_counts)
        self._telemetry.update_risk_state(self.daily_pnl, self.consecutive_loss)
        summary = self._telemetry.build_summary(trade_date.isoformat())
        logger.info("DAILY_SUMMARY %s", self._telemetry.format_daily_summary(summary))

    def process_strategy(self, ts: int, price: float, dt: datetime.datetime) -> OrderSignal | None:
        self._maybe_reset_daily_state(dt)
        market = self.indicators.snapshot(ts, price, dt)
        vol_threshold = self._vol_threshold(dt)
        signal, effects = self.strategy.evaluate(
            market,
            self._position_snapshot(),
            self._risk_gate(ts, dt),
            vol_threshold,
            session_force_flatten_time=self._cfg.session_force_flatten_time,
            max_daily_loss_points=self._cfg.max_daily_loss_points,
            on_daily_loss_block=lambda: logger.warning("觸發單日最大虧損，停止新進場"),
        )
        if effects.block_new_entry:
            self.block_new_entry = True
        return signal

    def reset_strategy_state(self) -> None:
        """Reset strategy episode state after fills / session events."""
        self.strategy.reset()

    def reset_momentum(self) -> None:
        """Backward-compatible alias for ``reset_strategy_state``."""
        self.reset_strategy_state()

    def manage_exit(self, price: float, ts: int) -> OrderSignal | None:
        dt = self._last_tick_exchange_dt or datetime.datetime.fromtimestamp(ts)
        market = self.indicators.snapshot(ts, price, dt)
        signal, _effects = self.strategy.manage_exit(market, self._position_snapshot())
        return signal

    def _maybe_kernel_force_flatten(
        self, ts: int, price: float, dt: datetime.datetime
    ) -> OrderSignal | None:
        """Kernel-owned force flatten at session_force_flatten_time.

        Strategy may return a custom OrderSignal via session_force_flatten_signal
        (for price/slippage/audit customization). If None, kernel synthesizes a
        standard full exit using flatten_slippage_points.
        """
        if self.position_qty <= 0:
            return None
        if self.is_pending or self.exit_pending:
            return None
        risk = self._risk_gate(ts, dt)
        if not risk.force_flatten:
            return None

        market = self.indicators.snapshot(ts, price, dt)
        position = self._position_snapshot()

        # Strategy hook for customization (price, slippage, reason, audit)
        custom, _effects = self.strategy.session_force_flatten_signal(
            market, position, self._cfg.session_force_flatten_time
        )
        if custom is not None:
            # Trust strategy provided signal but ensure intent/qty safety for first version
            if custom.intent != "exit":
                custom = None  # fallthrough to default
            else:
                return custom

        # Default kernel-produced exit (full position, using configured flatten slippage)
        action = "Sell" if self.position_dir == "Long" else "Buy"
        return OrderSignal(
            action=action,
            qty=self.position_qty,
            ref_price=price,
            intent="exit",
            exchange_ts=ts,
            slippage_points=self._cfg.flatten_slippage_points,
            # audit left to None for pure kernel forced; consumers can enrich via telemetry
        )

    def _stage_critical_alert(self, message: str) -> None:
        """Record a CRITICAL alert to be sent outside the lock.

        Must be called with ``self.lock`` held. The actual send happens via
        ``_flush_staged_critical_alert`` after the lock is released, so we never
        do network I/O on the callback hot path.
        """
        self._staged_critical_alert = message

    def _flush_staged_critical_alert(self) -> None:
        """Send any staged CRITICAL alert. Call OUTSIDE the lock."""
        with self.lock:
            message = self._staged_critical_alert
            self._staged_critical_alert = None
        if message:
            self._alerts.send(message, level="CRITICAL")

    def _clear_entry_tracking(self) -> None:
        self.entry_exchange_ts = 0
        self.ticks_since_entry = 0

    def _begin_entry_tracking(self, exchange_ts: int) -> None:
        self.entry_exchange_ts = exchange_ts
        self.ticks_since_entry = 0

    def _activate_vwap_stop_immediately(self) -> None:
        """重啟對帳持倉：進場時間未知，直接啟用 VWAP 停損。"""
        self.entry_exchange_ts = 0
        self.ticks_since_entry = self._cfg.exit_grace_ticks

    def place_order(self, signal: OrderSignal):
        action = signal.action
        qty = signal.qty
        ref_price = signal.ref_price

        try:
            is_market = bool(getattr(signal, "market", False))
            account = self._call_api(lambda: self.api.futopt_account)
            if is_market:
                price = 0.0
                trade = self._call_api(
                    self._order_adapter.place_market,
                    self.contract,
                    action=action,
                    qty=qty,
                    account=account,
                )
            else:
                slip = (
                    signal.slippage_points
                    if signal.slippage_points is not None
                    else self._cfg.ioc_slippage_points
                )
                price = ref_price + slip if action == "Buy" else ref_price - slip
                trade = self._call_api(
                    self._order_adapter.place_ioc_limit,
                    self.contract,
                    action=action,
                    qty=qty,
                    limit_price=price,
                    account=account,
                )
            oid = str(getattr(trade.order, "id", "") or "")
            with self.lock:
                self.pending_trade = trade
                self.pending_order_id = oid
                self.pending_since = self._clock()
                self._exit_order_retry_count = 0
                self._exit_order_retry_at = 0.0

                # Phase 2: Emit pending_armed only when order_id is known (SPEC §5.3 MUST).
                # If oid empty at place time, defer to first callback backfill (avoids duplicate armed).
                if self.pending_order_id:
                    try:
                        exec_audit = ExecAudit(
                            event_type="pending_armed",
                            ts=signal.exchange_ts or 0,
                            signal_id=signal.signal_id or self.pending_signal_id,
                            order_id=self.pending_order_id,
                            limit_price=self.pending_limit_price,
                            direction=signal.action,
                        )
                        logger.info("EXEC_AUDIT %s", format_exec_audit(exec_audit))
                    except Exception:
                        pass  # never break hot path

            # Layer 2 (order worker only): bounded update_status for oid backfill and
            # early terminal capture. Falls back to callback/inference on failure.
            if self._cfg.order_status_query_enabled:
                self._refresh_trade_after_place(trade, signal)
                with self.lock:
                    oid = self.pending_order_id or oid

            logger.info(
                "下單 %s %d 口 @ %s (%s%s) | trade=%s",
                action,
                qty,
                "市價" if is_market else f"{price:.1f}",
                signal.intent,
                "/MKT" if is_market else "",
                oid,
            )
        except Exception as e:
            self._handle_place_order_failure(signal, e)

    def _handle_place_order_failure(self, signal: OrderSignal, exc: Exception) -> None:
        category = classify_order_error(exc)
        intent = signal.intent
        logger.error(
            "下單失敗 | intent=%s category=%s err=%s",
            intent,
            category.value,
            exc,
        )

        if intent == "entry":
            with self.lock:
                self._clear_pending()
            if category == OrderErrorCategory.FATAL:
                self._alerts.send(f"進場下單致命錯誤: {exc}", level="CRITICAL")
            return

        with self.lock:
            attempt = self._exit_order_retry_count

        if should_retry_order(
            intent=intent,
            category=category,
            attempt=attempt,
            max_retries=self._cfg.exit_order_max_retries,
        ):
            with self.lock:
                self._exit_order_retry_count = attempt + 1
                self._exit_order_retry_at = self._clock() + self._cfg.exit_order_retry_delay_sec
            logger.warning(
                "出場下單將退避重試 | attempt=%d/%d delay=%.1fs",
                attempt + 1,
                self._cfg.exit_order_max_retries,
                self._cfg.exit_order_retry_delay_sec,
            )
            return

        self._alerts.send(
            f"出場下單失敗且重試耗盡 | category={category.value} err={exc}",
            level="CRITICAL",
        )
        with self.lock:
            self.block_new_entry = True
        try:
            self.sync_positions()
        except Exception as sync_err:
            logger.error("出場失敗後對帳異常: %s", sync_err)

    def _reconstruct_pending_signal(self) -> OrderSignal | None:
        with self.lock:
            if not self.is_pending or self.pending_intent != "exit":
                return None
            action = self._pending_action
            if not action:
                action = "Sell" if self.position_dir == "Long" else "Buy"
            # Phase 1: prefer actual position_qty for exit sizing (full flatten policy)
            exit_qty = self.position_qty if self.position_qty > 0 else (self.pending_qty or 1)
            return OrderSignal(
                action,
                exit_qty,
                self.pending_signal_price,
                "exit",
                exchange_ts=self.pending_exchange_ts,
                slippage_points=self.pending_ioc_slippage,
                market=getattr(self, "pending_market", False),
            )

    def _check_exit_order_retry(self) -> None:
        with self.lock:
            retry_at = self._exit_order_retry_at
            if retry_at <= 0 or self._clock() < retry_at:
                return
            self._exit_order_retry_at = 0.0

        signal = self._reconstruct_pending_signal()
        if signal is None:
            return
        logger.info("出場下單退避重試觸發")
        self._enqueue_order(signal)

    def _maybe_emergency_market_flatten(self) -> None:
        """P0-5: a stop-loss IOC missed → flatten the held position with a single
        kernel-owned MARKET order (guaranteed fill). Single-flight: never sends
        while any order is in flight; bypasses the entry/exit freeze via
        ``_kernel_converging`` because we KNOW we hold a position to kill."""
        signal = None
        with self.lock:
            if not self._stop_market_flatten_request:
                return
            if self.is_pending or self._settling:
                return  # single-flight; retry next loop once the slot is free
            if self.position_qty <= 0:
                self._stop_market_flatten_request = False
                return
            self._stop_market_flatten_request = False
            action = "Sell" if self.position_dir == "Long" else "Buy"
            qty = self.position_qty
            ref_price = self.indicators.last_tick_price or self.entry_price
            ts = int(self.last_tick_exchange_ts or self._last_tick_exchange_ts_or_zero())
            signal = OrderSignal(
                action=action,
                qty=qty,
                ref_price=ref_price,
                intent="exit",
                exchange_ts=ts,
                market=True,
            )
            self._kernel_converging = True
            try:
                if self._validate_order_signal(signal):
                    if not getattr(signal, "signal_id", ""):
                        signal.signal_id = self._make_signal_id(signal.exchange_ts or ts)
                    self._arm_pending(signal)
                else:
                    signal = None
            finally:
                self._kernel_converging = False
        if signal is not None:
            logger.warning(
                "停損市價平倉 | %s %d 口（kernel 主動，guaranteed fill）",
                signal.action,
                signal.qty,
            )
            self._enqueue_order(signal)

    def _start_order_worker(self) -> None:
        if self._order_worker_started:
            return
        self._order_worker_started = True
        threading.Thread(
            target=self._order_worker_loop,
            daemon=True,
            name="order-worker",
        ).start()

    def _order_worker_loop(self) -> None:
        while True:
            item = self._order_queue.get()
            try:
                if item is None:
                    break
                if isinstance(item, QueryStatusTask):
                    self._query_pending_status(item)
                else:
                    self.place_order(item)
            except BaseException as e:
                # Catch PanicException etc. too; order worker death is critical (no more orders).
                logger.error("Order worker 嚴重異常: %s", e)
                # Re-raise only system exits; otherwise continue to not lose the worker.
                if isinstance(e, (SystemExit, KeyboardInterrupt)):
                    raise
                # else log and continue (worker stays alive)
            finally:
                self._order_queue.task_done()

    def _enqueue_query_status(self) -> None:
        """Enqueue a Layer-2 update_status(trade) on the order worker (debounced)."""
        if not self._cfg.order_status_query_enabled:
            return
        task: QueryStatusTask | None = None
        with self.lock:
            if not self.is_pending:
                return
            if self._status_query_inflight:
                return
            self._status_query_inflight = True
            task = QueryStatusTask(
                order_id=str(self.pending_order_id or ""),
                generation=self._pending_generation,
            )
        if task is None:
            return
        if self._order_sync_mode:
            self._query_pending_status(task)
            return
        self._start_order_worker()
        self._order_queue.put_nowait(task)

    @staticmethod
    def _read_trade_terminal_state(trade) -> tuple[str, int, int]:
        """Normalize trade.status to (state, deal_qty, cancel_qty). MockBroker-safe."""
        if trade is None:
            return "unknown", 0, 0
        try:
            status_info = getattr(trade, "status", None)
            if status_info is None:
                return "unknown", 0, 0
            raw_status = getattr(status_info, "status", None)
            if raw_status is None:
                return "unknown", 0, 0
            status_name = str(raw_status)
            if "." in status_name:
                status_name = status_name.rsplit(".", 1)[-1]
            deal_qty = int(getattr(status_info, "deal_quantity", 0) or 0)
            cancel_qty = int(getattr(status_info, "cancel_quantity", 0) or 0)
            mapping = {
                "Filled": "filled",
                "PartFilled": "partial",
                "Cancelled": "cancelled",
                "Failed": "failed",
                "Inactive": "inactive",
                "PendingSubmit": "working",
                "PreSubmitted": "working",
                "Submitted": "working",
            }
            return mapping.get(status_name, "unknown"), deal_qty, cancel_qty
        except Exception:
            return "unknown", 0, 0

    def _apply_query_terminal_state(
        self, state: str, deal_qty: int, cancel_qty: int
    ) -> bool:
        """Resolve pending from a Layer-2 terminal snapshot. Returns True when settled."""
        _ = cancel_qty  # reserved for audit; position truth comes from list_positions
        if state == "filled":
            return self._reconcile_pending_via_broker_snapshot()
        if state == "partial":
            if self._reconcile_pending_via_broker_snapshot():
                return True
            return False

        if state not in ("cancelled", "failed", "inactive"):
            return False

        # IOC can report Cancelled/Failed with non-zero deal_quantity (partial fill +
        # remainder cancelled). Adopt via Layer 3 before treating as a clean no-fill.
        if deal_qty > 0 and self._reconcile_pending_via_broker_snapshot():
            return True

        broker = self.read_broker_position()
        if broker is None:
            return False
        broker_qty, broker_dir = broker
        with self.lock:
            if not self.is_pending:
                return True
            intent = self.pending_intent
            kernel_qty = self.position_qty
            kernel_dir = self.position_dir
            exit_reason = self.pending_exit_reason or ""

        if intent == PendingIntent.ENTRY:
            # A matching broker fill may already be visible even when status says
            # cancelled (report lag). Try Layer 3 before miss / anomaly paths.
            if self._reconcile_pending_via_broker_snapshot():
                return True

            entry_anomaly = broker_qty > 0 and (
                kernel_qty == 0 or broker_qty > kernel_qty
            )
            if entry_anomaly:
                # Layer 2 confirmed the entry order is terminal at the exchange —
                # unlike a live exit flatten, there is nothing left in-flight to
                # protect. clear_pending=True unblocks convergence flatten.
                self._halt_position_unconfirmed(
                    f"Layer2 終態={state} 但券商持倉不符 | broker={broker_dir} {broker_qty}口",
                    clear_pending=True,
                )
                return True
            self._resolve_entry_missed()
            return True

        # exit: adopt if broker already reflects a reduction
        if broker_qty < kernel_qty:
            return self._apply_pending_broker_truth(broker_qty, broker_dir)

        if broker_qty == kernel_qty and broker_dir == kernel_dir:
            # Layer 2 authoritative terminal (cancelled/failed/inactive): equivalent
            # to an explicit Cancelled callback — clear pending even during HALT so
            # convergence / market escalation can re-arm. The HALT no-clear rule
            # applies only to Layer 3 inference (unchanged broker read), not here.
            if exit_reason in _STOP_LOSS_REASONS and self._cfg.emergency_market_orders:
                with self.lock:
                    self._stop_market_flatten_request = True
                    logger.warning(
                        "停損 IOC 未成交（Layer2 %s）→ 安排市價平倉 | reason=%s",
                        state,
                        exit_reason,
                    )
            with self.lock:
                if self.is_pending:
                    self._clear_pending()
            return True

        if broker_qty > kernel_qty or broker_dir != kernel_dir:
            self._halt_position_unconfirmed(
                f"Layer2 終態={state} 券商持倉異常 | kernel={kernel_dir} {kernel_qty} "
                f"broker={broker_dir} {broker_qty}",
                clear_pending=True,
            )
            return True
        return False

    def _query_pending_status(self, task: QueryStatusTask) -> None:
        """Layer 2: update_status(trade) on the order worker only."""
        try:
            with self.lock:
                if not self._pending_task_current(task):
                    return
                trade = self.pending_trade
            if trade is None:
                return

            timeout = int(self._cfg.order_status_query_timeout_ms)
            self._call_api(self.api.update_status, trade=trade, timeout=timeout)
            state, deal_qty, cancel_qty = self._read_trade_terminal_state(trade)
            logger.info(
                "Layer2 update_status | order=%s state=%s deal=%d cancel=%d",
                task.order_id,
                state,
                deal_qty,
                cancel_qty,
            )

            # The bounded API call may take up to order_status_query_timeout_ms; a
            # callback could have resolved/re-armed pending meanwhile. Re-check the
            # generation before acting so we never apply this terminal to a NEW order.
            with self.lock:
                if not self._pending_task_current(task):
                    return

            if state in ("working", "unknown"):
                self._reconcile_pending_via_broker_snapshot()
                return

            self._apply_query_terminal_state(state, deal_qty, cancel_qty)
        except Exception as e:
            logger.warning("Layer2 update_status 失敗: %s", e)
        finally:
            with self.lock:
                self._status_query_inflight = False

    def _pending_task_current(self, task: QueryStatusTask) -> bool:
        """True if ``task`` still refers to the live pending. Caller holds the lock.

        Generation is the primary guard (handles an empty order_id at enqueue time);
        order_id is a secondary check once known.
        """
        if not self.is_pending:
            return False
        if task.generation >= 0 and task.generation != self._pending_generation:
            return False
        if task.order_id and self.pending_order_id and self.pending_order_id != task.order_id:
            return False
        return True

    def _refresh_trade_after_place(self, trade, signal: OrderSignal) -> None:
        """Place-time bounded refresh: oid backfill + early terminal capture."""
        with self.lock:
            gen = self._pending_generation
        try:
            timeout = int(self._cfg.order_status_query_timeout_ms)
            self._call_api(self.api.update_status, trade=trade, timeout=timeout)
        except Exception as e:
            logger.warning("place 後 update_status 失敗: %s", e)
            return

        oid = str(getattr(getattr(trade, "order", None), "id", "") or "")
        with self.lock:
            if not self.is_pending or self._pending_generation != gen:
                return  # pending resolved / re-armed during the API call
            if oid and not self.pending_order_id:
                self.pending_order_id = oid
                try:
                    exec_audit = ExecAudit(
                        event_type="pending_armed",
                        ts=signal.exchange_ts or 0,
                        signal_id=signal.signal_id or self.pending_signal_id,
                        order_id=self.pending_order_id,
                        limit_price=self.pending_limit_price,
                        direction=signal.action,
                    )
                    logger.info("EXEC_AUDIT %s (layer2 backfill)", format_exec_audit(exec_audit))
                except Exception:
                    pass

        state, deal_qty, cancel_qty = self._read_trade_terminal_state(trade)
        if state in ("working", "unknown"):
            return
        with self.lock:
            if not self.is_pending or self._pending_generation != gen:
                return
        self._apply_query_terminal_state(state, deal_qty, cancel_qty)

    def _enqueue_order(self, signal: OrderSignal) -> None:
        """Decouple API place_order from on_tick lock (live: async worker)."""
        if self._order_sync_mode:
            self.place_order(signal)
            return
        self._start_order_worker()
        self._order_queue.put_nowait(signal)

    def _maybe_dump_raw_order_event(self, stat, msg) -> None:
        if not self._cfg.dump_order_events:
            return
        if stat in self._raw_order_evt_dumped:
            return
        self._raw_order_evt_dumped.add(stat)
        logger.info(
            "RAW_ORDER_EVT %s | keys=%s | %r",
            stat,
            list(msg.keys()),
            msg,
        )

    def handle_order_event(self, stat, msg):
        self._maybe_dump_raw_order_event(stat, msg)
        needs_sync = False
        with self.lock:
            if is_futures_order(stat):
                self._handle_futures_order(msg)
            elif is_futures_deal(stat):
                needs_sync = self._handle_futures_deal(msg)
        if needs_sync:
            self.sync_positions()
        self._flush_staged_critical_alert()

    def _event_order_id(self, msg: dict) -> str | None:
        trade_id = msg.get("trade_id")
        if trade_id:
            return str(trade_id)
        status = msg.get("status") or {}
        for key in ("id", "order_id"):
            value = status.get(key)
            if value:
                return str(value)
        order = msg.get("order") or {}
        for key in ("id", "order_id"):
            value = order.get(key)
            if value:
                return str(value)
        return None

    def _matches_pending_order(self, msg: dict) -> bool:
        expected = self.pending_order_id
        if not expected:
            return False
        actual = self._event_order_id(msg)
        return actual is not None and actual == expected

    def _log_callback_latency(self, msg: dict, *, event: str) -> None:
        """UAT/live calibration: server exchange_ts vs local receive time."""
        status = msg.get("status") or {}
        raw_ts = (
            status.get("exchange_ts")
            or status.get("ts")
            or msg.get("exchange_ts")
            or msg.get("ts")
        )
        if raw_ts is None:
            return
        try:
            delta_ms = (self._clock() - float(raw_ts)) * 1000.0
            logger.info(
                "CALLBACK_LATENCY %s | exchange_ts=%s local_recv_delta_ms=%.1f order=%s",
                event,
                raw_ts,
                delta_ms,
                self._event_order_id(msg),
            )
        except (TypeError, ValueError):
            pass

    def _handle_futures_order(self, msg):
        self._log_callback_latency(msg, event="order")
        op = msg.get("operation", {})
        op_code = op.get("op_code", "")
        op_type = op.get("op_type", "")
        status = msg.get("status", {}).get("status", "")

        logger.info(
            "委託回報 | op=%s code=%s status=%s | order=%s",
            op_type,
            op_code,
            status,
            self._event_order_id(msg),
        )

        if not self.is_pending:
            return
        actual_id = self._event_order_id(msg)
        if not self.pending_order_id and actual_id:
            # Backfill order_id from first callback if it was empty at place time (common in sim/PendingSubmit).
            # Re-emit armed with real id (to satisfy SPEC §5.3 and audit completeness).
            self.pending_order_id = actual_id
            try:
                exec_audit = ExecAudit(
                    event_type="pending_armed",
                    ts=getattr(self, 'pending_exchange_ts', 0) or 0,
                    signal_id=self.pending_signal_id,
                    order_id=self.pending_order_id,
                    limit_price=self.pending_limit_price,
                    direction=self._pending_action or "",
                )
                logger.info("EXEC_AUDIT %s (backfilled)", format_exec_audit(exec_audit))
            except Exception:
                pass
        if not self._matches_pending_order(msg):
            logger.warning(
                "忽略非當前委託狀態回報 | expected=%s got=%s",
                self.pending_order_id,
                actual_id,
            )
            return

        if op_code and op_code != "00":
            logger.warning("委託失敗: %s", op.get("op_msg", op_code))
            self._clear_pending()
            return

        if status in ("Cancelled", "Failed") or op_type in ("Cancel", "Delete"):
            deal_qty = msg.get("status", {}).get("deal_quantity", 0)
            if deal_qty == 0:
                if self.pending_intent == PendingIntent.ENTRY:
                    tag = "intent_cancelled"
                    if (
                        self._pending_intent_cancel_exchange_dt is not None
                        and self._calendar.is_opening_session_window(
                            self._pending_intent_cancel_exchange_dt
                        )
                    ):
                        tag = "intent_cancelled_open_session"
                    self._telemetry.record_intent_cancelled(tag)
                    logger.info(
                        "委託未成交/已取消，重置 pending | tag=%s",
                        tag,
                    )
                    cancel_tag = tag
                else:
                    logger.info("委託未成交/已取消，重置 pending")
                    cancel_tag = ""
                    # P0-5: a STOP-LOSS exit IOC that missed (no fill) must not be
                    # left to chase with another limit IOC in a fast market →
                    # escalate to a kernel-owned MARKET flatten (guaranteed fill).
                    if (
                        bool(self._cfg.emergency_market_orders)
                        and self.pending_exit_reason in _STOP_LOSS_REASONS
                        and self.position_qty > 0
                    ):
                        self._stop_market_flatten_request = True
                        logger.warning(
                            "停損 IOC 未成交 → 安排市價平倉（emergency）| reason=%s",
                            self.pending_exit_reason,
                        )
                # Emit EXEC cancel (Phase 2) - for non-happy cancel path coverage
                try:
                    exec_audit = ExecAudit(
                        event_type="pending_cancelled",
                        ts=int(self.pending_exchange_ts or 0),
                        signal_id=self.pending_signal_id,
                        tag=cancel_tag,
                        order_id=self.pending_order_id or "",
                    )
                    logger.info("EXEC_AUDIT %s", format_exec_audit(exec_audit))
                except Exception:
                    pass
                self._clear_pending()

    def _handle_futures_deal(self, msg) -> bool:
        self._log_callback_latency(msg, event="deal")
        price = float(msg["price"])
        qty = int(msg["quantity"])
        action = msg.get("action", "")
        order_id = self._event_order_id(msg)
        logger.info(
            "成交回報 | %s %d 口 @ %.1f | order=%s",
            action,
            qty,
            price,
            order_id,
        )

        if not self.is_pending:
            # P0-2: an orphan deal (no pending) almost always means a real broker
            # fill whose callback arrived after we cleared pending on timeout.
            # Do NOT silently drop it: force a reconcile + circuit-break new entry.
            logger.warning(
                "孤兒成交回報（無 pending）→ HALT 並全面凍結新單 | order=%s qty=%d @ %.1f",
                order_id,
                qty,
                price,
            )
            # P0-5: unattributable fill → position is unconfirmed. Freeze BOTH
            # entry and exit (not just block_new_entry); kernel converges via
            # reconcile + single flatten once broker truth is adopted.
            self.block_new_entry = True
            self._position_unconfirmed = True
            self._stage_critical_alert(
                f"孤兒成交回報（無 pending）| order={order_id} qty={qty} @ {price} "
                "→ 已 HALT 並凍結所有新單；請人工核對券商部位"
            )
            return True  # trigger sync_positions in caller

        # Symmetric backfill for deal-first events (if pending_order_id was empty at place time)
        if not self.pending_order_id and order_id:
            self.pending_order_id = order_id
            logger.debug("Backfilled pending_order_id from deal event: %s", order_id)
            try:
                exec_audit = ExecAudit(
                    event_type="pending_armed",
                    ts=getattr(self, 'pending_exchange_ts', 0) or 0,
                    signal_id=self.pending_signal_id,
                    order_id=self.pending_order_id,
                    limit_price=self.pending_limit_price,
                    direction=self._pending_action or "",
                )
                logger.info("EXEC_AUDIT %s (backfilled from deal)", format_exec_audit(exec_audit))
            except Exception:
                pass

        if not self._matches_pending_order(msg):
            # P0-2: a deal for a different order_id while we hold a pending is a
            # real broker fill we did not expect (e.g. stale order, duplicate
            # leg). Reconcile instead of dropping; keep current pending intact.
            logger.warning(
                "非當前委託成交回報 → HALT 並全面凍結新單 | expected=%s got=%s qty=%d @ %.1f",
                self.pending_order_id,
                order_id,
                qty,
                price,
            )
            # P0-5: a fill for a different order while we hold a pending is an
            # unattributed lot → position unconfirmed. Freeze entry AND exit, and
            # transition the in-flight pending into SETTLING so the settle loop
            # (and, via it, the convergence flatten) starts polling the broker
            # immediately instead of waiting out pending_timeout_sec.
            self.block_new_entry = True
            self._position_unconfirmed = True
            if not self._settling:
                self._settling = True
                self._settle_since = self._clock()
                self._reconcile_last_read = None
                self._reconcile_read_streak = 0
            self._stage_critical_alert(
                f"非當前委託成交回報 | expected={self.pending_order_id} got={order_id} "
                f"qty={qty} @ {price} → 已 HALT 並凍結所有新單；請人工核對券商部位"
            )
            return True  # trigger sync_positions in caller

        is_buy = self._is_buy_action(action)
        return self._apply_deal_fill(price, is_buy, deal_qty=qty)

    def _exit_leg_pnl(self, price: float, leg_qty: int) -> float:
        """Per-lot PnL for one exit fill leg (points, not currency)."""
        if leg_qty <= 0:
            return 0.0
        if self.position_dir == "Long":
            return (price - self.entry_price) * leg_qty
        return (self.entry_price - price) * leg_qty

    def _apply_exit_deal_leg(self, price: float, deal_qty: int) -> float:
        """Apply one exit deal leg: reduce position and accumulate PnL immediately."""
        leg_qty = min(deal_qty, self.position_qty)
        leg_pnl = self._exit_leg_pnl(price, leg_qty)
        if leg_qty > 0:
            self.position_qty -= leg_qty
            self.daily_pnl += leg_pnl
            self._pending_exit_pnl += leg_pnl
        return leg_pnl

    def _apply_deal_fill(self, price: float, is_buy: bool, deal_qty: int = 1) -> bool:
        """套用成交。回傳 True 表示須在 lock 外呼叫 sync_positions()。"""
        expected = self.pending_qty if self.pending_qty > 0 else 1
        if deal_qty > expected:
            logger.warning(
                "成交口數超過 pending | deal=%d expected=%d order=%s",
                deal_qty,
                expected,
                self.pending_order_id,
            )
        self.filled_qty = getattr(self, "filled_qty", 0) + deal_qty
        if self.filled_qty > expected:
            logger.warning(
                "累計成交超過 pending | filled=%d expected=%d order=%s",
                self.filled_qty,
                expected,
                self.pending_order_id,
            )

        # Exit IOC: book PnL and reduce held qty on every deal leg, not only when
        # the order is fully filled (multi-lot partial fills use different prices).
        if self.pending_intent == PendingIntent.EXIT and self.has_position:
            self._apply_exit_deal_leg(price, deal_qty)

        if self.filled_qty < expected:
            logger.info(
                "部分成交進度 | intent=%s %d/%d (deal=%d) order=%s | pending 持續（IOC 未結束不全解鎖）",
                self.pending_intent,
                self.filled_qty,
                expected,
                deal_qty,
                self.pending_order_id,
            )
            return False  # keep pending for more fills or cancel

        intent = self.pending_intent
        order_id = self.pending_order_id or ""
        direction = "Buy" if is_buy else "Sell"
        if intent == PendingIntent.ENTRY:
            if self.has_position:
                logger.warning(
                    "STATE_GUARD unexpected entry fill while positioned | qty=%d dir=%s order=%s",
                    self.position_qty,
                    self.position_dir,
                    order_id,
                )
            self.position_qty = self.filled_qty  # Phase 1: use accumulated filled for this pending
            self.entry_price = price
            self.position_dir = "Long" if is_buy else "Short"
            self.trailing_peak = price
            self._begin_entry_tracking(self.pending_exchange_ts)
            fill_audit = self._telemetry.record_fill(
                intent="entry",
                direction=direction,
                signal_price=self.pending_signal_price,
                fill_price=price,
                is_buy=is_buy,
                limit_price=self.pending_limit_price,
                order_id=order_id,
                ts=self.pending_exchange_ts,
                ioc_slippage_allowed=self.pending_ioc_slippage,
                episode_id=self.pending_episode_id,
                signal_id=self.pending_signal_id,
            )
            logger.info("FILL_AUDIT %s", self._telemetry.format_fill_audit(fill_audit))
            self.reset_strategy_state()
            self._consecutive_missed_entries = 0
            self._clear_pending()
            logger.info("進場完成 | %s %d口 @ %.1f", self.position_dir, self.position_qty, price)
            return False

        elif intent == PendingIntent.EXIT:
            total_pnl = self._pending_exit_pnl
            self._pending_exit_pnl = 0.0

            hold_sec = 0
            if self.entry_exchange_ts > 0:
                hold_sec = max(0, self.pending_exchange_ts - self.entry_exchange_ts)

            if total_pnl < 0:
                self.consecutive_loss += 1
            else:
                self.consecutive_loss = 0

            fill_audit = self._telemetry.record_fill(
                intent="exit",
                direction=direction,
                signal_price=self.pending_signal_price,
                fill_price=price,
                is_buy=is_buy,
                limit_price=self.pending_limit_price,
                order_id=order_id,
                ts=self.pending_exchange_ts,
                ioc_slippage_allowed=self.pending_ioc_slippage,
                exit_reason=self.pending_exit_reason,
                pnl_points=total_pnl,
                hold_sec=hold_sec,
                signal_id=self.pending_signal_id,
            )
            self._telemetry.update_risk_state(self.daily_pnl, self.consecutive_loss)
            logger.info("FILL_AUDIT %s", self._telemetry.format_fill_audit(fill_audit))

            self.last_exit_time = self.pending_exchange_ts
            self._clear_pending()
            if self.position_qty > 0:
                logger.warning(
                    "部分平倉 | 委託已結束，剩 %d 口（續由策略/對帳處理）| 本筆 PnL=%.1f",
                    self.position_qty,
                    total_pnl,
                )
                return True
            self.position_dir = "Flat"
            self.entry_price = 0.0
            self.trailing_peak = 0.0
            self._clear_entry_tracking()
            logger.info(
                "平倉完成 | PnL=%.1f | 今日=%.1f | 連續虧損=%d",
                total_pnl,
                self.daily_pnl,
                self.consecutive_loss,
            )
            return True  # re-sync to confirm broker is truly flat

        if intent == PendingIntent.EXIT and not self.has_position and self._pending_exit_pnl == 0:
            logger.warning(
                "STATE_GUARD unexpected exit fill while flat | order=%s",
                order_id,
            )

        # Light state guard after fill (defensive logging)
        try:
            from trading_engine.core.trading_state import validate_pending_consistency

            validate_pending_consistency(
                is_pending=self.is_pending,
                pending_intent=self.pending_intent,
                exit_pending=self.exit_pending,
                position_qty=getattr(self, "position_qty", 0),
                position_dir=getattr(self, "position_dir", "Flat"),
                logger=logger,
            )
        except Exception:
            pass

        return False

    @staticmethod
    def _is_buy_action(action) -> bool:
        if action == "Buy":
            return True
        name = getattr(action, "name", None)
        return name == "Buy"

    def _still_own_pending(self, trade=None) -> bool:
        """須在 lock 內呼叫：確認 pending 仍屬於此 trade。
        只使用 is_pending，不讀 live trade.order.id（避免 bg thread borrow 風險）。
        pending_order_id 空時仍視為 owned（id 尚未回填），讓 timeout 能清掉卡住的 pending。
        """
        if not self.is_pending:
            return False
        # trade param kept for backward compat with direct callers (tests/reconnect);
        # we intentionally ignore it here to avoid any live object access from bg threads.
        return True

    def _reconcile_pending_via_broker_snapshot(self) -> bool:
        """Reconcile pending against broker position snapshot (sim + live fallback).

        Uses ``list_positions`` only (non-mutating). Unreadable broker -> False.
        """
        broker = self.read_broker_position()
        if broker is None:
            return False
        return self._apply_pending_broker_truth(broker[0], broker[1])

    def _halt_position_unconfirmed(
        self, reason: str, *, clear_pending: bool = False
    ) -> None:
        """P0-5: enter HALT — broker position not confirmed / anomalous.

        Freezes BOTH entry and exit (``_position_unconfirmed`` + ``block_new_entry``)
        and raises a one-shot CRITICAL.

        Single-flight discipline (the never->1-lot guarantee): a live order's
        ``order_id`` is NEVER dropped here unless ``clear_pending=True`` is set by
        a caller that knows the in-flight order is terminal (e.g. an entry IOC
        confirmed missed). Dropping a live order would let convergence issue a
        second flatten while the first is still working at the broker. While a
        live order is kept, we also skip ``sync_positions`` so the settle loop's
        fill-detection math (kernel_qty vs broker_qty) is not clobbered.

        Safe to call from background threads (does its own locking; sends the
        alert and ``sync_positions`` outside the lock).
        """
        with self.lock:
            already = self._position_unconfirmed
            self._position_unconfirmed = True
            self.block_new_entry = True
            if clear_pending and self.is_pending:
                self._clear_pending()
            # A still-live pending means a kernel order may be working at the
            # broker; do not disturb it (no clear, no sync) to stay single-flight.
            keep_live_order = self.is_pending
        logger.warning("部位未確認（HALT）| %s", reason)
        if not keep_live_order:
            try:
                self.sync_positions()
            except Exception as e:
                logger.error("HALT 後對帳失敗: %s", e)
        if not already:
            try:
                self._alerts.send(
                    f"部位未確認，已凍結所有新單（entry+exit）| {reason} "
                    "→ 請人工核對券商部位",
                    level="CRITICAL",
                )
            except Exception as e:
                logger.error("HALT 告警送出失敗: %s", e)

    def _apply_pending_broker_truth(self, broker_qty: int, broker_dir: str) -> bool:
        """Resolve the current pending using an already-read broker snapshot.

        The broker position is the single source of truth (P0-5). Returns True
        when the pending is fully resolved — whether the order filled, did not
        fill, or escalated to HALT. Returns False when the broker does not yet
        reflect a resolvable outcome (caller keeps settling / retries).
        """
        ceiling = self._cfg.max_position_qty
        within_ceiling = ceiling <= 0 or broker_qty <= ceiling
        with self.lock:
            if not self.is_pending:
                return True
            intent = self.pending_intent
            kernel_qty = self.position_qty
            kernel_dir = self.position_dir
            pending_qty = self.pending_qty if self.pending_qty > 0 else 1
            pending_action = self._pending_action or ""
            fill_price = self.pending_signal_price

        # Ceiling backstop: the broker holds MORE than the kernel believed AND
        # more than the ceiling → accumulation anomaly (the >1-lot failure mode).
        # A broker qty <= kernel (e.g. a partial exit still showing lots) is a
        # known/decreasing position handled by the normal resolution below.
        if ceiling > 0 and broker_qty > ceiling and broker_qty > kernel_qty:
            # An ENTRY that produced >ceiling is terminal (it filled) → safe to
            # clear and adopt truth. An EXIT/flatten that is still live must be
            # kept (single-flight) so convergence does not double-send.
            self._halt_position_unconfirmed(
                f"對帳發現超過部位上限 | kernel={kernel_dir} {kernel_qty}口 "
                f"broker={broker_dir} {broker_qty}口 > max={ceiling}",
                clear_pending=(intent == PendingIntent.ENTRY),
            )
            return True

        if intent == PendingIntent.ENTRY:
            expected_dir = "Long" if pending_action == "Buy" else "Short"
            entry_filled = (
                broker_qty == pending_qty
                and broker_dir == expected_dir
                and (
                    (kernel_qty == 0 and kernel_dir == "Flat")
                    or (kernel_qty == broker_qty and kernel_dir == expected_dir)
                )
            )
            if entry_filled:
                if kernel_qty == broker_qty and kernel_dir == expected_dir:
                    with self.lock:
                        if self.is_pending:
                            self._consecutive_missed_entries = 0
                            self._clear_pending()
                    return True
                logger.info(
                    "結算對帳：entry 已成交（broker=%s %d口）→ 採用券商為準",
                    broker_dir,
                    broker_qty,
                )
                need_sync = False
                with self.lock:
                    if not self.is_pending:
                        return True
                    self.filled_qty = 0
                    self._apply_deal_fill(
                        fill_price,
                        broker_dir == "Long",
                        deal_qty=max(1, broker_qty - kernel_qty),
                    )
                    need_sync = not self.is_pending
                if need_sync:
                    self.sync_positions()
                return need_sync
            # Not (yet) a positive fill. A flat snapshot alone is not proof of
            # non-fill during report latency; the time-gated MISSED decision lives
            # in ``_settle_via_reconcile`` (``entry_miss_confirm_sec`` + debounce).
            return False

        if intent == PendingIntent.EXIT:
            exit_filled = broker_qty < kernel_qty and (
                broker_qty == 0 or broker_dir == kernel_dir
            )
            if exit_filled:
                logger.info(
                    "結算對帳：exit 已成交（broker=%s %d口）→ 採用券商為準",
                    broker_dir,
                    broker_qty,
                )
                need_sync = False
                with self.lock:
                    if not self.is_pending:
                        return True
                    self.filled_qty = 0
                    is_buy = self.position_dir == "Short"
                    self._apply_deal_fill(
                        fill_price, is_buy, deal_qty=max(1, kernel_qty - broker_qty)
                    )
                    need_sync = not self.is_pending
                if need_sync:
                    self.sync_positions()
                return need_sync
            # No-fill but broker confirms the position is unchanged, consistent,
            # and within the ceiling → safe to clear pending; normal operation
            # resumes (a confirmed, in-bounds position may be re-exited by the
            # strategy on a later tick).
            #
            # CRITICAL single-flight rule: do NOT infer-clear during HALT
            # (`_position_unconfirmed`). Under multi-minute broker report latency a
            # live flatten can sit unreflected; clearing it here would let
            # convergence send a SECOND flatten and over-flatten. During HALT an
            # exit resolves ONLY on a real reduction (above) or an explicit
            # Cancelled callback (`_handle_futures_order`); otherwise keep settling.
            if (
                broker_qty == kernel_qty
                and broker_dir == kernel_dir
                and within_ceiling
            ):
                with self.lock:
                    if not self.is_pending:
                        return True
                    if self._position_unconfirmed:
                        return False
                    logger.info(
                        "結算對帳：exit 未成交但部位與券商一致（%s %d口）→ 清除 pending 回復正常",
                        broker_dir,
                        broker_qty,
                    )
                    self._clear_pending()
                return True
            # Broker holds MORE than the kernel believed → extra/unattributed lots.
            # A flatten may still be live here; keep it (single-flight) so
            # convergence does not double-send.
            if broker_qty > kernel_qty:
                self._halt_position_unconfirmed(
                    f"對帳發現額外部位 | kernel={kernel_dir} {kernel_qty}口 "
                    f"broker={broker_dir} {broker_qty}口",
                    clear_pending=False,
                )
                return True
            return False

        return False

    def _record_reconcile_read(self, broker: tuple[int, str]) -> bool:
        """Debounce broker reads. Returns True once the same (qty, dir) has been
        observed ``reconcile_confirm_reads`` times in a row (P0-5)."""
        need = max(1, int(self._cfg.reconcile_confirm_reads))
        with self.lock:
            if self._reconcile_last_read == broker:
                self._reconcile_read_streak += 1
            else:
                self._reconcile_last_read = broker
                self._reconcile_read_streak = 1
            return self._reconcile_read_streak >= need

    def _resolve_entry_missed(self) -> None:
        """Entry IOC declared missed after stable readable-flat debounce.

        Clean resume (no sticky HALT) unless the consecutive-miss circuit breaker
        trips — that indicates a structural failure (orders not reaching exchange).
        """
        max_miss = int(self._cfg.max_consecutive_missed_entries)
        with self.lock:
            if not self.is_pending or self.pending_intent != PendingIntent.ENTRY:
                return
            self._consecutive_missed_entries += 1
            count = self._consecutive_missed_entries
            order_id = self.pending_order_id or ""

        logger.warning(
            "entry IOC 未成交 → 視為 miss，恢復正常 | order=%s consecutive=%d",
            order_id,
            count,
        )

        if max_miss > 0 and count >= max_miss:
            self._halt_position_unconfirmed(
                f"連續 {count} 筆 entry miss（≥{max_miss}）→ 結構性問題，委託可能未達交易所",
                clear_pending=True,
            )
            return

        with self.lock:
            if self.is_pending:
                self._clear_pending()

    def _settle_via_reconcile(self) -> None:
        """P0-5 settle loop: while SETTLING, poll the broker on a fast cadence and
        adopt debounced truth. Transient entry uncertainty → MISSED clean resume;
        sticky HALT is reserved for genuine anomalies (unreadable broker, ceiling
        breach, orphan fill, consecutive-miss circuit breaker)."""
        with self.lock:
            if not self._settling or not self.is_pending:
                return
            settle_since = self._settle_since
            intent = self.pending_intent
        clear_on_halt = intent == PendingIntent.ENTRY

        # Flag-gated only (see _check_pending_timeout): catch a Cancelled in ~1s
        # rather than waiting entry_miss_confirm_sec. Inference remains the fallback
        # when the query says working/unknown.
        if self._cfg.order_status_query_enabled:
            self._enqueue_query_status()

        broker = self.read_broker_position()
        if broker is None:
            if self._clock() - settle_since >= self._cfg.settle_timeout_sec:
                self._halt_position_unconfirmed(
                    f"結算逾時 {self._cfg.settle_timeout_sec}s 且券商持倉讀取失敗",
                    clear_pending=clear_on_halt,
                )
            return

        broker_qty, broker_dir = broker

        if self._record_reconcile_read(broker):
            if self._apply_pending_broker_truth(broker_qty, broker_dir):
                return  # resolved (filled / exit no-fill / HALT from ceiling)

            # Entry: stable readable-flat past confirm window → MISSED (resume).
            if (
                intent == PendingIntent.ENTRY
                and broker_qty == 0
                and broker_dir == "Flat"
                and self._clock() - settle_since >= self._cfg.entry_miss_confirm_sec
            ):
                self._resolve_entry_missed()
                return

        # Exit: settle window exhausted without resolution → HALT (single-flight).
        if intent != PendingIntent.ENTRY and self._clock() - settle_since >= self._cfg.settle_timeout_sec:
            self._halt_position_unconfirmed(
                f"結算逾時 {self._cfg.settle_timeout_sec}s 仍無法確認部位",
                clear_pending=False,
            )
            return

        # Entry: debounce never stabilized flat within settle window → anomaly HALT.
        if intent == PendingIntent.ENTRY and self._clock() - settle_since >= self._cfg.settle_timeout_sec:
            self._halt_position_unconfirmed(
                f"結算逾時 {self._cfg.settle_timeout_sec}s entry 仍無法 debounce 確認 flat",
                clear_pending=True,
            )

    def _maybe_converge_flatten(self) -> None:
        """P0-5 convergence: while HALT and the broker-confirmed position is not
        flat, the kernel sends exactly ONE flatten sized to the DEBOUNCED broker
        truth (not the possibly-stale kernel belief), then returns to SETTLING to
        await confirmation. Single-flight: never sends while any order is in
        flight. Lifts HALT once the broker is confirmed flat (``block_new_entry``
        stays sticky until daily reset / manual clear)."""
        with self.lock:
            if not self._position_unconfirmed:
                return
            if self.is_pending or self._settling:
                return  # single-flight: an order is already in flight / confirming
            now = self._clock()
            if now < self._converge_flatten_at:
                return

        # Size to a fresh, debounced broker read. Never act on an unreadable or
        # not-yet-confirmed broker (the whole point: stale reads must not drive
        # orders). Requires reconcile_confirm_reads consecutive identical reads.
        broker = self.read_broker_position()
        if broker is None:
            return
        if not self._record_reconcile_read(broker):
            return
        broker_qty, broker_dir = broker

        signal = None
        with self.lock:
            if not self._position_unconfirmed or self.is_pending or self._settling:
                return
            if broker_qty <= 0:
                # Confirmed flat → lift HALT. Keep block_new_entry sticky so no
                # NEW entry resumes until the operator / daily reset clears it.
                self._position_unconfirmed = False
                self._converge_flatten_at = 0.0
                self._reconcile_last_read = None
                self._reconcile_read_streak = 0
                if self.position_qty != 0:
                    self.position_qty = 0
                    self.position_dir = "Flat"
                logger.info("部位已確認 flat → 解除 HALT（block_new_entry 維持至日切/人工）")
                return
            # Adopt broker truth into kernel accounting, then flatten exactly it.
            self.position_qty = broker_qty
            self.position_dir = broker_dir
            now = self._clock()
            self._converge_flatten_at = now + max(1, int(self._cfg.reconcile_fast_sec))
            action = "Sell" if broker_dir == "Long" else "Buy"
            qty = broker_qty
            ref_price = self.indicators.last_tick_price or self.entry_price
            ts = int(self.last_tick_exchange_ts or self._last_tick_exchange_ts_or_zero())
            use_market = bool(self._cfg.emergency_market_orders)
            signal = OrderSignal(
                action=action,
                qty=qty,
                ref_price=ref_price,
                intent="exit",
                exchange_ts=ts,
                slippage_points=self._cfg.flatten_slippage_points,
                market=use_market,
            )
            # Kernel-owned convergence: arm directly (bypassing the strategy and
            # the settling/unconfirmed freeze in _validate_order_signal). Emergency
            # market order → guaranteed fill so the HALT actually converges to flat
            # instead of chasing with limit IOCs.
            self._kernel_converging = True
            try:
                if self._validate_order_signal(signal):
                    if not getattr(signal, "signal_id", ""):
                        signal.signal_id = self._make_signal_id(signal.exchange_ts or ts)
                    self._arm_pending(signal)
                    # Return to SETTLING so _settle_via_reconcile actively polls
                    # the broker for the convergence outcome instead of waiting on
                    # callbacks / a full pending_timeout_sec.
                    self._settling = True
                    self._settle_since = self._clock()
                    self._reconcile_last_read = None
                    self._reconcile_read_streak = 0
                else:
                    signal = None
            finally:
                self._kernel_converging = False
        if signal is not None:
            logger.warning(
                "HALT 收斂平倉 | %s %d 口 @ ref=%.1f（kernel 主動，唯一一張）",
                signal.action,
                signal.qty,
                signal.ref_price,
            )
            self._enqueue_order(signal)

    def _last_tick_exchange_ts_or_zero(self) -> int:
        dt = self._last_tick_exchange_dt
        return int(dt.timestamp()) if dt is not None else 0

    def _reconcile_pending_trade(self, trade) -> bool:
        """補查委託狀態。回傳 True 表示 pending 已處理完畢（含 callback 已搶先處理）。

        根本改進（按此 review 建議）：
        - 背景 thread 絕不對 live trade 物件呼叫 update_status（避免 Shioaji 內部 Rust borrow panic）。
        - 優先靠 handle_order_event callback。
        - 補查走 order_deal_records()（query 新資料，不 mutate live trade），用 pending_order_id 比對。
        - simulation / live fallback：list_positions 快照對帳（P1-2）。
        """
        if self._cfg.simulation:
            return self._reconcile_pending_via_broker_snapshot()

        # 絕不使用 account update_status 來觸發 borrow；直接用 records（query）。
        # 這避免了即使 account 層級也會 borrow 底下 trades 的風險。
        try:
            # order_deal_records() is a query API (non-mutating on live Trade objects in Shioaji).
            # Safe for background threads; assumed not to trigger internal borrow on trades.
            records = self._call_api(self.api.order_deal_records)
        except Exception as e:
            logger.warning("order_deal_records 補查失敗: %s", e)
            records = []

        order_id = self.pending_order_id
        if not order_id:
            return self._reconcile_pending_via_broker_snapshot()

        for state, event in records:
            if not is_futures_deal(state):
                continue
            if str(event.get("trade_id", "")) != order_id:
                continue
            needs_sync = False
            with self.lock:
                if not self.is_pending or self.pending_order_id != order_id:
                    return True
                logger.info("order_deal_records 補查到成交")
                needs_sync = self._handle_futures_deal(event)
            if needs_sync:
                self.sync_positions()
            return True

        return self._reconcile_pending_via_broker_snapshot()

    def _check_pending_timeout(self):
        """P0-5: a pending timeout means the order outcome is UNKNOWN, not FAILED.

        We do NOT clear pending and let the strategy re-issue (that is what caused
        cascading duplicate orders + >1 lot). Instead we try a fast reconcile and,
        if still unresolved, transition into SETTLING: keep ``pending_order_id`` so
        a late fill still attributes, freeze all new orders, and let
        ``_settle_via_reconcile`` converge against the broker (the source of truth).
        """
        with self.lock:
            if not self.is_pending:
                return
            if self._settling:
                # Past the callback-wait window already; the settle loop owns it.
                return
            if self._clock() - self.pending_since < self._cfg.pending_timeout_sec:
                return
            trade = self.pending_trade

        # First attempt: fast reconcile (deal records / broker snapshot).
        # Layer 2 is gated on the flag ALONE (not on simulation): UAT runs the real
        # Shioaji simulation API, so it must exercise update_status to validate borrow
        # safety before production. Backtest's MockBroker is a no-op → "unknown" →
        # inference fallback, so enabling the flag there changes nothing.
        if self._cfg.order_status_query_enabled:
            resolved = self._reconcile_pending_via_broker_snapshot()
            if not resolved and trade is not None:
                resolved = self._reconcile_pending_trade(trade)
            if not resolved:
                self._enqueue_query_status()
        elif trade is not None:
            resolved = self._reconcile_pending_trade(trade)
        else:
            resolved = self._reconcile_pending_via_broker_snapshot()

        intent = None
        entered_settling = False
        with self.lock:
            if not self.is_pending:
                return
            if resolved:
                return
            if not self._still_own_pending():
                return
            if not self._settling:
                self._settling = True
                self._settle_since = self._clock()
                self._reconcile_last_read = None
                self._reconcile_read_streak = 0
                entered_settling = True
                intent = self.pending_intent
                # Phase 2 audit: timeout now means "switch to broker reconcile".
                try:
                    exec_audit = ExecAudit(
                        event_type="pending_timeout",
                        ts=int(self.pending_exchange_ts or 0),
                        signal_id=self.pending_signal_id,
                        pending_sec=self._cfg.pending_timeout_sec,
                    )
                    logger.info("EXEC_AUDIT %s", format_exec_audit(exec_audit))
                except Exception:
                    pass

        if entered_settling:
            logger.warning(
                "Pending 超時 %.0fs 未獲回報 → 轉主動對帳確認（UNKNOWN，不重下單、凍結新單）",
                self._cfg.pending_timeout_sec,
            )
            self._alerts.send(
                f"Pending 超時無回報（intent={intent or 'unknown'}）→ 轉對帳確認並凍結新單 "
                f"| timeout={self._cfg.pending_timeout_sec}s",
                level="CRITICAL",
            )
            # Kick off the first reconcile attempt immediately.
            self._settle_via_reconcile()
