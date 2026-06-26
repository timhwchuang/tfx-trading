"""Tests for Shioaji historical ts decode (SSOT)."""

from __future__ import annotations

import datetime
import unittest

from trading_engine.calendar.shioaji_ts import shioaji_historical_ts_from_ns


class TestShioajiHistoricalTs(unittest.TestCase):
    def test_wall_clock_from_utc_epoch(self):
        wall = datetime.datetime(2026, 6, 25, 8, 45, 0, tzinfo=datetime.timezone.utc)
        ts_ns = int(wall.timestamp() * 1_000_000_000)
        self.assertEqual(
            shioaji_historical_ts_from_ns(ts_ns),
            datetime.datetime(2026, 6, 25, 8, 45, 0),
        )

    def test_plus_eight_decode_is_wrong_for_historical(self):
        wall = datetime.datetime(2026, 6, 25, 8, 45, 0, tzinfo=datetime.timezone.utc)
        ts_ns = int(wall.timestamp() * 1_000_000_000)
        taiwan = datetime.timezone(datetime.timedelta(hours=8))
        wrong = datetime.datetime.fromtimestamp(ts_ns / 1e9, taiwan).replace(tzinfo=None)
        self.assertEqual(wrong, datetime.datetime(2026, 6, 25, 16, 45, 0))
        self.assertNotEqual(wrong, shioaji_historical_ts_from_ns(ts_ns))


if __name__ == "__main__":
    unittest.main()
