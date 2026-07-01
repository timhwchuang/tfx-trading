"""Tests for unified live CLI config → strategy loading (FT-022 Phase 4)."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

from live.__main__ import main as live_main
from strategy_gudt_route_a import GudtRouteAStrategy
from strategy_vwap_momentum import VWAPMomentumStrategy

REPO_ROOT = Path(__file__).resolve().parents[4]


class TestLiveConfigSwitch(unittest.TestCase):
    def test_default_config_loads_vwap_momentum(self) -> None:
        with mock.patch("shioaji.Shioaji"):
            with mock.patch("integrations.gudt_live_bootstrap.start_live_session") as start_live:
                with mock.patch("trading_engine.engine.TradingEngine") as engine_cls:
                    rc = live_main([])
        self.assertEqual(rc, 0)
        strategy = engine_cls.call_args.kwargs["strategy"]
        self.assertIsInstance(strategy, VWAPMomentumStrategy)
        start_live.assert_called_once()
        self.assertIsNone(start_live.call_args.kwargs.get("coordinator"))

    def test_gudt_baseline_config_loads_gudt_route_a_with_coordinator(self) -> None:
        gudt_config = REPO_ROOT / "workspaces/gudt-route-a-baseline/config/config.yaml"
        self.assertTrue(gudt_config.is_file())
        prior_config = os.environ.get("CONFIG_PATH")
        try:
            with mock.patch("shioaji.Shioaji"):
                with mock.patch("integrations.gudt_live_bootstrap.start_live_session") as start_live:
                    with mock.patch("trading_engine.engine.TradingEngine"):
                        with mock.patch(
                            "integrations.strategy_bootstrap._load_probe_rows",
                            return_value=[],
                        ):
                            rc = live_main(["--config", str(gudt_config)])
            self.assertEqual(rc, 0)
            coord = start_live.call_args.kwargs.get("coordinator")
            self.assertIsNotNone(coord)
            self.assertIsInstance(coord.strategy, GudtRouteAStrategy)
        finally:
            if prior_config is None:
                os.environ.pop("CONFIG_PATH", None)
            else:
                os.environ["CONFIG_PATH"] = prior_config


if __name__ == "__main__":
    unittest.main()
