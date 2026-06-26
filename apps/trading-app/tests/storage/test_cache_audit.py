"""Tests for storage.cache_audit."""

from __future__ import annotations

import datetime
import tempfile
import unittest
from pathlib import Path

from storage.cache_audit import (
    EXPECTED_DAY_BARS,
    aggregate_ticks_to_minute_bars,
    audit_day,
    discover_tick_cache_pairs,
    scan_cache_dir,
)
from storage.kbar_loader import KBarRecord, save_kbars_csv
from storage.tick_loader import ReplayTick, save_ticks_csv


class TestCacheAudit(unittest.TestCase):
    def test_aggregate_ticks_to_minute_bars(self):
        day = datetime.date(2026, 6, 22)
        ticks = [
            ReplayTick(datetime.datetime(2026, 6, 22, 8, 45, 1), "100.0", 2, 1),
            ReplayTick(datetime.datetime(2026, 6, 22, 8, 45, 30), "102.0", 3, 1),
            ReplayTick(datetime.datetime(2026, 6, 22, 8, 46, 0), "101.0", 1, 1),
        ]
        bars = aggregate_ticks_to_minute_bars(ticks)
        b45 = datetime.datetime(2026, 6, 22, 8, 45)
        self.assertEqual(bars[b45].Open, 100.0)
        self.assertEqual(bars[b45].High, 102.0)
        self.assertEqual(bars[b45].Low, 100.0)
        self.assertEqual(bars[b45].Close, 102.0)
        self.assertEqual(bars[b45].Volume, 5)

    def test_audit_day_ok_when_ticks_match_kbars(self):
        day = datetime.date(2026, 6, 22)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            save_ticks_csv(
                [
                    ReplayTick(datetime.datetime(2026, 6, 22, 8, 45), "100.0", 10, 1),
                    ReplayTick(datetime.datetime(2026, 6, 22, 8, 45, 30), "101.0", 5, 1),
                ],
                root / "TMFR1_2026-06-22.csv",
            )
            save_kbars_csv(
                [
                    KBarRecord(
                        ts=datetime.datetime(2026, 6, 22, 8, 46),
                        Open=100.0,
                        High=101.0,
                        Low=100.0,
                        Close=101.0,
                        Volume=15,
                    )
                ],
                root / "TMFR1_kbars_2026-06-22.csv",
            )
            report = audit_day("TMFR1", day, cache_dir=root, max_examples=10)
            self.assertFalse(report.ohlc_mismatches)
            self.assertFalse(report.volume_mismatches)
            self.assertEqual(report.missing_kbar_for_ticks, [])

    def test_discover_excludes_kbars_and_dedupes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "TMFR1_2026-06-15.csv").write_text("x", encoding="utf-8")
            (root / "TMFR1_kbars_2026-06-15.csv").write_text("skip", encoding="utf-8")
            (root / "TXFR1_2026-06-15.csv").write_text("y", encoding="utf-8")
            pairs = discover_tick_cache_pairs(root)
            self.assertEqual(
                pairs,
                [
                    ("TMFR1", datetime.date(2026, 6, 15)),
                    ("TXFR1", datetime.date(2026, 6, 15)),
                ],
            )

    def test_expected_day_bars_is_300(self):
        self.assertEqual(EXPECTED_DAY_BARS, 300)

    def test_severity_fails_on_kbar_without_ticks(self):
        from storage.cache_audit import DayAuditReport

        r = DayAuditReport(
            code="TMFR1",
            date=datetime.date(2026, 1, 21),
            kbar_without_tick_count=15,
            kbar_count=300,
        )
        self.assertEqual(r.severity, "FAIL")

    def test_audit_ignores_out_of_session_tick_minutes(self):
        day = datetime.date(2026, 6, 22)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            save_ticks_csv(
                [
                    ReplayTick(datetime.datetime(2026, 6, 22, 8, 44), "99.0", 1, 1),
                    ReplayTick(datetime.datetime(2026, 6, 22, 8, 45), "100.0", 10, 1),
                ],
                root / "TMFR1_2026-06-22.csv",
            )
            save_kbars_csv(
                [
                    KBarRecord(
                        ts=datetime.datetime(2026, 6, 22, 8, 46),
                        Open=100.0,
                        High=100.0,
                        Low=100.0,
                        Close=100.0,
                        Volume=10,
                    )
                ],
                root / "TMFR1_kbars_2026-06-22.csv",
            )
            report = audit_day("TMFR1", day, cache_dir=root, max_examples=10)
            self.assertEqual(report.missing_kbar_count, 0)

    def test_format_day_line(self):
        from storage.cache_audit import DayAuditReport, format_day_line

        r = DayAuditReport(
            code="TMFR1",
            date=datetime.date(2026, 1, 8),
            vol_diff_count=53,
            ohlc_diff_count=4,
            kbar_count=291,
        )
        line = format_day_line(r)
        self.assertIn("差異vols:53", line)
        self.assertIn("kbars:291/300", line)


if __name__ == "__main__":
    unittest.main()
