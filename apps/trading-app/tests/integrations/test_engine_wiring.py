"""Tests for integrations.engine_wiring."""

from __future__ import annotations

import datetime
import logging
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import MagicMock

from config import DEFAULT_CONFIG_PATH, load_config
from core.runtime_config import TradingAppRuntimeConfig, _to_engine_settings
from integrations.engine_wiring import (
    build_strategy_session,
    default_strategy,
    trading_app_engine_ports,
    validate_strategy_name,
)
from observability import DailyObservability
from strategy_gudt_route_a import GudtRouteAStrategy
from strategy_momentum_continuation import MomentumContinuationStrategy
from strategy_opening_range_breakout import OpeningRangeBreakoutStrategy
from strategy_vwap_momentum import VWAPMomentumStrategy
from strategy_vwap_stretch_fade import VwapStretchFadeStrategy
from trading_engine.logging_setup import shutdown_async_logging

REPO_ROOT = Path(__file__).resolve().parents[4]


class TestEngineWiring(unittest.TestCase):
    def tearDown(self) -> None:
        shutdown_async_logging()

    def test_shared_obs_between_telemetry_and_strategy(self):
        api = MagicMock()
        ports = trading_app_engine_ports(api=api, use_mock_adapter=True)
        strategy = default_strategy(ports["runtime_config"], ports["obs"])

        self.assertIs(strategy.obs, ports["obs"])
        self.assertIs(ports["telemetry"].underlying, ports["obs"])

    def test_external_obs_reused_by_ports(self):
        api = MagicMock()
        obs = DailyObservability()
        ports = trading_app_engine_ports(api=api, use_mock_adapter=True, obs=obs)
        self.assertIs(ports["obs"], obs)
        self.assertIs(ports["telemetry"].underlying, obs)

    def test_log_file_env_writes_audit_lines(self):
        import integrations.engine_wiring as wiring

        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "uat.log"
            wiring._logging_configured = False
            with mock.patch.object(wiring, "LOG_FILE", str(log_path)):
                with mock.patch.object(wiring, "LOG_LEVEL", "INFO"):
                    api = MagicMock()
                    wiring.trading_app_engine_ports(api=api, use_mock_adapter=True)
                    logging.getLogger("trading_engine").info("SIGNAL_AUDIT smoke")
                    shutdown_async_logging()
                    self.assertTrue(log_path.exists())
                    self.assertIn("SIGNAL_AUDIT", log_path.read_text(encoding="utf-8"))

    def test_validate_strategy_name_unknown_raises(self):
        with self.assertRaises(LookupError):
            validate_strategy_name("not_a_real_strategy")

    def test_load_config_strategy_name_default(self):
        app_settings = load_config(DEFAULT_CONFIG_PATH)
        self.assertEqual(app_settings.strategy_name, "vwap_momentum")

    def test_load_config_workspace_strategy_names(self):
        cases = (
            ("mc-baseline", "momentum_continuation"),
            ("vsf-baseline", "vwap_stretch_fade"),
            ("orb-baseline", "opening_range_breakout"),
            ("gudt-route-a-baseline", "gudt_route_a"),
        )
        for ws, expected in cases:
            with self.subTest(workspace=ws):
                path = REPO_ROOT / "workspaces" / ws / "config" / "config.yaml"
                self.assertTrue(path.is_file(), msg=str(path))
                app_settings = load_config(path)
                self.assertEqual(app_settings.strategy_name, expected)

    def test_build_strategy_session_smoke_all_names(self):
        obs = DailyObservability()
        cache_dir = REPO_ROOT / "tick_cache"
        dates = [datetime.date(2026, 1, 2)]
        cases = (
            ("vwap_momentum", VWAPMomentumStrategy),
            ("momentum_continuation", MomentumContinuationStrategy),
            ("vwap_stretch_fade", VwapStretchFadeStrategy),
            ("opening_range_breakout", OpeningRangeBreakoutStrategy),
            ("gudt_route_a", GudtRouteAStrategy),
        )
        for ws_suffix, expected_cls in cases:
            with self.subTest(strategy=ws_suffix):
                if ws_suffix == "vwap_momentum":
                    app_settings = load_config(DEFAULT_CONFIG_PATH)
                else:
                    ws_map = {
                        "momentum_continuation": "mc-baseline",
                        "vwap_stretch_fade": "vsf-baseline",
                        "opening_range_breakout": "orb-baseline",
                        "gudt_route_a": "gudt-route-a-baseline",
                    }
                    path = (
                        REPO_ROOT
                        / "workspaces"
                        / ws_map[ws_suffix]
                        / "config"
                        / "config.yaml"
                    )
                    app_settings = load_config(path)
                cfg = TradingAppRuntimeConfig(_to_engine_settings(app_settings))
                strategy = build_strategy_session(
                    cfg,
                    obs,
                    code=app_settings.product_code,
                    dates=dates,
                    cache_dir=cache_dir,
                )
                self.assertIsInstance(strategy, expected_cls)
                self.assertEqual(cfg.strategy_name, ws_suffix if ws_suffix != "vwap_momentum" else "vwap_momentum")


if __name__ == "__main__":
    unittest.main()