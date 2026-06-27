"""Tests for backtest.engine BacktestEngine wrapper."""

from __future__ import annotations

import datetime
import unittest

from backtest.engine import BacktestEngine
from core.runtime_config import default_runtime_config
from integrations.engine_wiring import load_named_strategy
from observability import DailyObservability
from trading_engine.logging_setup import shutdown_async_logging


class TestBacktestEngineObs(unittest.TestCase):
    def tearDown(self) -> None:
        shutdown_async_logging()

    def test_injected_obs_shared_with_telemetry(self) -> None:
        obs = DailyObservability()
        cfg = default_runtime_config()
        strategy = load_named_strategy("momentum_continuation", cfg, obs)
        engine = BacktestEngine(
            "TMFR1",
            [datetime.date(2026, 4, 1)],
            strategy=strategy,
            runtime_config=cfg,
            obs=obs,
        )
        self.assertIs(strategy.obs, obs)
        self.assertIs(engine._core.host._telemetry.underlying, obs)


if __name__ == "__main__":
    unittest.main()
