from __future__ import annotations

import datetime
from trading_engine.core.types import OrderSignal
from trading_engine.orders.logutil import logger

class StrategyHostMixin:
    def is_trading_session(self, dt: datetime.datetime) -> bool:
        cfg = self._cfg
        if self._calendar.is_trading_session(dt, cfg.session_start, cfg.session_end):
            return True
        if getattr(cfg, "night_enabled", False) and self._calendar.is_trading_session(
            dt, cfg.night_session_start, cfg.night_session_end
        ):
            return True
        return False


    def _active_session_windows(
        self, dt: datetime.datetime
    ) -> tuple[datetime.time, datetime.time, datetime.time, datetime.time] | None:
        from trading_engine.calendar.taifex import resolve_active_session

        cfg = self._cfg
        return resolve_active_session(
            dt,
            day_start=cfg.session_start,
            day_end=cfg.session_end,
            day_flatten=cfg.session_flatten_time,
            day_force=cfg.session_force_flatten_time,
            night_enabled=bool(getattr(cfg, "night_enabled", False)),
            night_start=getattr(cfg, "night_session_start", datetime.time(15, 0)),
            night_end=getattr(cfg, "night_session_end", datetime.time(5, 0)),
            night_flatten=getattr(
                cfg, "night_session_flatten_time", datetime.time(4, 50)
            ),
            night_force=getattr(
                cfg, "night_session_force_flatten_time", datetime.time(4, 55)
            ),
        )


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
        self._trading_date = trade_date


    def _reset_daily_state(self) -> None:
        """Reset day-scoped ops state only.

        Progressive capital book (``realized_pnl`` / ``equity_peak`` /
        ``capital_frozen``) is intentionally **not** cleared on day rollover
        or plain process restart (durable store reloads it). Clear only via
        ``clear_capital_risk()``, empty ``capital_state_path``, or deleting
        the capital JSON before start.
        """
        self._book.reset_day_ops()
        self._link.reset_day_ops()
        self._integrity.reset_day_ops()
        self._ticks.reset_day_counters()


    def _emit_daily_summary(self, trade_date: datetime.date) -> None:
        # Host day line: simple ledger snapshot (not legacy observability).
        logger.info(
            "DAILY_SUMMARY %s",
            {
                "date": trade_date.isoformat(),
                "daily_pnl": self.daily_pnl,
                "realized_pnl": self.realized_pnl,
                "equity_peak": self.equity_peak,
                "drawdown": self.current_drawdown,
                "capital_frozen": self.capital_frozen,
                "consecutive_loss": self.consecutive_loss,
            },
        )


    def process_strategy(self, ts: int, price: float, dt: datetime.datetime) -> OrderSignal | None:
        self._maybe_reset_daily_state(dt)
        market = self._market_snapshot(ts, price, dt)
        signal, effects = self.strategy.evaluate(
            market,
            self._position_snapshot(),
            self._risk_gate(ts, dt),
        )
        if effects.block_new_entry:
            self.block_new_entry = True
        return signal


    def reset_strategy_state(self) -> None:
        """Reset strategy episode state after fills / session events."""
        self.strategy.reset()


    def _stage_critical_alert(self, message: str) -> None:
        """Record a CRITICAL alert to be sent outside the lock.

        Must be called with ``self.lock`` held. The actual send happens via
        ``_flush_staged_critical_alert`` after the lock is released, so we never
        do network I/O on the callback hot path.

        Multiple stages in one critical section are joined (not overwritten).
        """
        if self._staged_critical_alert:
            self._staged_critical_alert = f"{self._staged_critical_alert}\n{message}"
        else:
            self._staged_critical_alert = message


    def _flush_staged_critical_alert(self) -> None:
        """Send any staged CRITICAL alert. Call OUTSIDE the lock."""
        with self.lock:
            message = self._staged_critical_alert
            self._staged_critical_alert = None
        if message:
            self._alerts.send(message, level="CRITICAL")


