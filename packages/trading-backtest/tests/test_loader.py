"""Loader validation and tick normalization tests."""

from __future__ import annotations

import datetime
import gzip
import logging
import tempfile
import unittest
from pathlib import Path

from trading_backtest.loader import (
    KBarRecord,
    iter_kbars_in_range,
    kbar_gz_path,
    kbar_path,
    load_kbars_csv,
    load_ticks_csv,
    resolve_kbar_path,
    save_kbars_csv,
)


def _write_tick_csv(path: Path, rows: list[dict[str, str]]) -> None:
    import csv

    fields = [
        "datetime",
        "close",
        "volume",
        "bid_price",
        "ask_price",
        "tick_type",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


class TestLoaderValidation(unittest.TestCase):
    def test_close_normalized_to_float(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "TXFR1_2026-06-12.csv"
            _write_tick_csv(
                path,
                [
                    {
                        "datetime": "2026-06-12T09:00:00",
                        "close": "18000.5",
                        "volume": "1",
                        "bid_price": "17999",
                        "ask_price": "18001",
                        "tick_type": "0",
                    }
                ],
            )
            ticks = load_ticks_csv(path)
            self.assertEqual(len(ticks), 1)
            self.assertIsInstance(ticks[0].close, float)
            self.assertAlmostEqual(ticks[0].close, 18000.5)

    def test_unsorted_ticks_are_sorted_with_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "TXFR1_2026-06-12.csv"
            _write_tick_csv(
                path,
                [
                    {
                        "datetime": "2026-06-12T09:00:02",
                        "close": "18002",
                        "volume": "1",
                        "bid_price": "0",
                        "ask_price": "0",
                        "tick_type": "0",
                    },
                    {
                        "datetime": "2026-06-12T09:00:00",
                        "close": "18000",
                        "volume": "1",
                        "bid_price": "0",
                        "ask_price": "0",
                        "tick_type": "0",
                    },
                ],
            )
            with self.assertLogs("trading_backtest.loader", level="WARNING") as logs:
                ticks = load_ticks_csv(path)
            self.assertEqual(
                [t.datetime for t in ticks],
                [
                    datetime.datetime(2026, 6, 12, 9, 0, 0),
                    datetime.datetime(2026, 6, 12, 9, 0, 2),
                ],
            )
            self.assertTrue(any("not monotonically sorted" in m for m in logs.output))

    def test_duplicate_tick_row_logged_not_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "TXFR1_2026-06-12.csv"
            row = {
                "datetime": "2026-06-12T09:00:00",
                "close": "18000",
                "volume": "1",
                "bid_price": "0",
                "ask_price": "0",
                "tick_type": "0",
            }
            _write_tick_csv(path, [row, row])
            with self.assertLogs("trading_backtest.loader", level="INFO") as logs:
                ticks = load_ticks_csv(path)
            self.assertEqual(len(ticks), 2)
            self.assertTrue(any("identical tick row" in m for m in logs.output))

    def test_same_millisecond_different_price_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "TXFR1_2026-06-12.csv"
            base = {
                "datetime": "2026-06-12T09:00:00.130000",
                "volume": "1",
                "bid_price": "0",
                "ask_price": "0",
                "tick_type": "1",
            }
            _write_tick_csv(
                path,
                [
                    {**base, "close": "18000"},
                    {**base, "close": "18001"},
                ],
            )
            with self.assertNoLogs("trading_backtest.loader", level="WARNING"):
                ticks = load_ticks_csv(path)
            self.assertEqual(len(ticks), 2)

    def test_non_positive_close_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "TXFR1_2026-06-12.csv"
            _write_tick_csv(
                path,
                [
                    {
                        "datetime": "2026-06-12T09:00:00",
                        "close": "0",
                        "volume": "1",
                        "bid_price": "0",
                        "ask_price": "0",
                        "tick_type": "0",
                    }
                ],
            )
            with self.assertLogs("trading_backtest.loader", level="WARNING") as logs:
                load_ticks_csv(path)
            self.assertTrue(any("non-positive close" in m for m in logs.output))

    def test_large_price_jump_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "TXFR1_2026-06-12.csv"
            _write_tick_csv(
                path,
                [
                    {
                        "datetime": "2026-06-12T09:00:00",
                        "close": "18000",
                        "volume": "1",
                        "bid_price": "0",
                        "ask_price": "0",
                        "tick_type": "0",
                    },
                    {
                        "datetime": "2026-06-12T09:00:01",
                        "close": "20000",
                        "volume": "1",
                        "bid_price": "0",
                        "ask_price": "0",
                        "tick_type": "0",
                    },
                ],
            )
            with self.assertLogs("trading_backtest.loader", level="WARNING") as logs:
                load_ticks_csv(path)
            self.assertTrue(any("large price jump" in m for m in logs.output))


class TestKbarGzCache(unittest.TestCase):
    def test_load_kbars_csv_reads_gzip(self):
        bar = KBarRecord(
            datetime.datetime(2026, 6, 22, 9, 0),
            100.0,
            101.0,
            99.0,
            100.5,
            10,
        )
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            plain = kbar_path(cache_dir, "TMFR1", datetime.date(2026, 6, 22))
            gz = kbar_gz_path(cache_dir, "TMFR1", datetime.date(2026, 6, 22))
            save_kbars_csv([bar], plain)
            gz.write_bytes(gzip.compress(plain.read_bytes()))
            plain.unlink()
            loaded = load_kbars_csv(gz)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].ts, bar.ts)
            self.assertAlmostEqual(loaded[0].Close, bar.Close)

    def test_resolve_kbar_path_prefers_plain_over_gz(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            date = datetime.date(2026, 6, 22)
            plain = kbar_path(cache_dir, "TMFR1", date)
            gz = kbar_gz_path(cache_dir, "TMFR1", date)
            plain.write_text("ts,Open,High,Low,Close,Volume\n", encoding="utf-8")
            gz.write_bytes(b"\x1f\x8b")  # not valid csv; plain must win
            self.assertEqual(
                resolve_kbar_path(cache_dir, "TMFR1", date),
                plain,
            )

    def test_iter_kbars_in_range_reads_gz_only_mirror(self):
        bars = [
            KBarRecord(
                datetime.datetime(2026, 6, 22, 9, i),
                100.0 + i,
                101.0,
                99.0,
                100.5,
                10,
            )
            for i in range(3)
        ]
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            date = datetime.date(2026, 6, 22)
            plain = kbar_path(cache_dir, "TMFR1", date)
            gz = kbar_gz_path(cache_dir, "TMFR1", date)
            save_kbars_csv(bars, plain)
            gz.write_bytes(gzip.compress(plain.read_bytes()))
            plain.unlink()
            loaded = iter_kbars_in_range(
                "TMFR1",
                date,
                date,
                cache_dir=cache_dir,
            )
            self.assertEqual(len(loaded), 3)
            self.assertEqual([b.ts for b in loaded], [b.ts for b in bars])


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
