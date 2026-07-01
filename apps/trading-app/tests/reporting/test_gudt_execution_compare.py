"""Tests for GUDT execution compare (plan vs kernel fills)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from observability import format_fill_audit, FillAudit
from reporting.date_slices import DateRange, day_in_date_range
from reporting.gudt_execution_compare import (
    build_planned_rounds,
    compare_execution,
    normalize_exit_reason,
)


class TestGudtExecutionCompare(unittest.TestCase):
    def test_build_planned_rounds_long(self) -> None:
        plans = {
            "2026-06-01": {
                "path": "p0+sealed",
                "skipped": False,
                "events": [
                    {"ts": 1000, "price": 46050.0, "leg": "long_entry", "reason": "p0+sealed"},
                    {"ts": 2000, "price": 46288.0, "leg": "long_exit", "reason": "trail_stop"},
                ],
            }
        }
        rounds = build_planned_rounds(
            plans, date_range=DateRange("test", "2026-06-01", "2026-06-30")
        )
        self.assertEqual(len(rounds), 1)
        self.assertEqual(rounds[0].planned_gross, 238.0)

    def test_compare_n_match(self) -> None:
        plans = {
            "2026-06-01": {
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
                date_range=DateRange("test", "2026-06-01", "2026-06-30"),
            )
        self.assertEqual(result.cf_round_count, 1)
        self.assertEqual(result.kernel_round_count, 1)
        self.assertEqual(result.failures, [])
        self.assertTrue(result.rounds[0].exit_reason_match)

    def test_compare_n_mismatch_fails(self) -> None:
        plans = {
            "2026-06-01": {
                "path": "p0+sealed",
                "skipped": False,
                "events": [
                    {"ts": 1000, "price": 100.0, "leg": "long_entry", "reason": "p0"},
                    {"ts": 2000, "price": 110.0, "leg": "long_exit", "reason": "horizon"},
                ],
            }
        }
        with tempfile.TemporaryDirectory() as d:
            log_path = Path(d) / "empty.log"
            log_path.write_text("", encoding="utf-8")
            result = compare_execution(
                plans,
                log_path,
                date_range=DateRange("test", "2026-06-01", "2026-06-30"),
            )
        self.assertTrue(result.failures)

    def test_months_filter_excludes_hull_gap(self) -> None:
        plans = {
            "2025-05-02": {
                "path": "p0",
                "skipped": False,
                "events": [
                    {"ts": 1, "price": 100.0, "leg": "long_entry", "reason": "p0"},
                    {"ts": 2, "price": 110.0, "leg": "long_exit", "reason": "horizon"},
                ],
            },
            "2025-12-01": {
                "path": "p0",
                "skipped": False,
                "events": [
                    {"ts": 1, "price": 100.0, "leg": "long_entry", "reason": "p0"},
                    {"ts": 2, "price": 110.0, "leg": "long_exit", "reason": "horizon"},
                ],
            },
        }
        dr = DateRange("spot", "2025-05-01", "2025-12-31", months=("2025-05",))
        rounds = build_planned_rounds(plans, date_range=dr)
        self.assertEqual(len(rounds), 1)
        self.assertEqual(rounds[0].day, "2025-05-02")
        self.assertFalse(day_in_date_range("2025-12-01", dr))


if __name__ == "__main__":
    unittest.main()
