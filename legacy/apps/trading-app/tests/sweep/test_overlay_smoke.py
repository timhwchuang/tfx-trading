"""FT-003: overlay_smoke CLI."""

from __future__ import annotations

import datetime
import unittest
from pathlib import Path
from unittest.mock import patch

from sweep.overlay_smoke import run_overlay_smoke


class TestOverlaySmoke(unittest.TestCase):
    def test_pass_when_kpi_differs(self):
        summaries_a = [{"pnl": {"daily_pnl_points": 1.0}, "fills": {"exit_count": 2}, "quick_stop_loss": {"count": 0}}]
        summaries_b = [{"pnl": {"daily_pnl_points": 9.0}, "fills": {"exit_count": 2}, "quick_stop_loss": {"count": 0}}]

        def fake_run(_code, _dates, cache_dir, runtime_config=None):
            val = runtime_config.live_get("MIN_ATR_THRESHOLD", 25.0)
            if val == 22.0:
                return summaries_a, [], []
            return summaries_b, [], []

        with patch("sweep.overlay_smoke._run_backtest_summaries", side_effect=fake_run):
            rc = run_overlay_smoke(
                key="min_atr_threshold",
                values=[22.0, 36.0],
                date=datetime.date(2026, 3, 2),
                cache_dir=Path("/tmp"),
            )
        self.assertEqual(rc, 0)

    def test_fail_when_kpi_identical(self):
        summaries = [{"pnl": {"daily_pnl_points": 1.0}, "fills": {"exit_count": 2}, "quick_stop_loss": {"count": 0}}]

        def fake_run(_code, _dates, cache_dir, runtime_config=None):
            return summaries, [], []

        with patch("sweep.overlay_smoke._run_backtest_summaries", side_effect=fake_run):
            rc = run_overlay_smoke(
                key="min_atr_threshold",
                values=[22.0, 36.0],
                date=datetime.date(2026, 3, 2),
                cache_dir=Path("/tmp"),
            )
        self.assertEqual(rc, 1)

    def test_pass_overlay_only_key_when_kpi_identical(self):
        summaries = [{"pnl": {"daily_pnl_points": 1.0}, "fills": {"exit_count": 2}, "quick_stop_loss": {"count": 0}}]

        def fake_run(_code, _dates, cache_dir, runtime_config=None):
            return summaries, [], []

        with patch("sweep.overlay_smoke._run_backtest_summaries", side_effect=fake_run):
            rc = run_overlay_smoke(
                key="pending_timeout_sec",
                values=[30, 120],
                date=datetime.date(2026, 3, 2),
                cache_dir=Path("/tmp"),
            )
        self.assertEqual(rc, 0)

    def test_fail_overlay_readback_mismatch(self):
        summaries = [{"pnl": {"daily_pnl_points": 1.0}, "fills": {"exit_count": 2}, "quick_stop_loss": {"count": 0}}]

        def fake_run(_code, _dates, cache_dir, runtime_config=None):
            return summaries, [], []

        with (
            patch("sweep.overlay_smoke._run_backtest_summaries", side_effect=fake_run),
            patch(
                "sweep.overlay_smoke._read_applied_value",
                side_effect=[30, 30],
            ),
        ):
            rc = run_overlay_smoke(
                key="pending_timeout_sec",
                values=[30, 120],
                date=datetime.date(2026, 3, 2),
                cache_dir=Path("/tmp"),
            )
        self.assertEqual(rc, 1)

    def test_fail_when_strategy_key_overlay_not_applied(self):
        """Deliberately broken overlay: KPI unchanged and readback ignores toggle."""
        summaries = [{"pnl": {"daily_pnl_points": 1.0}, "fills": {"exit_count": 2}, "quick_stop_loss": {"count": 0}}]

        def fake_run(_code, _dates, cache_dir, runtime_config=None):
            return summaries, [], []

        with (
            patch("sweep.overlay_smoke._run_backtest_summaries", side_effect=fake_run),
            patch(
                "sweep.overlay_smoke._read_applied_value",
                side_effect=[False, False],
            ),
        ):
            rc = run_overlay_smoke(
                key="structure_filter_enabled",
                values=[False, True],
                date=datetime.date(2026, 3, 2),
                cache_dir=Path("/tmp"),
            )
        self.assertEqual(rc, 1)

    def test_rejects_holdout_date(self):
        with self.assertRaises(RuntimeError):
            run_overlay_smoke(
                key="min_atr_threshold",
                values=[22.0, 36.0],
                date=datetime.date(2026, 5, 15),
                cache_dir=Path("/tmp"),
            )


if __name__ == "__main__":
    unittest.main()
