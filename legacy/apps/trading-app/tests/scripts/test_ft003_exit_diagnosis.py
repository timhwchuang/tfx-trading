"""Tests for FT-003 exit diagnosis."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from reporting.exit_diagnosis import (
    diagnose_report,
    merge_exit_into_markdown,
    parse_exit_audits_from_log,
)


class TestExitDiagnosisMerge(unittest.TestCase):
    def test_merge_appends_multiple_agents(self) -> None:
        template = """# Test

## D. 出場診斷（P0 — baseline valid）

（由 `ft003_exit_diagnosis.py` 填入）

---

## E. tail
"""
        with tempfile.TemporaryDirectory() as tmp:
            md = Path(tmp) / "VOLATILITY_BASELINE.md"
            md.write_text(template, encoding="utf-8")
            merge_exit_into_markdown(
                md,
                "**Agent / report**：`agent-a` / `a.json`\n\n### D.1\n",
                agent="agent-a",
            )
            merge_exit_into_markdown(
                md,
                "**Agent / report**：`agent-b` / `b.json`\n\n### D.1\n",
                agent="agent-b",
            )
            text = md.read_text(encoding="utf-8")
            self.assertIn("agent-a", text)
            self.assertIn("agent-b", text)
            self.assertEqual(text.count("**Agent / report**："), 2)


class TestDiagnoseReport(unittest.TestCase):
    def test_aggregates_near_miss_from_daily_summaries(self) -> None:
        report = {
            "exit_reasons": {"stop_loss": 2},
            "expectancy_by_reason": {"stop_loss": {"count": 2, "total_pnl": -10, "avg_pnl": -5}},
            "daily_summaries": [
                {"near_miss": {"blocked_both": 10, "blocked_vwap_only": 1, "blocked_vol_only": 0}},
                {"near_miss": {"blocked_both": 20, "blocked_vwap_only": 2, "blocked_vol_only": 1}},
            ],
        }
        d = diagnose_report(report)
        self.assertEqual(d["near_miss"]["blocked_both"], 30)
        self.assertEqual(d["near_miss"]["_aggregated_from_days"], 2)

    def test_integrity_warning_on_count_mismatch(self) -> None:
        report = {
            "exit_reasons": {"stop_loss": 57},
            "expectancy_by_reason": {"stop_loss": {"count": 55, "total_pnl": -1, "avg_pnl": -1}},
            "near_miss": {},
        }
        d = diagnose_report(report)
        self.assertTrue(any("stop_loss" in w for w in d["integrity_warnings"]))


class TestParseExitAudits(unittest.TestCase):
    def test_grace_and_malformed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "baseline.log"
            audit = {
                "intent": "exit",
                "reason": "stop_loss",
                "hold_ticks": 5,
                "in_grace": True,
            }
            log.write_text(
                f"SIGNAL_AUDIT {json.dumps(audit)}\n"
                'SIGNAL_AUDIT {"intent":"exit","reason":"stop_loss" broken}\n',
                encoding="utf-8",
            )
            stats = parse_exit_audits_from_log(log)
            self.assertEqual(stats["stop_loss_count"], 1)
            self.assertEqual(stats["stop_loss_in_grace_pct"], 100.0)
            self.assertEqual(stats["malformed_audit_lines"], 1)


if __name__ == "__main__":
    unittest.main()
