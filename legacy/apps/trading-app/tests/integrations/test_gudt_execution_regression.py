"""Light integration: execution parity hard gate on synthetic plan+log."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from observability import FillAudit, format_fill_audit
from reporting.date_slices import DateRange
from reporting.gudt_execution_compare import compare_execution


class TestGudtExecutionRegression(unittest.TestCase):
    def test_single_day_round_trip_parity(self) -> None:
        day = "2026-06-01"
        plans = {
            day: {
                "path": "p0+sealed",
                "skipped": False,
                "events": [
                    {"ts": 1780278300, "price": 46050.0, "leg": "long_entry", "reason": "p0+sealed"},
                    {"ts": 1780280837, "price": 46288.0, "leg": "long_exit", "reason": "trail_stop"},
                ],
            }
        }
        entry = FillAudit(
            intent="entry",
            direction="Buy",
            signal_price=46050.0,
            fill_price=46050.0,
            slippage_pts=0.0,
            limit_price=46053.0,
            slippage_vs_limit_pts=0.0,
            order_id="1",
            ts=1780278300,
        )
        exit_ = FillAudit(
            intent="exit",
            direction="Sell",
            signal_price=46288.0,
            fill_price=46288.0,
            slippage_pts=0.0,
            limit_price=46285.0,
            slippage_vs_limit_pts=0.0,
            order_id="2",
            ts=1780280837,
            exit_reason="trail_stop",
            pnl_points=238.0,
            hold_sec=2537,
        )
        log_body = (
            f"INFO FILL_AUDIT {format_fill_audit(entry)}\n"
            f"INFO FILL_AUDIT {format_fill_audit(exit_)}\n"
        )
        with tempfile.TemporaryDirectory() as d:
            log_path = Path(d) / "baseline.log"
            log_path.write_text(log_body, encoding="utf-8")
            result = compare_execution(
                plans,
                log_path,
                date_range=DateRange("regression", day, day),
            )
        self.assertEqual(result.cf_round_count, 1)
        self.assertEqual(result.kernel_round_count, 1)
        self.assertFalse(result.failures)


if __name__ == "__main__":
    unittest.main()
