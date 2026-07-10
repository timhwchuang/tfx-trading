"""Tick arrival bookkeeping + no-tick / clock-skew watchdogs (Phase G3 service).

State lives on ``TickState`` (``_ticks``).
"""

from __future__ import annotations

import datetime
from typing import Any, Protocol

from trading_engine.core.host_service import HostBoundService
from trading_engine.logging_setup import get_logger

logger = get_logger()


class TickWatchdogHost(Protocol):
    """Surface used by tick arrival / no-tick watchdog."""

    lock: Any
    _cfg: Any
    _ticks: Any
    _link: Any
    _alerts: Any
    _resubscribe_ticks: Any
    _clock: Any

    def _mark_disconnected(self, **kwargs) -> bool: ...


class _TickWatchdogMethods:
    def _record_tick_arrival_locked(
        self, ts: int, exchange_dt: datetime.datetime, tick_type: int
    ) -> None:
        """Must be called with self.lock held."""
        self._ticks.last_tick_exchange_ts = ts
        self._ticks._last_tick_wall_time = self._clock()
        self._ticks._last_tick_exchange_dt = exchange_dt
        bucket = tick_type if tick_type in self._ticks._tick_type_counts else 0
        self._ticks._tick_type_counts[bucket] = self._ticks._tick_type_counts.get(bucket, 0) + 1
        self._ticks._no_tick_resubscribe_streak = 0
        self._maybe_warn_clock_skew(ts)

    def _record_tick_arrival(
        self, ts: int, exchange_dt: datetime.datetime, tick_type: int
    ) -> None:
        self._ticks.last_tick_exchange_ts = ts
        self._ticks._last_tick_wall_time = self._clock()
        self._ticks._last_tick_exchange_dt = exchange_dt
        bucket = tick_type if tick_type in self._ticks._tick_type_counts else 0
        self._ticks._tick_type_counts[bucket] = self._ticks._tick_type_counts.get(bucket, 0) + 1
        self._ticks._no_tick_resubscribe_streak = 0
        self._maybe_warn_clock_skew(ts)

    def _maybe_warn_clock_skew(self, exchange_ts: int) -> None:
        skew = abs(exchange_ts - self._clock())
        if skew <= self._cfg.clock_skew_warn_sec:
            return
        now = self._clock()
        if now - self._ticks._last_clock_skew_warn_wall < 300:
            return
        self._ticks._last_clock_skew_warn_wall = now
        logger.warning(
            "系統鐘與交易所時間偏差 %.1fs | 策略決策仍以 tick 時間為準",
            skew,
        )

    def _maybe_log_tick_type_summary(self) -> None:
        """P1-3: 每 30 分鐘輸出 tick_type 分布（UAT 觀測）。"""
        if self._ticks._last_tick_exchange_dt is None:
            return
        if not self.is_trading_session(self._ticks._last_tick_exchange_dt):
            return
        now = self._clock()
        if now - self._ticks._last_tick_type_log_wall < 1800:
            return
        total = sum(self._ticks._tick_type_counts.values())
        if total == 0:
            return
        self._ticks._last_tick_type_log_wall = now
        inferred_total = sum(self._ticks._tick_type_inferred_counts.values())
        logger.info(
            "tick_type 分布 | type0=%d type1=%d type2=%d total=%d "
            "| type0_pct=%.1f%% | inferred_buy=%d inferred_sell=%d inferred_total=%d",
            self._ticks._tick_type_counts.get(0, 0),
            self._ticks._tick_type_counts.get(1, 0),
            self._ticks._tick_type_counts.get(2, 0),
            total,
            100.0 * self._ticks._tick_type_counts.get(0, 0) / total,
            self._ticks._tick_type_inferred_counts.get(1, 0),
            self._ticks._tick_type_inferred_counts.get(2, 0),
            inferred_total,
        )

    def _check_no_tick_watchdog(self) -> None:
        """P4-8: 交易時段內長時間無 tick → 告警並嘗試重訂閱。"""
        if not self._link._api_connected or self.contract is None:
            return
        if self._ticks._last_tick_exchange_dt is None or self._ticks._last_tick_wall_time <= 0:
            return
        if not self.is_trading_session(self._ticks._last_tick_exchange_dt):
            return
        silent = self._clock() - self._ticks._last_tick_wall_time
        if silent < self._cfg.no_tick_timeout_sec:
            return
        now = self._clock()
        if now - self._ticks._last_no_tick_resubscribe_wall < 60:
            return
        self._ticks._last_no_tick_resubscribe_wall = now
        self._ticks._no_tick_resubscribe_streak += 1
        escalate_after = self._cfg.no_tick_resubscribe_escalate_after
        logger.warning(
            "No-tick 看門狗 | %.0fs 無 tick，嘗試重訂閱 %s（streak=%d/%d）",
            silent,
            self.contract.code,
            self._ticks._no_tick_resubscribe_streak,
            escalate_after,
        )
        try:
            if self._resubscribe_ticks is None:
                logger.warning("No-tick 看門狗 | 未設定 tick 重訂閱 hook，略過")
                return
            self._resubscribe_ticks()
            logger.info("No-tick 看門狗 | 重訂閱已送出")
        except Exception as e:
            logger.warning("No-tick 看門狗 | 重訂閱失敗: %s", e)
            self._ticks._no_tick_resubscribe_streak = 0
            self._mark_disconnected()
            return

        with self.lock:
            if not self._link._api_connected:
                return
            if self._ticks._no_tick_resubscribe_streak < escalate_after:
                return
            silent_after = self._clock() - self._ticks._last_tick_wall_time
            if silent_after < self._cfg.no_tick_timeout_sec:
                return
            streak = self._ticks._no_tick_resubscribe_streak
            self._ticks._no_tick_resubscribe_streak = 0
            connected_gen = self._link._connected_reconnect_generation

        if not self._mark_disconnected(
            require_silent_sec=self._cfg.no_tick_timeout_sec,
            max_connected_reconnect_generation=connected_gen,
            require_was_connected=True,
        ):
            logger.info("No-tick 升級已取消：tick 或 reconnect 已恢復")
            return

        msg = (
            f"No-tick 看門狗 | 連續 {streak} 次重訂閱仍無 tick → "
            "升級 session relogin"
        )
        logger.warning(msg)
        self._alerts.send(msg, level="CRITICAL")


class TickWatchdogService(HostBoundService):
    def __init__(self, host: TickWatchdogHost) -> None:
        super().__init__(host, _TickWatchdogMethods)


TickWatchdogMixin = TickWatchdogService

__all__ = ["TickWatchdogHost", "TickWatchdogService", "TickWatchdogMixin"]
