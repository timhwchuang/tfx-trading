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
            # Phase 1: use accumulated filled for this pending (Book SSOT).
            self._book.apply_entry_fill(
                self.filled_qty,
                price,
                "Long" if is_buy else "Short",
                self.pending_exchange_ts,
            )
            fill_audit = FillAudit(
                intent="entry",
                direction=direction,
                fill_price=price,
                qty=self.position_qty,
                pnl_points=0.0,
                realized_pnl=self.realized_pnl,
                equity_peak=self.equity_peak,
                drawdown=self.current_drawdown,
                order_id=order_id,
                ts=self.pending_exchange_ts,
                signal_id=self.pending_signal_id,
            )
            logger.info("FILL_AUDIT %s", format_fill_audit(fill_audit))
            self.reset_strategy_state()
            self._consecutive_missed_entries = 0
            self._clear_pending()
            logger.info("進場完成 | %s %d口 @ %.1f", self.position_dir, self.position_qty, price)
            return False

        elif intent == PendingIntent.EXIT:
            total_pnl = self._pending_exit_pnl
            self._pending_exit_pnl = 0.0

            # Progressive capital book (cross-day); daily_pnl already updated per leg.
            self._capital.apply_realized_pnl(total_pnl)
            if total_pnl < 0:
                self.consecutive_loss += 1
            else:
                self.consecutive_loss = 0

            max_mdd = float(getattr(self._cfg, "max_mdd_points", 0) or 0)
            if self._capital.evaluate_mdd(max_mdd):
                logger.warning(
                    "累進 MDD 達上限 %.1f（drawdown=%.1f peak=%.1f equity=%.1f）"
                    " → capital_frozen；凍結新進場直到 clear_capital_risk()",
                    max_mdd,
                    self.current_drawdown,
                    self.equity_peak,
                    self.realized_pnl,
                )
                self._stage_critical_alert(
                    f"累進 MDD 觸頂 | drawdown={self.current_drawdown:.1f} "
                    f"limit={max_mdd:.1f} realized={self.realized_pnl:.1f} "
                    f"peak={self.equity_peak:.1f} → 已凍結新進場；請檢視策略後 clear_capital_risk()"
                )
            # Durable progressive book (restart-safe); position still broker-SSOT.
            # Persist under lock intentionally (durability > latency; max_qty=1).
            self._persist_capital_state()

            fill_audit = FillAudit(
                intent="exit",
                direction=direction,
                fill_price=price,
                qty=self.filled_qty,
                pnl_points=total_pnl,
                realized_pnl=self.realized_pnl,
                equity_peak=self.equity_peak,
                drawdown=self.current_drawdown,
                order_id=order_id,
                ts=self.pending_exchange_ts,
                signal_id=self.pending_signal_id,
                exit_reason=self.pending_exit_reason,
            )
            logger.info("FILL_AUDIT %s", format_fill_audit(fill_audit))

            self._book.mark_exit_time(self.pending_exchange_ts)
            self._clear_pending()
            if self.position_qty > 0:
                logger.warning(
                    "部分平倉 | 委託已結束，剩 %d 口（續由策略/對帳處理）| 本筆 PnL=%.1f",
                    self.position_qty,
                    total_pnl,
                )
                return True
            self._book.clear_position()
            logger.info(
                "平倉完成 | PnL=%.1f | 今日=%.1f | 累進=%.1f | DD=%.1f | 連虧=%d",
                total_pnl,
                self.daily_pnl,
                self.realized_pnl,
                self.current_drawdown,
                self.consecutive_loss,
            )
            self._post_exit_reconcile_until = self._clock() + max(
                0, int(self._cfg.post_exit_reconcile_sec)
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


