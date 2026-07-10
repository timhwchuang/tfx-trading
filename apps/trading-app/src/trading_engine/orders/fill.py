from __future__ import annotations

from trading_engine.core.audit.fill_audit import FillAudit, format_fill_audit
from trading_engine.core.trading_state import PendingIntent
from trading_engine.orders.logutil import logger

class OrderFillMixin:
    def _apply_exit_deal_leg(self, price: float, deal_qty: int) -> float:
        """Apply one exit deal leg via Book mutation API."""
        _leg_qty, leg_pnl = self._book.apply_exit_leg(price, deal_qty)
        return leg_pnl


    def _apply_deal_fill(self, price: float, is_buy: bool, deal_qty: int = 1) -> bool:
        """套用成交。回傳 True 表示須在 lock 外呼叫 sync_positions()。"""
        expected = self._book.pending_qty if self._book.pending_qty > 0 else 1
        if deal_qty > expected:
            logger.warning(
                "成交口數超過 pending | deal=%d expected=%d order=%s",
                deal_qty,
                expected,
                self._book.pending_order_id,
            )
        self._book.filled_qty = self._book.filled_qty + deal_qty
        if self._book.filled_qty > expected:
            logger.warning(
                "累計成交超過 pending | filled=%d expected=%d order=%s",
                self._book.filled_qty,
                expected,
                self._book.pending_order_id,
            )

        # Exit IOC: book PnL and reduce held qty on every deal leg, not only when
        # the order is fully filled (multi-lot partial fills use different prices).
        if self._book.pending_intent == PendingIntent.EXIT and self.has_position:
            self._apply_exit_deal_leg(price, deal_qty)

        if self._book.filled_qty < expected:
            logger.info(
                "部分成交進度 | intent=%s %d/%d (deal=%d) order=%s | pending 持續（IOC 未結束不全解鎖）",
                self._book.pending_intent,
                self._book.filled_qty,
                expected,
                deal_qty,
                self._book.pending_order_id,
            )
            return False  # keep pending for more fills or cancel

        intent = self._book.pending_intent
        order_id = self._book.pending_order_id or ""
        direction = "Buy" if is_buy else "Sell"
        if intent == PendingIntent.ENTRY:
            if self.has_position:
                logger.warning(
                    "STATE_GUARD unexpected entry fill while positioned | qty=%d dir=%s order=%s",
                    self._book.position_qty,
                    self._book.position_dir,
                    order_id,
                )
            # Phase 1: use accumulated filled for this pending (Book SSOT).
            self._book.apply_entry_fill(
                self._book.filled_qty,
                price,
                "Long" if is_buy else "Short",
                self._book.pending_exchange_ts,
            )
            fill_audit = FillAudit(
                intent="entry",
                direction=direction,
                fill_price=price,
                qty=self._book.position_qty,
                pnl_points=0.0,
                realized_pnl=self.realized_pnl,
                equity_peak=self.equity_peak,
                drawdown=self.current_drawdown,
                order_id=order_id,
                ts=self._book.pending_exchange_ts,
                signal_id=self._book.pending_signal_id,
            )
            logger.info("FILL_AUDIT %s", format_fill_audit(fill_audit))
            self.reset_strategy_state()
            self._integrity._consecutive_missed_entries = 0
            self._clear_pending()
            logger.info("進場完成 | %s %d口 @ %.1f", self._book.position_dir, self._book.position_qty, price)
            return False

        elif intent == PendingIntent.EXIT:
            total_pnl = self._book._pending_exit_pnl
            self._book._pending_exit_pnl = 0.0

            # Progressive capital book (cross-day); daily_pnl already updated per leg.
            if total_pnl < 0:
                self._book.consecutive_loss += 1
            else:
                self._book.consecutive_loss = 0

            # Host capital policy: apply PnL + MDD + persist (not inlined in engine).
            cap_evt = self._capital_svc.on_exit_fill(total_pnl)
            if cap_evt.freeze_alert:
                self._stage_critical_alert(cap_evt.freeze_alert)
            if cap_evt.persist_alert:
                self._stage_critical_alert(cap_evt.persist_alert)

            fill_audit = FillAudit(
                intent="exit",
                direction=direction,
                fill_price=price,
                qty=self._book.filled_qty,
                pnl_points=total_pnl,
                realized_pnl=self.realized_pnl,
                equity_peak=self.equity_peak,
                drawdown=self.current_drawdown,
                order_id=order_id,
                ts=self._book.pending_exchange_ts,
                signal_id=self._book.pending_signal_id,
                exit_reason=self._book.pending_exit_reason,
            )
            logger.info("FILL_AUDIT %s", format_fill_audit(fill_audit))

            self._book.mark_exit_time(self._book.pending_exchange_ts)
            self._clear_pending()
            if self._book.position_qty > 0:
                logger.warning(
                    "部分平倉 | 委託已結束，剩 %d 口（續由策略/對帳處理）| 本筆 PnL=%.1f",
                    self._book.position_qty,
                    total_pnl,
                )
                return True
            self._book.clear_position()
            logger.info(
                "平倉完成 | PnL=%.1f | 今日=%.1f | 累進=%.1f | DD=%.1f | 連虧=%d",
                total_pnl,
                self._book.daily_pnl,
                self.realized_pnl,
                self.current_drawdown,
                self._book.consecutive_loss,
            )
            self._integrity._post_exit_reconcile_until = self._clock() + max(
                0, int(self._cfg.post_exit_reconcile_sec)
            )
            return True  # re-sync to confirm broker is truly flat

        if intent == PendingIntent.EXIT and not self.has_position and self._book._pending_exit_pnl == 0:
            logger.warning(
                "STATE_GUARD unexpected exit fill while flat | order=%s",
                order_id,
            )

        # Light state guard after fill (defensive logging)
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
            pass

        return False


    @staticmethod
    def _is_buy_action(action) -> bool:
        if action == "Buy":
            return True
        name = getattr(action, "name", None)
        return name == "Buy"


