"""P6-SMC-CAL B-class integration: log + kbar + tick replay harness."""

from __future__ import annotations

import datetime
import json
import tempfile
import unittest
from pathlib import Path

from reporting.forward_pnl import ForwardPnlPolicy
from reporting.performance_metrics import FrictionSettings
from reporting.structure_calibration import run_b_class_structure_calibration
from reporting.structure_calibration_cli import format_structure_calibration_report

_FIXTURE_TICKS = Path(__file__).resolve().parent.parent / "fixtures" / "ticks"
_FIXTURE_KBARS = Path(__file__).resolve().parent.parent / "fixtures" / "kbars"
_DAY = datetime.date(2026, 6, 12)
_ENTRY_TS = int(datetime.datetime(2026, 6, 12, 9, 0, 0).timestamp())


def _decision_line(payload: dict) -> str:
    return f"12:00:00 [INFO] DECISION_AUDIT {json.dumps(payload, ensure_ascii=False)}"


def _signal_line(payload: dict) -> str:
    return f"12:00:00 [INFO] SIGNAL_AUDIT {json.dumps(payload, ensure_ascii=False)}"


class TestStructureCalibrationBClass(unittest.TestCase):
    def test_run_b_class_with_fixture_kbars_and_ticks(self):
        log_lines = [
            _decision_line(
                {
                    "audit_schema_version": 1,
                    "event_type": "momentum_armed",
                    "ts": _ENTRY_TS,
                    "episode_id": "20260612-001",
                    "direction": "Long",
                    "trigger_price": 100.0,
                    "vol_1s": 150,
                    "buy_ratio": 0.8,
                    "sell_ratio": 0.2,
                    "vol_threshold": 120.0,
                    "multiplier": 1.0,
                    "vwap": 99.5,
                    "atr": 5.0,
                }
            ),
            _signal_line(
                {
                    "audit_schema_version": 1,
                    "intent": "entry",
                    "direction": "Buy",
                    "price": 100.0,
                    "ts": _ENTRY_TS + 20,
                    "episode_id": "20260612-001",
                    "reason": "pullback",
                }
            ),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            result = run_b_class_structure_calibration(
                log_lines=log_lines,
                code="TXFR1",
                dates=[_DAY],
                kbar_cache_dir=_FIXTURE_KBARS,
                tick_cache_dir=_FIXTURE_TICKS,
                forward_policy=ForwardPnlPolicy(window_seconds=1800),
                friction=FrictionSettings(enabled=True, round_trip_friction_points=2.0),
                output_dir=out_dir,
            )
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["n_armed"], 1)
            self.assertGreater(result["kbar_count"], 0)
            cf = result["counterfactuals"]
            self.assertIn("structure_only", cf)
            self.assertIn("comparison", cf)
            self.assertIn("delta_structure_vs_trend", cf["comparison"])
            self.assertEqual(result["conversion_30s_rate"], 1.0)
            self.assertTrue((out_dir / "structure_events.csv").is_file())
            self.assertTrue((out_dir / "structure_armed_join.csv").is_file())

    def test_format_report_includes_counterfactuals(self):
        result = {
            "status": "ok",
            "code": "TXFR1",
            "dates": ["2026-06-12"],
            "n_armed": 1,
            "kbar_count": 90,
            "tick_count": 8,
            "forward_policy": "fixed_seconds=1800",
            "conversion_30s_rate": 1.0,
            "counterfactuals": {
                "no_filter": {"veto_rate": 0.0, "n_veto": 0, "n_allowed": 1, "delta_expectancy_net": 0.0, "delta_expectancy": 0.0},
                "structure_only": {"veto_rate": 0.0, "n_veto": 0, "n_allowed": 1, "delta_expectancy_net": 5.0, "delta_expectancy": 7.0, "notes": "B-class"},
                "trend_only": {"veto_rate": 0.0, "n_veto": 0, "n_allowed": 1, "delta_expectancy_net": 3.0, "delta_expectancy": 5.0},
                "comparison": {
                    "structure_veto_rate": 0.0,
                    "trend_veto_rate": 0.0,
                    "delta_structure_vs_trend": 2.0,
                    "delta_structure_vs_no_filter": 5.0,
                    "phase3_gate": True,
                    "phase3_gate_note": "test",
                },
            },
        }
        text = format_structure_calibration_report(result)
        self.assertIn("structure_only", text)
        self.assertIn("delta_structure_vs_trend", text)

    def test_no_kbars_returns_blocked_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_b_class_structure_calibration(
                log_lines=[
                    _decision_line(
                        {
                            "event_type": "momentum_armed",
                            "ts": _ENTRY_TS,
                            "episode_id": "e",
                            "direction": "Long",
                            "trigger_price": 100.0,
                            "atr": 5.0,
                        }
                    )
                ],
                code="TXFR1",
                dates=[_DAY],
                kbar_cache_dir=Path(tmp),
                tick_cache_dir=_FIXTURE_TICKS,
            )
        self.assertEqual(result["status"], "no_kbars")


if __name__ == "__main__":
    unittest.main()