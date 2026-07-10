from __future__ import annotations

from trading_engine.core.audit.exec_audit import ExecAudit, format_exec_audit
from trading_engine.core.audit.signal_audit import format_signal_audit
from trading_engine.core.risk import compute_limit_price
from trading_engine.core.trading_state import PendingIntent
from trading_engine.core.types import OrderSignal
from trading_engine.orders.logutil import logger

class OrderFlightMixin:
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
        if self._book.is_pending:
            logger.warning(
                "拒絕 OrderSignal: 已有 pending (intent=%s)",
                self._book.pending_intent,
            )
            return False
        # P0-5: while the previous order's outcome is UNKNOWN (settling) or the
        # broker position is unconfirmed (HALT), freeze BOTH entry and exit.
        # The strategy must never re-issue here; the kernel owns convergence via
        # _settle_via_reconcile + _maybe_converge_flatten. ``_kernel_converging``
        # lets kernel-owned convergence flatten bypass this freeze.
        if (
            self._integrity._settling or self._integrity._position_unconfirmed
        ) and not self._integrity._kernel_converging:
            logger.warning(
                "拒絕 OrderSignal: 部位未確認/結算中 (settling=%s unconfirmed=%s intent=%s)",
                self._integrity._settling,
                self._integrity._position_unconfirmed,
                signal.intent,
            )
            return False
        # Kernel-owned market flatten is pending (stop-loss miss / L1 cancel).
        # Block strategy re-arm until _maybe_emergency_market_flatten runs.
        if (
            self._integrity._stop_market_flatten_request
            and not self._integrity._kernel_converging
        ):
            logger.warning(
                "拒絕 OrderSignal: kernel 市價平倉待送出 (intent=%s)",
                signal.intent,
            )
            return False
        if signal.intent == "entry":
            if self.entry_blocked:
                logger.warning(
                    "拒絕 entry OrderSignal: entry_blocked "
                    "(ops_block=%s capital_frozen=%s mdd_gate=%s)",
                    self._book.block_new_entry,
                    self.capital_frozen,
                    self._capital_gate_active(),
                )
                return False
            if self._book.position_qty > 0:
                logger.warning(
                    "拒絕 entry OrderSignal: 已有持倉 qty=%s",
                    self._book.position_qty,
                )
                return False
            # P0-4: hard position ceiling. ``is_pending`` is already rejected
            # above, so pending_qty is 0 here; guard held + requested qty.
            ceiling = self._cfg.max_position_qty
            if ceiling > 0 and self._book.position_qty + signal.qty > ceiling:
                logger.warning(
                    "拒絕 entry OrderSignal: 超過部位上限 | 持倉=%d + 委託=%d > max=%d",
                    self._book.position_qty,
                    signal.qty,
                    ceiling,
                )
                return False
        if signal.intent == "exit" and self._book.position_qty <= 0:
            logger.warning("拒絕 exit OrderSignal: 無持倉")
            return False
        return True


    def _arm_pending(self, signal: OrderSignal) -> None:
        """P2-2: lock 內同步設 pending，堵住雙 tick 雙單。"""
        self._book.is_pending = True
        # Bump generation so any in-flight Layer-2 query for a prior pending is stale.
        self._integrity._pending_generation += 1
        self._book.pending_intent = signal.intent
        self._book.pending_exchange_ts = signal.exchange_ts
        self._book.pending_qty = signal.qty
        self._book.pending_signal_price = signal.ref_price
        self._book.pending_market = bool(getattr(signal, "market", False))
        self._book.pending_ioc_slippage = (
            signal.slippage_points
            if signal.slippage_points is not None
            else self._cfg.ioc_slippage_points
        )
        self._book._pending_action = signal.action
        is_buy = signal.action == "Buy"
        if self._book.pending_market:
            # Market order: no limit gate. Track 0 for audit; fill is whatever the
            # venue gives (guaranteed fill is the point).
            self._book.pending_ioc_slippage = 0
            self._book.pending_limit_price = 0.0
        else:
            self._book.pending_limit_price = compute_limit_price(
                signal.ref_price,
                is_buy=is_buy,
                ioc_slippage=self._book.pending_ioc_slippage,
            )
        self._book.pending_exit_reason = (
            signal.audit.reason
            if signal.audit is not None and signal.intent == PendingIntent.EXIT
            else ""
        )
        self._book.pending_episode_id = ""
        self._book.pending_signal_id = ""
        if signal.signal_id:
            self._book.pending_signal_id = signal.signal_id
        if signal.audit is not None:
            self._book.pending_episode_id = getattr(signal.audit, "episode_id", "") or ""
            if not self._book.pending_signal_id:
                self._book.pending_signal_id = getattr(signal.audit, "signal_id", "") or ""
        if signal.intent == PendingIntent.EXIT:
            self._book.exit_pending = True

        # Set pending_since early (at arm time) to avoid premature timeout window
        # when place_order takes time or order_id population is delayed.
        # Always use internal _clock() (wall time) for consistent comparison in _check_pending_timeout.
        self._book.pending_since = self._clock()

        # Note: pending_armed EXEC is emitted from place_order after order_id is known (to satisfy SPEC order_id MUST).
        # See OrderPlaceMixin.place_order in orders/place.py.

        # Defensive guard (logs only). Permanent invariant check.
        try:
            from trading_engine.core.trading_state import validate_pending_consistency

            validate_pending_consistency(
                is_pending=self._book.is_pending,
                pending_intent=self._book.pending_intent,
                exit_pending=self._book.exit_pending,
                position_qty=self._book.position_qty,
                position_dir=self._book.position_dir,
                logger=logger,
            )
        except Exception:
            pass  # never let guard break hot path


    @staticmethod
    def _log_signal_audit(signal: OrderSignal) -> None:
        if signal.audit is None:
            return
        logger.info("SIGNAL_AUDIT %s", format_signal_audit(signal.audit))


    def _still_own_pending(self, trade=None) -> bool:
        """須在 lock 內呼叫：確認 pending 仍屬於此 trade。
        只使用 is_pending，不讀 live trade.order.id（避免 bg thread borrow 風險）。
        pending_order_id 空時仍視為 owned（id 尚未回填），讓 timeout 能清掉卡住的 pending。
        """
        if not self._book.is_pending:
            return False
        # trade param kept for backward compat with direct callers (tests/reconnect);
        # we intentionally ignore it here to avoid any live object access from bg threads.
        return True


    def _check_pending_timeout(self):
        """P0-5: a pending timeout means the order outcome is UNKNOWN, not FAILED.

        We do NOT clear pending and let the strategy re-issue (that is what caused
        cascading duplicate orders + >1 lot). Instead we try a fast reconcile and,
        if still unresolved, transition into SETTLING: keep ``pending_order_id`` so
        a late fill still attributes, freeze all new orders, and let
        ``_settle_via_reconcile`` converge against the broker (the source of truth).
        """
        with self.lock:
            if not self._book.is_pending:
                return
            if self._integrity._settling:
                # Past the callback-wait window already; the settle loop owns it.
                return
            if self._clock() - self._book.pending_since < self._cfg.pending_timeout_sec:
                return

        # First attempt: fast reconcile (deal records / broker snapshot).
        resolved = self._reconcile_pending_trade()

        intent = None
        entered_settling = False
        with self.lock:
            if not self._book.is_pending:
                return
            if resolved:
                return
            if not self._still_own_pending():
                return
            if not self._integrity._settling:
                self._integrity._settling = True
                self._integrity._settle_since = self._clock()
                self._integrity._reconcile_last_read = None
                self._integrity._reconcile_read_streak = 0
                entered_settling = True
                intent = self._book.pending_intent
                # Phase 2 audit: timeout now means "switch to broker reconcile".
                try:
                    exec_audit = ExecAudit(
                        event_type="pending_timeout",
                        ts=int(self._book.pending_exchange_ts or 0),
                        signal_id=self._book.pending_signal_id,
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


