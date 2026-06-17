"""Single-threaded tick replay engine for backtesting."""

from __future__ import annotations

import datetime
from typing import Any

from trading_engine.adapters.mock import MockOrderAdapter
from trading_engine.calendar.taifex import is_trading_session
from trading_engine.core.runtime_config import RuntimeConfig
from trading_engine.core.side_effect_ports import (
    NullAlertPort,
    NullArchivePort,
    NullTelemetryPort,
    NullTrendRefreshPort,
)
from trading_engine.core.strategy import Strategy
from trading_engine.engine import TradingEngine

from trading_backtest.loader import DEFAULT_CACHE_DIR
from trading_backtest.mock_broker import MockBroker


class VirtualClock:
    def __init__(self) -> None:
        self._now = 0.0

    def set(self, epoch_sec: float) -> None:
        self._now = epoch_sec

    def __call__(self) -> float:
        return self._now


def _noop_maybe_refresh_atr(_ts: int) -> None:
    return


def _pre_tick_refresh_atr(host: TradingEngine, ts: int, atr_refresh_sec: int) -> None:
    if ts - host.last_atr_refresh >= atr_refresh_sec:
        host.last_atr_refresh = ts
        host.refresh_atr()


class BacktestEngine:
    def __init__(
        self,
        code: str,
        dates: list[datetime.date],
        strategy: Strategy,
        *,
        cache_dir=DEFAULT_CACHE_DIR,
        runtime_config: RuntimeConfig,
        broker: MockBroker | None = None,
        clock: VirtualClock | None = None,
        telemetry: Any | None = None,
        trend_refresh: Any | None = None,
        alerts: Any | None = None,
        archive: Any | None = None,
        order_adapter: Any | None = None,
    ) -> None:
        self.clock = clock or VirtualClock()
        cfg = runtime_config
        self.broker = broker or MockBroker(
            clock=self.clock,
            cache_dir=cache_dir,
            BLOWOUT_VOL=cfg.momentum_vol_1s,
            session_force_flatten_time=cfg.session_force_flatten_time,
        )
        adapter = order_adapter or MockOrderAdapter(self.broker)
        self.host = TradingEngine(
            api=self.broker,
            clock=self.clock,
            strategy=strategy,
            runtime_config=cfg,
            order_adapter=adapter,
            telemetry=telemetry or NullTelemetryPort(),
            trend_refresh=trend_refresh or NullTrendRefreshPort(),
            alerts=alerts or NullAlertPort(),
            archive=archive or NullArchivePort(),
        )
        self.host.contract = self.broker.resolve_contract(code)
        self.host._maybe_refresh_atr = _noop_maybe_refresh_atr
        self.host._order_sync_mode = True
        self.code = code
        self.dates = dates
        self.cache_dir = cache_dir
        self._cfg = cfg

    def run(self) -> None:
        from trading_backtest.loader import iter_replay_ticks

        for tick in iter_replay_ticks(self.code, self.dates, cache_dir=self.cache_dir):
            self.clock.set(tick.datetime.timestamp())
            self.broker.current_dt = tick.datetime
            self.broker.process_matching_queue(tick, self.host)
            self.host._check_pending_timeout()
            if is_trading_session(
                tick.datetime,
                self._cfg.session_start,
                self._cfg.session_end,
            ):
                _pre_tick_refresh_atr(
                    self.host,
                    int(tick.datetime.timestamp()),
                    self._cfg.atr_refresh_sec,
                )
                self.host.on_tick(tick)
        if self.host._last_tick_exchange_dt is not None:
            self.host._emit_daily_summary(self.host._last_tick_exchange_dt.date())


__all__ = ["BacktestEngine", "VirtualClock"]
