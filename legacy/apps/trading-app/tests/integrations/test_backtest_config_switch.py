"""Tests for unified backtest CLI config → strategy loading (FT-022 Phase 3)."""

from __future__ import annotations

import datetime
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backtest.__main__ import main as backtest_main
from strategy_momentum_continuation import MomentumContinuationStrategy
from strategy_vwap_momentum import VWAPMomentumStrategy

REPO_ROOT = Path(__file__).resolve().parents[4]


class TestBacktestConfigSwitch(unittest.TestCase):
    def test_default_config_loads_vwap_momentum(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            dt = datetime.date(2026, 6, 22)
            from tests.storage.test_data_loader import ReplayTick, cache_path, save_ticks_csv

            save_ticks_csv(
                [ReplayTick(datetime.datetime(2026, 6, 22, 9), "18000", 1, 0)],
                cache_path(root, "TMFR1", dt),
            )
            with mock.patch("backtest.__main__.build_strategy_session") as build_session:
                build_session.return_value = mock.MagicMock()
                with mock.patch("backtest.__main__.BacktestEngine") as engine_cls:
                    rc = backtest_main(
                        [
                            "--dates",
                            "2026-06-22",
                            "--cache-dir",
                            str(root),
                        ]
                    )
            self.assertEqual(rc, 0)
            build_session.assert_called_once()
            cfg = build_session.call_args.args[0]
            self.assertEqual(cfg.strategy_name, "vwap_momentum")

    def test_mc_baseline_config_loads_momentum_continuation(self) -> None:
        mc_config = REPO_ROOT / "workspaces/mc-baseline/config/config.yaml"
        self.assertTrue(mc_config.is_file())

        prior_config = os.environ.get("CONFIG_PATH")
        try:
            with tempfile.TemporaryDirectory() as d:
                root = Path(d)
                dt = datetime.date(2026, 6, 22)
                from tests.storage.test_data_loader import ReplayTick, cache_path, save_ticks_csv

                save_ticks_csv(
                    [ReplayTick(datetime.datetime(2026, 6, 22, 9), "18000", 1, 0)],
                    cache_path(root, "TMFR1", dt),
                )
                with mock.patch("backtest.__main__.BacktestEngine") as engine_cls:
                    with mock.patch(
                        "integrations.engine_wiring.resolve_strategy_bootstrap",
                        return_value={},
                    ):
                        rc = backtest_main(
                            [
                                "--config",
                                str(mc_config),
                                "--dates",
                                "2026-06-22",
                                "--cache-dir",
                                str(root),
                            ]
                        )
                self.assertEqual(rc, 0)
                strategy = engine_cls.call_args.kwargs["strategy"]
                self.assertIsInstance(strategy, MomentumContinuationStrategy)
                runtime_cfg = engine_cls.call_args.kwargs["runtime_config"]
                self.assertEqual(runtime_cfg.strategy_name, "momentum_continuation")
        finally:
            if prior_config is None:
                os.environ.pop("CONFIG_PATH", None)
            else:
                os.environ["CONFIG_PATH"] = prior_config

    def test_backtest_engine_receives_injected_strategy(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            dt = datetime.date(2026, 6, 22)
            from tests.storage.test_data_loader import ReplayTick, cache_path, save_ticks_csv

            save_ticks_csv(
                [ReplayTick(datetime.datetime(2026, 6, 22, 9), "18000", 1, 0)],
                cache_path(root, "TMFR1", dt),
            )
            with mock.patch("backtest.__main__.BacktestEngine") as engine_cls:
                with mock.patch(
                    "integrations.engine_wiring.resolve_strategy_bootstrap",
                    return_value={},
                ):
                    rc = backtest_main(
                        [
                            "--dates",
                            "2026-06-22",
                            "--cache-dir",
                            str(root),
                        ]
                    )
            self.assertEqual(rc, 0)
            self.assertIsInstance(
                engine_cls.call_args.kwargs["strategy"],
                VWAPMomentumStrategy,
            )


if __name__ == "__main__":
    unittest.main()
