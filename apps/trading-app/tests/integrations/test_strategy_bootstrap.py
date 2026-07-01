"""Tests for integrations.strategy_bootstrap (FT-022 Phase 2)."""

from __future__ import annotations

import datetime
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from config import load_config
from core.runtime_config import TradingAppRuntimeConfig, _to_engine_settings
from integrations.engine_wiring import build_strategy_session
from integrations.strategy_bootstrap import (
    bootstrap_gudt_route_a,
    resolve_strategy_bootstrap,
    write_day_plans_json,
)
from observability import DailyObservability
from reporting.gudt_wash_probe import DayWashContext
from strategy_gudt_route_a.types import DayReplayPlan, TradeEvent

REPO_ROOT = Path(__file__).resolve().parents[4]


class TestStrategyBootstrap(unittest.TestCase):
    def _gudt_cfg(self) -> TradingAppRuntimeConfig:
        path = REPO_ROOT / "workspaces/gudt-route-a-baseline/config/config.yaml"
        return TradingAppRuntimeConfig(_to_engine_settings(load_config(path)))

    def test_live_mode_returns_empty_plans(self) -> None:
        cfg = self._gudt_cfg()
        out = bootstrap_gudt_route_a(
            cfg,
            code="TMFR1",
            dates=[datetime.date(2026, 6, 3)],
            cache_dir=REPO_ROOT / "tick_cache",
            mode="live",
        )
        self.assertEqual(out["day_plans"], {})

    def test_resolve_strategy_bootstrap_non_gudt_empty(self) -> None:
        cfg = TradingAppRuntimeConfig(_to_engine_settings(load_config()))
        out = resolve_strategy_bootstrap(
            "vwap_momentum",
            cfg,
            code="TMFR1",
            dates=[datetime.date(2026, 1, 2)],
            cache_dir=REPO_ROOT / "tick_cache",
        )
        self.assertEqual(out, {})

    @mock.patch("integrations.strategy_bootstrap.build_replay_plans_for_range")
    @mock.patch("integrations.strategy_bootstrap.load_probe_contexts")
    @mock.patch("integrations.strategy_bootstrap._load_probe_rows")
    def test_backtest_bootstrap_non_empty_plans(
        self,
        mock_rows: mock.MagicMock,
        mock_ctx: mock.MagicMock,
        mock_plans: mock.MagicMock,
    ) -> None:
        mock_rows.return_value = [{"day": "2026-06-03", "path": "p0"}]
        mock_ctx.return_value = {
            "2026-06-03": DayWashContext(
                day=datetime.date(2026, 6, 3),
                atr=30.0,
                drive_high=100.0,
                drive_low=90.0,
                gap_pts=8.0,
                open_0845=108.0,
                prior_close=100.0,
                ticks=[],
            )
        }
        mock_plans.return_value = {
            "2026-06-03": DayReplayPlan(
                day="2026-06-03",
                path="p0+sealed",
                events=[
                    TradeEvent(
                        ts=1_000,
                        action="Buy",
                        price=100.0,
                        leg="long_entry",
                        reason="p0+sealed",
                    )
                ],
                meta={"net": 10.0},
                skipped=False,
            )
        }
        cfg = self._gudt_cfg()
        out = bootstrap_gudt_route_a(
            cfg,
            code="TMFR1",
            dates=[datetime.date(2026, 6, 3)],
            cache_dir=REPO_ROOT / "tick_cache",
            mode="backtest",
            quiet_gudt_skip=True,
        )
        self.assertIn("2026-06-03", out["day_plans"])
        self.assertFalse(out["day_plans"]["2026-06-03"].skipped)

    @mock.patch("integrations.strategy_bootstrap.build_replay_plans_for_range")
    @mock.patch("integrations.strategy_bootstrap.load_probe_contexts")
    @mock.patch("integrations.strategy_bootstrap._load_probe_rows")
    def test_skip_day_logs_reason(
        self,
        mock_rows: mock.MagicMock,
        mock_ctx: mock.MagicMock,
        mock_plans: mock.MagicMock,
    ) -> None:
        mock_rows.return_value = [{"day": "2026-06-04", "path": "p0"}]
        mock_ctx.return_value = {}
        mock_plans.return_value = {
            "2026-06-04": DayReplayPlan(day="2026-06-04", path="skip", skipped=True),
        }
        cfg = self._gudt_cfg()
        with self.assertLogs("integrations.strategy_bootstrap", level="INFO") as captured:
            out = bootstrap_gudt_route_a(
                cfg,
                code="TMFR1",
                dates=[datetime.date(2026, 6, 4)],
                cache_dir=REPO_ROOT / "tick_cache",
                mode="backtest",
                quiet_gudt_skip=False,
            )
        self.assertEqual(
            out["day_plans"]["2026-06-04"].meta.get("skip_reason"),
            "probe_error",
        )
        joined = "\n".join(captured.output)
        self.assertIn("gudt_skip", joined)
        self.assertIn("skip_reason=probe_error", joined)

    @mock.patch("integrations.strategy_bootstrap.build_replay_plans_for_range")
    @mock.patch("integrations.strategy_bootstrap.load_probe_contexts")
    @mock.patch("integrations.strategy_bootstrap._load_probe_rows")
    def test_router_skip_reason_when_ctx_present(
        self,
        mock_rows: mock.MagicMock,
        mock_ctx: mock.MagicMock,
        mock_plans: mock.MagicMock,
    ) -> None:
        mock_rows.return_value = [{"day": "2026-06-05", "path": "p0"}]
        mock_ctx.return_value = {
            "2026-06-05": DayWashContext(
                day=datetime.date(2026, 6, 5),
                atr=30.0,
                drive_high=100.0,
                drive_low=90.0,
                gap_pts=8.0,
                open_0845=108.0,
                prior_close=100.0,
                ticks=[],
            )
        }
        mock_plans.return_value = {
            "2026-06-05": DayReplayPlan(day="2026-06-05", path="skip", skipped=True),
        }
        cfg = self._gudt_cfg()
        with self.assertLogs("integrations.strategy_bootstrap", level="INFO") as captured:
            out = bootstrap_gudt_route_a(
                cfg,
                code="TMFR1",
                dates=[datetime.date(2026, 6, 5)],
                cache_dir=REPO_ROOT / "tick_cache",
                mode="backtest",
            )
        self.assertEqual(
            out["day_plans"]["2026-06-05"].meta.get("skip_reason"),
            "router_skip",
        )
        self.assertIn("skip_reason=router_skip", "\n".join(captured.output))

    def test_write_day_plans_json(self) -> None:
        plans = {
            "2026-06-01": DayReplayPlan(day="2026-06-01", path="skip", skipped=True),
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "day_plans.json"
            write_day_plans_json(path, plans)
            self.assertTrue(path.is_file())
            self.assertIn("2026-06-01", path.read_text(encoding="utf-8"))

    @mock.patch("integrations.strategy_bootstrap.build_replay_plans_for_range")
    @mock.patch("integrations.strategy_bootstrap.load_probe_contexts")
    @mock.patch("integrations.strategy_bootstrap._load_probe_rows")
    def test_missing_backtest_date_gets_not_gudt_day_plan(
        self,
        mock_rows: mock.MagicMock,
        mock_ctx: mock.MagicMock,
        mock_plans: mock.MagicMock,
    ) -> None:
        mock_rows.return_value = []
        mock_ctx.return_value = {}
        mock_plans.return_value = {}
        cfg = self._gudt_cfg()
        out = bootstrap_gudt_route_a(
            cfg,
            code="TMFR1",
            dates=[datetime.date(2026, 6, 10)],
            cache_dir=REPO_ROOT / "tick_cache",
            mode="backtest",
            quiet_gudt_skip=True,
        )
        plan = out["day_plans"]["2026-06-10"]
        self.assertTrue(plan.skipped)
        self.assertEqual(plan.meta.get("skip_reason"), "not_gudt_day")

    @mock.patch("integrations.strategy_bootstrap.bootstrap_gudt_route_a")
    def test_build_strategy_session_injects_day_plans(
        self,
        mock_bootstrap: mock.MagicMock,
    ) -> None:
        plan = DayReplayPlan(day="2026-06-03", path="p0", skipped=False)
        mock_bootstrap.return_value = {"day_plans": {"2026-06-03": plan}}
        cfg = self._gudt_cfg()
        obs = DailyObservability()
        strategy = build_strategy_session(
            cfg,
            obs,
            code="TMFR1",
            dates=[datetime.date(2026, 6, 3)],
            cache_dir=REPO_ROOT / "tick_cache",
        )
        self.assertIn("2026-06-03", strategy._day_plans)


if __name__ == "__main__":
    unittest.main()
