"""Tests for reporting.evidence_csv validation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from reporting.evidence_csv import (
    evaluate_broker_reconciliation_csv,
    evaluate_tick_stratification_csv,
)


class TestEvidenceCsv(unittest.TestCase):
    def test_broker_csv_passes_when_explained(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broker.csv"
            path.write_text(
                "date,broker_daily_pnl_pts,log_daily_pnl_points,diff_pts,round_trips,broker_source_note,explained_y_or_n,explanation\n"
                "2026-06-17,3.0,3.5,-0.50,4,sim,Y,within threshold\n",
                encoding="utf-8",
            )
            passed, detail = evaluate_broker_reconciliation_csv(
                path,
                expected_dates={"2026-06-17"},
            )
            self.assertTrue(passed, detail)

    def test_broker_csv_fails_on_unexplained_diff(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broker.csv"
            path.write_text(
                "date,broker_daily_pnl_pts,log_daily_pnl_points,diff_pts,round_trips,broker_source_note,explained_y_or_n,explanation\n"
                "2026-06-17,1.0,3.5,-2.50,4,sim,,\n",
                encoding="utf-8",
            )
            passed, _detail = evaluate_broker_reconciliation_csv(
                path,
                expected_dates={"2026-06-17"},
            )
            self.assertFalse(passed)

    def test_tick_csv_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tick.csv"
            path.write_text(
                "date,type0_pct,tier,signal_intents,fills,conversion_pct,expectancy_gross_pts,expectancy_net_pts,notes\n"
                "2026-06-17,25.0,low_lt30,5,4,80.00,0.42,0.38,\n"
                "2026-06-18,35.0,mid_30_40,3,2,66.67,0.30,0.25,\n",
                encoding="utf-8",
            )
            passed, detail = evaluate_tick_stratification_csv(
                path,
                expected_dates={"2026-06-17", "2026-06-18"},
            )
            self.assertTrue(passed, detail)


if __name__ == "__main__":
    unittest.main()