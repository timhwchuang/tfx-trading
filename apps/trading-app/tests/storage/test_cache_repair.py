"""Tests for cache repair and rollover merge."""

from __future__ import annotations

import datetime
import gzip
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from storage.cache_audit import audit_day
from storage.kbar_loader import (
    KBarRecord,
    kbar_gz_path,
    kbar_path,
    load_kbars_csv,
    save_kbars_csv,
)
from storage.kbar_repair import repair_kbars_from_ticks
from storage.tick_loader import ReplayTick, cache_path, save_ticks_csv
from storage.tick_rollover import (
    is_near_month_settlement_day,
    merge_rollover_afternoon_ticks,
    next_continuous_code,
    ticks_need_rollover_afternoon,
)


class TestTickRollover(unittest.TestCase):
    def _settlement_day_ticks(self, day: datetime.date) -> list[ReplayTick]:
        ticks = [
            ReplayTick(
                datetime.datetime(day.year, day.month, day.day, 8, 45)
                + datetime.timedelta(minutes=i),
                "100",
                1,
                0,
            )
            for i in range(285)
        ]
        ticks.append(
            ReplayTick(datetime.datetime(day.year, day.month, day.day, 13, 29, 59), "100", 1, 0)
        )
        return ticks

    def test_next_continuous_code(self):
        self.assertEqual(next_continuous_code("TMFR1"), "TMFR2")
        self.assertIsNone(next_continuous_code("TXF"))

    def test_near_month_settlement_day(self):
        self.assertTrue(is_near_month_settlement_day(datetime.date(2026, 1, 21)))
        self.assertFalse(is_near_month_settlement_day(datetime.date(2026, 1, 8)))

    def test_ticks_need_rollover_afternoon(self):
        day = datetime.date(2026, 1, 21)
        ticks = self._settlement_day_ticks(day)[:-1]
        self.assertTrue(ticks_need_rollover_afternoon(ticks, day))
        full = [
            ReplayTick(datetime.datetime(2026, 1, 21, 13, 44, 59), "100", 1, 0)
        ]
        self.assertFalse(ticks_need_rollover_afternoon(full, day))
        partial_morning = [
            ReplayTick(datetime.datetime(2026, 1, 21, 11, 14), "100", 1, 0)
        ]
        self.assertFalse(ticks_need_rollover_afternoon(partial_morning, day))
        already_merged = self._settlement_day_ticks(day)[:-1] + [
            ReplayTick(datetime.datetime(2026, 1, 21, 13, 44), "100", 1, 0),
        ]
        self.assertTrue(ticks_need_rollover_afternoon(already_merged, day))
        fully_merged = self._settlement_day_ticks(day)[:-1] + [
            ReplayTick(
                datetime.datetime(2026, 1, 21, 13, 30) + datetime.timedelta(minutes=i),
                "100",
                1,
                0,
            )
            for i in range(15)
        ]
        self.assertFalse(ticks_need_rollover_afternoon(fully_merged, day))
        partial_afternoon = self._settlement_day_ticks(day)[:-1] + [
            ReplayTick(datetime.datetime(2026, 1, 21, 13, 30), "100", 1, 0),
        ]
        self.assertTrue(ticks_need_rollover_afternoon(partial_afternoon, day))
        partial_r2 = self._settlement_day_ticks(day)[:-1] + [
            ReplayTick(datetime.datetime(2026, 1, 21, 13, 35), "100", 1, 0),
        ]
        self.assertTrue(ticks_need_rollover_afternoon(partial_r2, day))
        night_only = self._settlement_day_ticks(day)[:-1] + [
            ReplayTick(datetime.datetime(2026, 1, 21, 15, 0), "100", 1, 0),
        ]
        self.assertTrue(ticks_need_rollover_afternoon(night_only, day))
        truncated_non_settlement = self._settlement_day_ticks(datetime.date(2026, 1, 8))[:-1]
        self.assertFalse(
            ticks_need_rollover_afternoon(truncated_non_settlement, datetime.date(2026, 1, 8))
        )


class TestKbarRepair(unittest.TestCase):
    def test_fills_missing_kbar_from_ticks(self):
        day = datetime.date(2026, 1, 8)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            ticks = []
            for minute in range(45, 60):
                ticks.append(
                    ReplayTick(
                        datetime.datetime(2026, 1, 8, 11, minute),
                        "30000",
                        10,
                        1,
                    )
                )
            save_ticks_csv(ticks, cache_path(root, "TMFR1", day))
            save_kbars_csv(
                [
                    KBarRecord(
                        ts=datetime.datetime(2026, 1, 8, 11, 54),
                        Open=30000.0,
                        High=30001.0,
                        Low=29999.0,
                        Close=30000.0,
                        Volume=10,
                    )
                ],
                kbar_path(root, "TMFR1", day),
            )
            n = repair_kbars_from_ticks("TMFR1", day, cache_dir=root)
            self.assertGreaterEqual(n, 5)
            report = audit_day("TMFR1", day, cache_dir=root, max_examples=10)
            self.assertLess(report.missing_kbar_count, 14)

    def test_keeps_afternoon_kbars_when_ticks_missing_rollover(self):
        """Settlement day, R1 ticks stop ~13:29; existing afternoon kbars must survive."""
        day = datetime.date(2026, 1, 21)
        morning_ticks = [
            ReplayTick(
                datetime.datetime(2026, 1, 21, 8, 45) + datetime.timedelta(minutes=i),
                "100",
                1,
                0,
            )
            for i in range(285)
        ]
        self.assertTrue(ticks_need_rollover_afternoon(morning_ticks, day))
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            save_ticks_csv(morning_ticks, cache_path(root, "TMFR1", day))
            afternoon_kbars = [
                KBarRecord(
                    ts=datetime.datetime(2026, 1, 21, 13, 31),
                    Open=100.0,
                    High=100.0,
                    Low=100.0,
                    Close=100.0,
                    Volume=5,
                ),
                KBarRecord(
                    ts=datetime.datetime(2026, 1, 21, 13, 40),
                    Open=100.0,
                    High=100.0,
                    Low=100.0,
                    Close=100.0,
                    Volume=5,
                ),
            ]
            save_kbars_csv(afternoon_kbars, kbar_path(root, "TMFR1", day))
            repair_kbars_from_ticks("TMFR1", day, cache_dir=root)
            ts_set = {b.ts for b in load_kbars_csv(kbar_path(root, "TMFR1", day))}
            self.assertIn(datetime.datetime(2026, 1, 21, 13, 31), ts_set)
            self.assertIn(datetime.datetime(2026, 1, 21, 13, 40), ts_set)

    def test_keeps_afternoon_kbars_when_partial_rollover_merge(self):
        """Partial TMFR2 merge (e.g. only 13:30) must not prune remaining afternoon kbars."""
        day = datetime.date(2026, 1, 21)
        morning_ticks = [
            ReplayTick(
                datetime.datetime(2026, 1, 21, 8, 45) + datetime.timedelta(minutes=i),
                "100",
                1,
                0,
            )
            for i in range(285)
        ]
        partial_ticks = morning_ticks + [
            ReplayTick(datetime.datetime(2026, 1, 21, 13, 30), "100", 1, 0),
        ]
        self.assertTrue(ticks_need_rollover_afternoon(partial_ticks, day))
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            save_ticks_csv(partial_ticks, cache_path(root, "TMFR1", day))
            afternoon_kbars = [
                KBarRecord(
                    ts=datetime.datetime(2026, 1, 21, 13, 31),
                    Open=100.0,
                    High=100.0,
                    Low=100.0,
                    Close=100.0,
                    Volume=5,
                ),
                KBarRecord(
                    ts=datetime.datetime(2026, 1, 21, 13, 40),
                    Open=100.0,
                    High=100.0,
                    Low=100.0,
                    Close=100.0,
                    Volume=5,
                ),
            ]
            save_kbars_csv(afternoon_kbars, kbar_path(root, "TMFR1", day))
            repair_kbars_from_ticks("TMFR1", day, cache_dir=root)
            ts_set = {b.ts for b in load_kbars_csv(kbar_path(root, "TMFR1", day))}
            self.assertIn(datetime.datetime(2026, 1, 21, 13, 31), ts_set)
            self.assertIn(datetime.datetime(2026, 1, 21, 13, 40), ts_set)

    def test_repair_writes_plain_csv_when_only_gz_mirror_exists(self):
        day = datetime.date(2026, 1, 8)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            ticks = [
                ReplayTick(
                    datetime.datetime(2026, 1, 8, 11, 54),
                    "30000",
                    10,
                    1,
                )
            ]
            save_ticks_csv(ticks, cache_path(root, "TMFR1", day))
            plain = kbar_path(root, "TMFR1", day)
            gz = kbar_gz_path(root, "TMFR1", day)
            save_kbars_csv(
                [
                    KBarRecord(
                        ts=datetime.datetime(2026, 1, 8, 11, 54),
                        Open=30000.0,
                        High=30001.0,
                        Low=29999.0,
                        Close=30000.0,
                        Volume=10,
                    )
                ],
                plain,
            )
            with plain.open("rb") as src, gzip.open(gz, "wb") as dst:
                dst.writelines(src)
            plain.unlink()
            repair_kbars_from_ticks("TMFR1", day, cache_dir=root)
            self.assertTrue(plain.is_file())
            self.assertFalse(gz.is_file())


class TestRolloverMerge(unittest.TestCase):
    def _settlement_day_ticks(self, day: datetime.date) -> list[ReplayTick]:
        ticks = [
            ReplayTick(
                datetime.datetime(day.year, day.month, day.day, 8, 45)
                + datetime.timedelta(minutes=i),
                "100",
                1,
                0,
            )
            for i in range(285)
        ]
        ticks.append(
            ReplayTick(datetime.datetime(day.year, day.month, day.day, 13, 29, 59), "100", 1, 0)
        )
        return ticks

    def test_merge_afternoon_into_primary(self):
        api = MagicMock()
        day = datetime.date(2026, 1, 21)
        afternoon = [
            ReplayTick(datetime.datetime(2026, 1, 21, 13, 30), "100", 1, 0),
            ReplayTick(datetime.datetime(2026, 1, 21, 13, 44), "101", 1, 0),
        ]
        api.Contracts.Futures.TMF.TMFR2 = MagicMock(code="TMFR2")

        from storage import tick_loader

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            save_ticks_csv(
                self._settlement_day_ticks(day)[:-1],
                cache_path(root, "TMFR1", day),
            )
            with unittest.mock.patch(
                "storage.tick_rollover.fetch_ticks_for_date", return_value=afternoon
            ):
                n_fetch, n_total = merge_rollover_afternoon_ticks(
                    api,
                    "TMFR1",
                    day,
                    cache_dir=root,
                    simulation=True,
                    resolve_contract=lambda _api, c: getattr(
                        api.Contracts.Futures.TMF, c
                    ),
                )
            self.assertEqual(n_fetch, 2)
            self.assertEqual(n_total, 287)
            loaded = tick_loader.load_merged_tick_cache(root, "TMFR1", day)
            self.assertEqual(loaded[-1].datetime, afternoon[-1].datetime)

    def test_ticks_need_rollover_uses_latest_tick_not_file_order(self):
        day = datetime.date(2026, 1, 21)
        ticks = TestTickRollover()._settlement_day_ticks(day)[:-1]
        shuffled = list(reversed(ticks))
        self.assertTrue(ticks_need_rollover_afternoon(shuffled, day))


if __name__ == "__main__":
    unittest.main()
