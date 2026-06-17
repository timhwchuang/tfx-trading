"""Loader validation and tick normalization tests."""

from __future__ import annotations

import datetime
import logging
import tempfile
import unittest
from pathlib import Path

from trading_backtest.loader import load_ticks_csv


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

    def test_duplicate_timestamp_warns(self):
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
            with self.assertLogs("trading_backtest.loader", level="WARNING") as logs:
                ticks = load_ticks_csv(path)
            self.assertEqual(len(ticks), 2)
            self.assertTrue(any("duplicate timestamp" in m for m in logs.output))

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


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
