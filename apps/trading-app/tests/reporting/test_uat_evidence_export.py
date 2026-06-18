"""Tests for reporting.uat_evidence_export."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from reporting.uat_evidence_export import (
    build_broker_row,
    build_tick_row,
    classify_tick_tier,
    export_evidence,
    load_broker_overrides,
    write_broker_reconciliation_csv,
    write_tick_stratification_csv,
)


def _sample_report(
    *,
    type0_pct: float = 25.0,
    log_pnl: float = 3.5,
    rounds: int = 4,
    entry_signals: int = 5,
    conversion: float = 0.8,
    exp_gross: float = 0.42,
    exp_net: float = 0.38,
) -> dict:
    return {
        "completed_rounds": rounds,
        "entry_signals": entry_signals,
        "momentum_to_entry_conversion": conversion,
        "tick_type": {"type0_pct": type0_pct},
        "performance": {
            "expectancy": {
                "expectancy_per_trade_gross": exp_gross,
                "expectancy_per_trade_net": exp_net,
            },
            "total_pnl_net": log_pnl,
        },
        "daily_summaries": [
            {"date": "2026-06-17", "pnl": {"daily_pnl_points": log_pnl}},
        ],
    }


class TestUatEvidenceExport(unittest.TestCase):
    def test_classify_tick_tier(self):
        self.assertEqual(classify_tick_tier(20.0), "low_lt30")
        self.assertEqual(classify_tick_tier(30.0), "mid_30_40")
        self.assertEqual(classify_tick_tier(40.0), "mid_30_40")
        self.assertEqual(classify_tick_tier(41.0), "high_gt40")

    def test_build_tick_row(self):
        row = build_tick_row("2026-06-17", _sample_report())
        self.assertEqual(row["tier"], "low_lt30")
        self.assertEqual(row["signal_intents"], "5")
        self.assertEqual(row["fills"], "4")
        self.assertEqual(row["conversion_pct"], "80.00")
        self.assertEqual(row["expectancy_net_pts"], "0.38")

    def test_build_broker_row_with_override(self):
        row = build_broker_row(
            "2026-06-17",
            _sample_report(log_pnl=3.5),
            broker_override={
                "broker_daily_pnl_pts": "3.0",
                "broker_source_note": "sim screenshot",
            },
        )
        self.assertEqual(row["log_daily_pnl_points"], "3.50")
        self.assertEqual(row["diff_pts"], "-0.50")
        self.assertEqual(row["explained_y_or_n"], "Y")

    def test_build_broker_row_flags_large_diff(self):
        row = build_broker_row(
            "2026-06-17",
            _sample_report(log_pnl=3.5),
            broker_override={"broker_daily_pnl_pts": "1.0"},
        )
        self.assertEqual(row["diff_pts"], "-2.50")
        self.assertEqual(row["explained_y_or_n"], "N")
        self.assertIn("review required", row["explanation"])

    def test_write_csv_merge_preserves_manual_broker_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "broker.csv"
            out.write_text(
                "date,broker_daily_pnl_pts,log_daily_pnl_points,diff_pts,round_trips,broker_source_note,explained_y_or_n,explanation\n"
                "2026-06-17,3.0,0,,0,sim stmt,Y,manual note\n",
                encoding="utf-8",
            )
            rows = write_broker_reconciliation_csv(
                [("2026-06-17", _sample_report(log_pnl=3.5, rounds=6))],
                out,
            )
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["broker_daily_pnl_pts"], "3.0")
            self.assertEqual(rows[0]["log_daily_pnl_points"], "3.50")
            self.assertEqual(rows[0]["round_trips"], "6")
            self.assertEqual(rows[0]["explanation"], "manual note")

    def test_write_tick_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "tick.csv"
            rows = write_tick_stratification_csv(
                [("2026-06-17", _sample_report(type0_pct=42.0))],
                out,
            )
            self.assertEqual(rows[0]["tier"], "high_gt40")
            with out.open(encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                saved = list(reader)
            self.assertEqual(saved[0]["tier"], "high_gt40")

    def test_load_broker_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broker_input.csv"
            path.write_text(
                "date,broker_daily_pnl_pts,broker_source_note\n"
                "2026-06-17,4.0,sim export\n",
                encoding="utf-8",
            )
            overrides = load_broker_overrides(path)
            self.assertEqual(overrides["2026-06-17"]["broker_daily_pnl_pts"], "4.0")

    def test_invalid_broker_pnl_does_not_crash(self):
        row = build_broker_row(
            "2026-06-17",
            _sample_report(),
            broker_override={"broker_daily_pnl_pts": "not-a-number"},
        )
        self.assertEqual(row["broker_daily_pnl_pts"], "not-a-number")
        self.assertIn("invalid broker_daily_pnl_pts", row["explanation"])

    def test_new_broker_row_with_broker_data_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "broker.csv"
            rows = write_broker_reconciliation_csv(
                [("2026-06-18", _sample_report(log_pnl=2.0, rounds=3))],
                out,
                broker_overrides={
                    "2026-06-18": {
                        "broker_daily_pnl_pts": "2.0",
                        "broker_source_note": "sim stmt",
                    }
                },
            )
            self.assertEqual(rows[0]["explained_y_or_n"], "Y")
            self.assertEqual(rows[0]["diff_pts"], "0.00")

    def test_tick_notes_include_missing_type0_and_zero_rounds(self):
        row = build_tick_row(
            "2026-06-17",
            {
                "completed_rounds": 0,
                "entry_signals": 0,
                "performance": {"expectancy": {}},
            },
        )
        self.assertIn("missing tick_type", row["notes"])
        self.assertIn("0 completed round-trips", row["notes"])

    def test_cli_main_smoke(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report = tmp_path / "day20260617.json"
            report.write_text(json.dumps(_sample_report()), encoding="utf-8")
            tick_out = tmp_path / "tick.csv"
            from reporting.uat_evidence_export import main

            rc = main(["tick", str(report), "--tick-output", str(tick_out)])
            self.assertEqual(rc, 0)
            self.assertTrue(tick_out.is_file())

    def test_export_evidence_both(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report = tmp_path / "day20260617.json"
            report.write_text(json.dumps(_sample_report()), encoding="utf-8")
            broker_out = tmp_path / "broker.csv"
            tick_out = tmp_path / "tick.csv"
            summary = export_evidence(
                [report],
                mode="both",
                broker_output=broker_out,
                tick_output=tick_out,
            )
            self.assertTrue(broker_out.is_file())
            self.assertTrue(tick_out.is_file())
            self.assertEqual(summary["report_count"], 1)


if __name__ == "__main__":
    unittest.main()