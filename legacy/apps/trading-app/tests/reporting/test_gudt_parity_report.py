"""Tests for GUDT research + parity reporting (FT-022 Phase 5)."""

from __future__ import annotations

import datetime
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from config import load_config
from core.runtime_config import TradingAppRuntimeConfig, _to_engine_settings
from reporting.gudt_parity_report import (
    EXTEND_DAYS_TARGET,
    FLIP_DAYS_TARGET,
    FULL_NET_TARGET,
    build_parity_report,
    build_research_report,
    parity_failures,
)
from strategy_gudt_route_a.types import DayReplayPlan

REPO_ROOT = Path(__file__).resolve().parents[4]


class TestGudtParityReport(unittest.TestCase):
    def _cfg(self) -> TradingAppRuntimeConfig:
        path = REPO_ROOT / "workspaces/gudt-route-a-baseline/config/config.yaml"
        return TradingAppRuntimeConfig(_to_engine_settings(load_config(path)))

    def test_parity_failures_oracle_pass(self) -> None:
        research = {
            "cf_net_total": FULL_NET_TARGET,
            "cf_extend_days": EXTEND_DAYS_TARGET,
            "cf_flip_days": FLIP_DAYS_TARGET,
            "slices": {"H1_2026": 1290.0, "UAT_2m": 100.0},
        }
        br5_slices = {"H1_2026": 1200.0, "UAT_2m": 50.0}
        failures = parity_failures(
            research,
            br5_slices=br5_slices,
            decision_mismatches=[],
        )
        self.assertEqual(failures, [])

    def test_parity_failures_detects_extend_mismatch(self) -> None:
        research = {
            "cf_net_total": FULL_NET_TARGET,
            "cf_extend_days": 0,
            "cf_flip_days": FLIP_DAYS_TARGET,
            "slices": {"H1_2026": 1290.0, "UAT_2m": 100.0},
        }
        failures = parity_failures(
            research,
            br5_slices={"H1_2026": 1200.0, "UAT_2m": 50.0},
            decision_mismatches=[],
        )
        self.assertTrue(any("extend_days" in f for f in failures))

    @mock.patch("reporting.gudt_parity_report.bootstrap_plans_for_range")
    @mock.patch("reporting.gudt_parity_report.load_probe_contexts")
    @mock.patch("reporting.gudt_parity_report.load_probe_rows_for_range")
    @mock.patch("reporting.gudt_parity_report.summarize_route_a_stack")
    def test_build_research_report_skip_stats(
        self,
        mock_summary: mock.MagicMock,
        mock_rows: mock.MagicMock,
        mock_ctx: mock.MagicMock,
        mock_bootstrap: mock.MagicMock,
    ) -> None:
        mock_rows.return_value = [{"day": "2026-06-03"}]
        mock_ctx.return_value = {}
        mock_summary.return_value = {
            "net_total": 10.0,
            "n": 1,
            "extend_days": 0,
            "flip_days": 0,
            "confirm_veto": 0,
            "picks": [{"day": "2026-06-03", "net": 10.0}],
        }
        mock_bootstrap.return_value = {
            "2026-06-03": DayReplayPlan(
                day="2026-06-03",
                path="skip",
                skipped=True,
                meta={"skip_reason": "not_gudt_day"},
            )
        }
        with tempfile.TemporaryDirectory() as d:
            out = build_research_report(
                self._cfg(),
                code="TMFR1",
                cache_dir=Path(d),
                from_date="2026-06-03",
                to_date="2026-06-03",
            )
        self.assertEqual(out["strategy"], "gudt_route_a")
        self.assertEqual(out["skip_stats"]["not_gudt_day"], 1)

    @mock.patch("reporting.gudt_parity_report.bootstrap_plans_for_range")
    @mock.patch("reporting.gudt_wash_probe.summarize_b_prime_composite")
    @mock.patch("reporting.gudt_parity_report.load_probe_contexts")
    @mock.patch("reporting.gudt_parity_report.load_probe_rows_for_range")
    @mock.patch("reporting.gudt_parity_report.summarize_route_a_stack")
    def test_build_parity_report_bootstrap_path(
        self,
        mock_summary: mock.MagicMock,
        mock_rows: mock.MagicMock,
        mock_ctx: mock.MagicMock,
        mock_br5: mock.MagicMock,
        mock_bootstrap: mock.MagicMock,
    ) -> None:
        pick = {
            "day": "2026-06-03",
            "net": FULL_NET_TARGET,
            "route_a_extended": True,
            "hedge": "flip",
            "dist_confirm": "pass",
        }
        mock_rows.return_value = [{"day": "2026-06-03"}]
        mock_ctx.return_value = {}
        mock_summary.return_value = {
            "net_total": FULL_NET_TARGET,
            "n": 1,
            "extend_days": EXTEND_DAYS_TARGET,
            "flip_days": FLIP_DAYS_TARGET,
            "confirm_veto": 0,
            "picks": [pick],
        }
        mock_br5.return_value = {"picks": [{"day": "2026-06-03", "net": 0.0}]}
        mock_bootstrap.return_value = {
            "2026-06-03": DayReplayPlan(
                day="2026-06-03",
                path="p0+sealed",
                skipped=False,
                meta={
                    "route_a_extended": True,
                    "hedge": "flip",
                    "dist_confirm": "pass",
                },
            )
        }
        with tempfile.TemporaryDirectory() as d:
            report = build_parity_report(
                self._cfg(),
                code="TMFR1",
                cache_dir=Path(d),
                from_date="2026-06-01",
                to_date="2026-06-30",
            )
        self.assertEqual(report["plans_source"], "bootstrap")
        self.assertEqual(report["decision_mismatches"], [])


if __name__ == "__main__":
    unittest.main()
