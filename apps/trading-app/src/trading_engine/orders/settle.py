from __future__ import annotations

from trading_engine.core.order_events import is_futures_deal, is_futures_order
from trading_engine.core.trading_state import PendingIntent
from trading_engine.core.types import OrderSignal
from trading_engine.orders.constants import _STOP_LOSS_REASONS
from trading_engine.orders.logutil import logger

class OrderSettleMixin:
    def _reconcile_pending_via_broker_snapshot(self) -> bool:
        """Reconcile pending against broker position snapshot (sim + live fallback).

        Uses ``list_positions`` only (non-mutating). Unreadable broker -> False.
        """
        broker = self.read_broker_position()
        if broker is None:
            return False
        return self._apply_pending_broker_truth(broker[0], broker[1])


    def _halt_position_unconfirmed(
        self,
        reason: str,
        *,
        clear_pending: bool = False,
        send_alert: bool = True,
    ) -> None:
        """P0-5: enter HALT — broker position not confirmed / anomalous.

        Freezes BOTH entry and exit (``_position_unconfirmed`` + ``block_new_entry``)
        and raises a one-shot CRITICAL when ``send_alert`` is True (callers that
        own a more specific CRITICAL should pass ``send_alert=False``).

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
            already = self._integrity._position_unconfirmed
            self._integrity._position_unconfirmed = True
            self._book.block_new_entry = True
            if clear_pending and self._book.is_pending:
                self._clear_pending(watch_late_fill=True)
            # A still-live pending means a kernel order may be working at the
            # broker; do not disturb it (no clear, no sync) to stay single-flight.
            keep_live_order = self._book.is_pending
        logger.warning("部位未確認（HALT）| %s", reason)
        if not keep_live_order:
            try:
                self.sync_positions()
            except Exception as e:
                logger.error("HALT 後對帳失敗: %s", e)
        if send_alert and not already:
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
            if not self._book.is_pending:
                return True
            intent = self._book.pending_intent
            kernel_qty = self._book.position_qty
            kernel_dir = self._book.position_dir
            pending_qty = self._book.pending_qty if self._book.pending_qty > 0 else 1
            pending_action = self._book._pending_action or ""
            fill_price = self._book.pending_signal_price

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
                        if self._book.is_pending:
                            self._integrity._consecutive_missed_entries = 0
                            self._clear_pending()
                    return True
                logger.info(
                    "結算對帳：entry 已成交（broker=%s %d口）→ 採用券商為準",
                    broker_dir,
                    broker_qty,
                )
                need_sync = False
                with self.lock:
                    if not self._book.is_pending:
                        return True
                    self._book.filled_qty = 0
                    self._apply_deal_fill(
                        fill_price,
                        broker_dir == "Long",
                        deal_qty=max(1, broker_qty - kernel_qty),
                    )
                    need_sync = not self._book.is_pending
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
                    if not self._book.is_pending:
                        return True
                    self._book.filled_qty = 0
                    is_buy = self._book.position_dir == "Short"
                    self._apply_deal_fill(
                        fill_price, is_buy, deal_qty=max(1, kernel_qty - broker_qty)
                    )
                    need_sync = not self._book.is_pending
                if need_sync:
                    self.sync_positions()
                return need_sync
            # L3 unchanged read is NEVER terminal for exits (single-flight).
            # A live IOC may have filled while list_positions still shows the
            # pre-flatten position. Resolution only via L1/L2 or time-gated
            # ``_resolve_exit_missed`` in ``_settle_via_reconcile``.
            if (
                broker_qty == kernel_qty
                and broker_dir == kernel_dir
                and within_ceiling
            ):
                return False
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
            if self._integrity._reconcile_last_read == broker:
                self._integrity._reconcile_read_streak += 1
            else:
                self._integrity._reconcile_last_read = broker
                self._integrity._reconcile_read_streak = 1
            return self._integrity._reconcile_read_streak >= need


    def _resolve_entry_missed(self) -> None:
        """Entry IOC declared missed after stable readable-flat debounce.

        Clean resume (no sticky HALT) unless the consecutive-miss circuit breaker
        trips — that indicates a structural failure (orders not reaching exchange).
        """
        max_miss = int(self._cfg.max_consecutive_missed_entries)
        with self.lock:
            if not self._book.is_pending or self._book.pending_intent != PendingIntent.ENTRY:
                return
            self._integrity._consecutive_missed_entries += 1
            count = self._integrity._consecutive_missed_entries
            order_id = self._book.pending_order_id or ""

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
            if self._book.is_pending:
                self._clear_pending(watch_late_fill=True)


    def _resolve_exit_missed(self) -> None:
        """Exit IOC declared missed after stable unchanged-position debounce.

        Stop-loss paths escalate to kernel-owned market flatten (never strategy
        limit retry). Profit/trailing exits clear pending for a single retry.
        """
        with self.lock:
            if not self._book.is_pending or self._book.pending_intent != PendingIntent.EXIT:
                return
            exit_reason = self._book.pending_exit_reason or ""
            order_id = self._book.pending_order_id or ""

        logger.warning(
            "exit IOC 未成交 → 視為 miss | order=%s reason=%s",
            order_id,
            exit_reason,
        )

        if exit_reason in _STOP_LOSS_REASONS and self._cfg.emergency_market_orders:
            with self.lock:
                if self._book.is_pending and self._book.pending_intent == PendingIntent.EXIT:
                    self._integrity._stop_market_flatten_request = True
                    logger.warning(
                        "停損 IOC 未成交（L3 miss）→ 安排市價平倉 | reason=%s",
                        exit_reason,
                    )

        with self.lock:
            if self._book.is_pending:
                self._clear_pending(watch_late_fill=True)


    def _settle_via_reconcile(self) -> None:
        """P0-5 settle loop: while SETTLING, poll the broker on a fast cadence and
        adopt debounced truth. Transient entry uncertainty → MISSED clean resume;
        sticky HALT is reserved for genuine anomalies (unreadable broker, ceiling
        breach, orphan fill, consecutive-miss circuit breaker)."""
        with self.lock:
            if not self._integrity._settling or not self._book.is_pending:
                return
            settle_since = self._integrity._settle_since
            intent = self._book.pending_intent
            kernel_qty = self._book.position_qty
            kernel_dir = self._book.position_dir
        clear_on_halt = intent == PendingIntent.ENTRY

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

            # Exit: stable unchanged position past confirm window → MISSED.
            if (
                intent == PendingIntent.EXIT
                and broker_qty == kernel_qty
                and broker_dir == kernel_dir
                and kernel_qty > 0
                and self._clock() - settle_since >= self._cfg.exit_miss_confirm_sec
            ):
                self._resolve_exit_missed()
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
            if not self._integrity._position_unconfirmed:
                return
            if self._book.is_pending or self._integrity._settling:
                return  # single-flight: an order is already in flight / confirming
            now = self._clock()
            if now < self._integrity._converge_flatten_at:
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
            if not self._integrity._position_unconfirmed or self._book.is_pending or self._integrity._settling:
                return
            if broker_qty <= 0:
                # Confirmed flat → lift HALT. Keep block_new_entry sticky so no
                # NEW entry resumes until the operator / daily reset clears it.
                self._integrity._position_unconfirmed = False
                self._integrity._converge_flatten_at = 0.0
                self._integrity._reconcile_last_read = None
                self._integrity._reconcile_read_streak = 0
                if self._book.position_qty != 0:
                    self._book.set_qty_dir(0, "Flat")
                logger.info("部位已確認 flat → 解除 HALT（block_new_entry 維持至日切/人工）")
                return
            # Adopt broker truth into kernel accounting, then flatten exactly it.
            self._book.set_qty_dir(broker_qty, broker_dir)
            now = self._clock()
            self._integrity._converge_flatten_at = now + max(1, int(self._cfg.reconcile_fast_sec))
            action = "Sell" if broker_dir == "Long" else "Buy"
            qty = broker_qty
            ref_price = self._ticks.last_tick_price or self._book.entry_price
            ts = int(self._ticks.last_tick_exchange_ts or self._last_tick_exchange_ts_or_zero())
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
            self._integrity._kernel_converging = True
            try:
                if self._validate_order_signal(signal):
                    if not getattr(signal, "signal_id", ""):
                        signal.signal_id = self._make_signal_id(signal.exchange_ts or ts)
                    self._arm_pending(signal)
                    # Return to SETTLING so _settle_via_reconcile actively polls
                    # the broker for the convergence outcome instead of waiting on
                    # callbacks / a full pending_timeout_sec.
                    self._integrity._settling = True
                    self._integrity._settle_since = self._clock()
                    self._integrity._reconcile_last_read = None
                    self._integrity._reconcile_read_streak = 0
                else:
                    signal = None
            finally:
                self._integrity._kernel_converging = False
        if signal is not None:
            logger.warning(
                "HALT 收斂平倉 | %s %d 口 @ ref=%.1f（kernel 主動，唯一一張）",
                signal.action,
                signal.qty,
                signal.ref_price,
            )
            self._enqueue_order(signal)


    def _last_tick_exchange_ts_or_zero(self) -> int:
        dt = self._ticks._last_tick_exchange_dt
        return int(dt.timestamp()) if dt is not None else 0


    def _reconcile_pending_trade(self) -> bool:
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

        order_id = self._book.pending_order_id
        if not order_id:
            return self._reconcile_pending_via_broker_snapshot()

        for state, event in records:
            if not is_futures_deal(state):
                continue
            if str(event.get("trade_id", "")) != order_id:
                continue
            needs_sync = False
            with self.lock:
                if not self._book.is_pending or self._book.pending_order_id != order_id:
                    return True
                logger.info("order_deal_records 補查到成交")
                needs_sync = self._handle_futures_deal(event)
            if needs_sync:
                self.sync_positions()
            return True

        return self._reconcile_pending_via_broker_snapshot()


    def _reconcile_recent_cleared_deals(self) -> None:
        """Scan order_deal_records for fills on recently cleared pending orders."""
        if int(self._cfg.cleared_order_registry_sec) <= 0:
            return
        with self.lock:
            if self._book.is_pending:
                return
            self._prune_cleared_orders()
            if not self._integrity._recent_cleared_orders:
                return
            target_ids = {oid for oid, _, _ in self._integrity._recent_cleared_orders}

        try:
            records = self._call_api(self.api.order_deal_records)
        except Exception as e:
            logger.warning("order_deal_records 遲到成交掃描失敗: %s", e)
            return

        for state, event in records:
            if not is_futures_deal(state):
                continue
            oid = str(event.get("trade_id", ""))
            if oid not in target_ids:
                continue
            with self.lock:
                if self._book.is_pending:
                    return
                recent = self._lookup_recent_cleared_order(oid)
                if recent is None:
                    continue
                _oid, cleared_intent = recent
                qty = int(event.get("quantity", 0))
                price = float(event.get("price", 0))
                logger.warning(
                    "order_deal_records 發現已清 pending 的遲到成交 | order=%s intent=%s",
                    oid,
                    cleared_intent,
                )
                self._book.block_new_entry = True
                self._integrity._position_unconfirmed = True
                self._stage_critical_alert(
                    f"order_deal_records 遲到成交（已清 pending）| order={oid} "
                    f"intent={cleared_intent} qty={qty} @ {price} → 已 HALT；請人工核對"
                )
            self.sync_positions()
            self._flush_staged_critical_alert()
            return

