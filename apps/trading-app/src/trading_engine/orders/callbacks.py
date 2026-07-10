from __future__ import annotations

from trading_engine.core.audit.exec_audit import ExecAudit, format_exec_audit
from trading_engine.core.order_events import is_futures_deal, is_futures_order
from trading_engine.core.trading_state import PendingIntent
from trading_engine.orders.constants import _STOP_LOSS_REASONS
from trading_engine.orders.logutil import logger

class OrderCallbackMixin:
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
        expected = self._book.pending_order_id
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

        if not self._book.is_pending:
            return
        actual_id = self._event_order_id(msg)
        if not self._book.pending_order_id and actual_id:
            # Backfill order_id from first callback if it was empty at place time (common in sim/PendingSubmit).
            # Re-emit armed with real id (to satisfy SPEC §5.3 and audit completeness).
            self._book.pending_order_id = actual_id
            try:
                exec_audit = ExecAudit(
                    event_type="pending_armed",
                    ts=self._book.pending_exchange_ts or 0,
                    signal_id=self._book.pending_signal_id,
                    order_id=self._book.pending_order_id,
                    limit_price=self._book.pending_limit_price,
                    direction=self._book._pending_action or "",
                )
                logger.info("EXEC_AUDIT %s (backfilled)", format_exec_audit(exec_audit))
            except Exception:
                pass
        if not self._matches_pending_order(msg):
            logger.warning(
                "忽略非當前委託狀態回報 | expected=%s got=%s",
                self._book.pending_order_id,
                actual_id,
            )
            return

        if op_code and op_code != "00":
            logger.warning("委託失敗: %s", op.get("op_msg", op_code))
            self._clear_pending()
            return

        if status in ("Cancelled", "Failed", "Inactive") or op_type in ("Cancel", "Delete"):
            deal_qty = int(msg.get("status", {}).get("deal_quantity", 0) or 0)
            if deal_qty == 0:
                if self._book.pending_intent == PendingIntent.ENTRY:
                    tag = "intent_cancelled"
                    if (
                        self._integrity._pending_intent_cancel_exchange_dt is not None
                        and self._calendar.is_opening_session_window(
                            self._integrity._pending_intent_cancel_exchange_dt
                        )
                    ):
                        tag = "intent_cancelled_open_session"
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
                        and self._book.pending_exit_reason in _STOP_LOSS_REASONS
                        and self._book.position_qty > 0
                    ):
                        self._integrity._stop_market_flatten_request = True
                        logger.warning(
                            "停損 IOC 未成交 → 安排市價平倉（emergency）| reason=%s",
                            self._book.pending_exit_reason,
                        )
                # Emit EXEC cancel (Phase 2) - for non-happy cancel path coverage
                try:
                    exec_audit = ExecAudit(
                        event_type="pending_cancelled",
                        ts=int(self._book.pending_exchange_ts or 0),
                        signal_id=self._book.pending_signal_id,
                        tag=cancel_tag,
                        order_id=self._book.pending_order_id or "",
                    )
                    logger.info("EXEC_AUDIT %s", format_exec_audit(exec_audit))
                except Exception:
                    pass
                self._clear_pending(watch_late_fill=True)


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

        if not self._book.is_pending:
            recent = self._lookup_recent_cleared_order(order_id)
            if recent is not None:
                _oid, cleared_intent = recent
                logger.warning(
                    "遲到成交於已清 pending → HALT | order=%s intent=%s qty=%d @ %.1f",
                    order_id,
                    cleared_intent,
                    qty,
                    price,
                )
                self._book.block_new_entry = True
                self._integrity._position_unconfirmed = True
                self._stage_critical_alert(
                    f"遲到成交於已清 pending | order={order_id} intent={cleared_intent} "
                    f"qty={qty} @ {price} → 已 HALT；請人工核對券商部位"
                )
                return True
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
            self._book.block_new_entry = True
            self._integrity._position_unconfirmed = True
            self._stage_critical_alert(
                f"孤兒成交回報（無 pending）| order={order_id} qty={qty} @ {price} "
                "→ 已 HALT 並凍結所有新單；請人工核對券商部位"
            )
            return True  # trigger sync_positions in caller

        # Symmetric backfill for deal-first events (if pending_order_id was empty at place time)
        if not self._book.pending_order_id and order_id:
            self._book.pending_order_id = order_id
            logger.debug("Backfilled pending_order_id from deal event: %s", order_id)
            try:
                exec_audit = ExecAudit(
                    event_type="pending_armed",
                    ts=self._book.pending_exchange_ts or 0,
                    signal_id=self._book.pending_signal_id,
                    order_id=self._book.pending_order_id,
                    limit_price=self._book.pending_limit_price,
                    direction=self._book._pending_action or "",
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
                self._book.pending_order_id,
                order_id,
                qty,
                price,
            )
            # P0-5: a fill for a different order while we hold a pending is an
            # unattributed lot → position unconfirmed. Freeze entry AND exit, and
            # transition the in-flight pending into SETTLING so the settle loop
            # (and, via it, the convergence flatten) starts polling the broker
            # immediately instead of waiting out pending_timeout_sec.
            self._book.block_new_entry = True
            self._integrity._position_unconfirmed = True
            if not self._integrity._settling:
                self._integrity._settling = True
                self._integrity._settle_since = self._clock()
                self._integrity._reconcile_last_read = None
                self._integrity._reconcile_read_streak = 0
            self._stage_critical_alert(
                f"非當前委託成交回報 | expected={self._book.pending_order_id} got={order_id} "
                f"qty={qty} @ {price} → 已 HALT 並凍結所有新單；請人工核對券商部位"
            )
            return True  # trigger sync_positions in caller

        is_buy = self._is_buy_action(action)
        return self._apply_deal_fill(price, is_buy, deal_qty=qty)


