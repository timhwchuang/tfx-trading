"""Tests for ft004_run_baseline gate report updates."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.ft004_run_baseline import _write_gate_report


class TestFt004GateReport(unittest.TestCase):
    def test_write_gate_report_updates_filled_rows(self) -> None:
        template = """## G1

| 指標 | 值 | Pass |
|------|-----|------|
| gross expectancy/趟 | -0.02 | ☐ |
| trade_count（valid 月） | 201 | |

## G2

| 指標 | 值 | Pass |
|------|-----|------|
| net expectancy/趟 | -5.02 | ☐ |

## G3

| 指標 | 值 | Pass |
|------|-----|------|
| trade_count | 201 | ☐ |

## G4

| 指標 | 值 | Pass |
|------|-----|------|
| quick_stop_loss_rate | 0.5% | ☑ |
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gate_report.md"
            path.write_text(template, encoding="utf-8")
            _write_gate_report(path, gross=6.5, net=1.5, trades=80, qsl=0.1)
            text = path.read_text(encoding="utf-8")
            self.assertIn("| gross expectancy/趟 | 6.50 | ☑ |", text)
            self.assertIn("| net expectancy/趟 | 1.50 | ☑ |", text)
            self.assertIn("| trade_count（valid 月） | 80 |", text)
            self.assertIn("| trade_count | 80 | ☑ |", text)
            self.assertIn("| quick_stop_loss_rate | 10.0% | ☑ |", text)


if __name__ == "__main__":
    unittest.main()
