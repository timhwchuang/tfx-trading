"""Tests for P0-11 tick archiver (plain CSV only)."""

from __future__ import annotations

import datetime
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from storage.tick_loader import (
    ReplayTick,
    cache_path,
    load_ticks_csv,
    resolve_tick_cache_path,
    save_ticks_csv,
)
from storage.tick_archiver import (
    TickArchiveRecord,
    TickArchiver,
    tick_to_archive_record,
)
from trading_engine.core.types import TickSnapshot


def _record(
    dt: datetime.datetime,
    *,
    close: str = "18000",
    volume: int = 1,
    tick_type: int = 1,
) -> TickArchiveRecord:
    return TickArchiveRecord(
        datetime=dt,
        close=close,
        volume=volume,
        tick_type=tick_type,
        bid_price=17999.0,
        ask_price=18001.0,
    )


class TestResolveTickCachePath(unittest.TestCase):
    def test_resolves_plain_csv_when_present(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            date = datetime.date(2026, 6, 12)
            plain = cache_path(root, "TXFR1", date)
            save_ticks_csv(
                [ReplayTick(datetime.datetime(2026, 6, 12, 9), "18000", 1, 0)],
                plain,
            )
            resolved = resolve_tick_cache_path(root, "TXFR1", date)
            self.assertEqual(resolved, plain)

    def test_returns_none_when_missing(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            date = datetime.date(2026, 6, 12)
            self.assertIsNone(resolve_tick_cache_path(root, "TXFR1", date))


class TestTickArchiver(unittest.TestCase):
    def test_enqueue_flush_shutdown(self):
        with tempfile.TemporaryDirectory() as d:
            archiver = TickArchiver(
                "TXFR1",
                cache_dir=Path(d),
                flush_batch=2,
                flush_interval_sec=0.05,
                queue_maxsize=100,
            )
            archiver.start()
            archiver.enqueue(
                _record(datetime.datetime(2026, 6, 12, 8, 45, 1))
            )
            archiver.enqueue(
                _record(datetime.datetime(2026, 6, 12, 8, 45, 2), close="18001")
            )
            time.sleep(0.2)
            archiver.shutdown()

            path = cache_path(Path(d), "TXFR1", datetime.date(2026, 6, 12))
            self.assertTrue(path.is_file())
            loaded = load_ticks_csv(path)
            self.assertEqual(len(loaded), 2)
            self.assertEqual(loaded[1].close, "18001")
            self.assertEqual(archiver.written, 2)
            self.assertEqual(archiver.dropped, 0)

    def test_day_rotation_keeps_plain_csv(self):
        with tempfile.TemporaryDirectory() as d:
            archiver = TickArchiver(
                "TXFR1",
                cache_dir=Path(d),
                flush_batch=1,
                flush_interval_sec=0.05,
            )
            archiver.start()
            archiver.enqueue(
                _record(datetime.datetime(2026, 6, 11, 13, 44, 59))
            )
            archiver.enqueue(
                _record(datetime.datetime(2026, 6, 12, 8, 45, 0))
            )
            time.sleep(0.25)
            archiver.shutdown()

            root = Path(d)
            old_plain = cache_path(root, "TXFR1", datetime.date(2026, 6, 11))
            new_plain = cache_path(root, "TXFR1", datetime.date(2026, 6, 12))
            self.assertTrue(old_plain.is_file())
            self.assertTrue(new_plain.is_file())
            self.assertFalse(Path(str(old_plain) + ".gz").is_file())
            self.assertEqual(len(load_ticks_csv(old_plain)), 1)
            self.assertEqual(len(load_ticks_csv(new_plain)), 1)

    def test_queue_full_drops_without_blocking(self):
        with tempfile.TemporaryDirectory() as d:
            archiver = TickArchiver(
                "TXFR1",
                cache_dir=Path(d),
                queue_maxsize=1,
                flush_batch=1000,
                flush_interval_sec=60.0,
            )
            archiver.start()
            archiver.enqueue(_record(datetime.datetime(2026, 6, 12, 9, 0)))
            archiver.enqueue(_record(datetime.datetime(2026, 6, 12, 9, 0, 1)))
            archiver.enqueue(_record(datetime.datetime(2026, 6, 12, 9, 0, 2)))
            time.sleep(0.05)
            archiver.shutdown()
            self.assertGreaterEqual(archiver.dropped, 1)

    def test_interval_flush_during_continuous_stream(self):
        """Time-based flush must fire even when queue never empties."""
        with tempfile.TemporaryDirectory() as d:
            archiver = TickArchiver(
                "TXFR1",
                cache_dir=Path(d),
                flush_batch=500,
                flush_interval_sec=0.1,
                queue_maxsize=100,
            )
            archiver.start()
            base = datetime.datetime(2026, 6, 12, 9, 0)
            for i in range(5):
                archiver.enqueue(_record(base.replace(second=i)))
            time.sleep(0.25)
            path = cache_path(Path(d), "TXFR1", datetime.date(2026, 6, 12))
            self.assertTrue(path.is_file())
            self.assertEqual(len(load_ticks_csv(path)), 5)
            archiver.shutdown()

    def test_enqueue_tick_from_mock(self):
        tick = MagicMock()
        tick.datetime = datetime.datetime(2026, 6, 12, 9, 0)
        tick.close = "18010"
        tick.volume = 4
        tick.bid_price = 18009.0
        tick.ask_price = 18011.0

        with tempfile.TemporaryDirectory() as d:
            archiver = TickArchiver(
                "TXFR1",
                cache_dir=Path(d),
                flush_batch=1,
                flush_interval_sec=0.05,
            )
            archiver.start()
            archiver.enqueue_tick(tick, tick_type=2)
            time.sleep(0.15)
            archiver.shutdown()

            loaded = load_ticks_csv(
                cache_path(Path(d), "TXFR1", datetime.date(2026, 6, 12))
            )
            self.assertEqual(loaded[0].tick_type, 2)
            self.assertEqual(loaded[0].volume, 4)

    def test_enqueue_tick_snapshot_live_path(self):
        """Live Shioaji adapter passes TickSnapshot (exchange_dt/price), not .datetime/.close."""
        snap = TickSnapshot(
            ts=int(datetime.datetime(2026, 6, 22, 10, 0, 0).timestamp()),
            price=48100.0,
            volume=7,
            tick_type=1,
            exchange_dt=datetime.datetime(2026, 6, 22, 10, 0, 0),
        )
        record = tick_to_archive_record(snap, tick_type=2)
        self.assertEqual(record.close, "48100.0")
        self.assertEqual(record.tick_type, 2)

        with tempfile.TemporaryDirectory() as d:
            archiver = TickArchiver(
                "TXFR1",
                cache_dir=Path(d),
                flush_batch=1,
                flush_interval_sec=0.05,
            )
            archiver.start()
            archiver.enqueue_tick(snap, tick_type=2)
            time.sleep(0.15)
            archiver.shutdown()

            self.assertEqual(archiver.written, 1)
            loaded = load_ticks_csv(
                cache_path(Path(d), "TXFR1", datetime.date(2026, 6, 22))
            )
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].close, "48100.0")
            self.assertEqual(loaded[0].tick_type, 2)


if __name__ == "__main__":
    unittest.main()
