"""K-bar timestamp conversion (simulation vs production API)."""

from __future__ import annotations

import datetime
import gzip
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from storage.kbar_loader import (
    KBarRecord,
    _all_day_kbar_needs_fetch,
    _filter_bars_by_time,
    _kbar_window_needs_fetch,
    download_and_cache_kbars,
    iter_kbars_in_range,
    kbar_cache_satisfies_request,
    kbars_cache_gz_path,
    kbars_cache_path,
    load_kbars_csv,
    kbar_ts_from_ns,
    save_kbars_csv,
)
from storage.tick_loader import _ns_to_taipei_naive, shioaji_ts_from_ns


def _session_kbars(date: datetime.date) -> list[KBarRecord]:
    """One bar per minute from 08:46 through 13:44 (covers 08:45–13:45 window)."""
    start = datetime.datetime.combine(date, datetime.time(8, 46))
    end = datetime.datetime.combine(date, datetime.time(13, 44))
    bars: list[KBarRecord] = []
    cur = start
    while cur <= end:
        bars.append(KBarRecord(cur, 100.0, 101.0, 99.0, 100.0, 10))
        cur += datetime.timedelta(minutes=1)
    return bars


def _write_gz_kbars_only(
    cache_dir: Path, code: str, date: datetime.date, bars: list[KBarRecord]
) -> Path:
    plain = kbars_cache_path(cache_dir, code, date)
    gz = kbars_cache_gz_path(cache_dir, code, date)
    save_kbars_csv(bars, plain)
    gz.write_bytes(gzip.compress(plain.read_bytes()))
    plain.unlink()
    return gz


class TestKbarTsFromNs(unittest.TestCase):
    def test_simulation_wall_clock_as_utc_epoch(self):
        """UAT simulation: 10:26 exchange time is stored as UTC epoch 10:26 (not +8)."""
        wall_as_utc = datetime.datetime(
            2026, 6, 22, 10, 26, 0, tzinfo=datetime.timezone.utc
        )
        ts_ns = int(wall_as_utc.timestamp() * 1_000_000_000)
        dt = kbar_ts_from_ns(ts_ns, simulation=True)
        self.assertEqual(dt, datetime.datetime(2026, 6, 22, 10, 26, 0))

    def test_simulation_old_conversion_would_add_eight_hours(self):
        wall_as_utc = datetime.datetime(
            2026, 6, 22, 10, 26, 0, tzinfo=datetime.timezone.utc
        )
        ts_ns = int(wall_as_utc.timestamp() * 1_000_000_000)
        wrong = _ns_to_taipei_naive(ts_ns)
        self.assertEqual(wrong, datetime.datetime(2026, 6, 22, 18, 26, 0))

    def test_production_true_utc_epoch(self):
        """Production kbars.ts: true UTC epoch -> Taipei naive via +8."""
        true_utc = datetime.datetime(
            2026, 6, 22, 2, 26, 0, tzinfo=datetime.timezone.utc
        )
        ts_ns = int(true_utc.timestamp() * 1_000_000_000)
        dt = kbar_ts_from_ns(ts_ns, simulation=False)
        self.assertEqual(dt, datetime.datetime(2026, 6, 22, 10, 26, 0))

    def test_shioaji_ts_from_ns_matches_kbar_helper(self):
        ts_ns = 1_700_000_000_000_000_000
        self.assertEqual(
            kbar_ts_from_ns(ts_ns, simulation=True),
            shioaji_ts_from_ns(ts_ns, simulation=True),
        )


class TestFilterBarsByTime(unittest.TestCase):
    def test_filters_to_day_session_window(self):
        bars = [
            KBarRecord(datetime.datetime(2026, 6, 18, 8, 44), 1, 1, 1, 1, 1),
            KBarRecord(datetime.datetime(2026, 6, 18, 8, 45), 1, 1, 1, 1, 1),
            KBarRecord(datetime.datetime(2026, 6, 18, 13, 45), 1, 1, 1, 1, 1),
            KBarRecord(datetime.datetime(2026, 6, 18, 13, 46), 1, 1, 1, 1, 1),
        ]
        kept = _filter_bars_by_time(
            bars,
            datetime.time(8, 45),
            datetime.time(13, 45),
        )
        self.assertEqual([b.ts for b in kept], [bars[1].ts, bars[2].ts])

    def test_window_needs_fetch_tolerates_one_minute_edges(self):
        bars = [
            KBarRecord(
                datetime.datetime(2026, 6, 18, 8, 46) + datetime.timedelta(minutes=i),
                1,
                1,
                1,
                1,
                1,
            )
            for i in range((13 * 60 + 44) - (8 * 60 + 46) + 1)
        ]
        self.assertFalse(
            _kbar_window_needs_fetch(
                bars,
                datetime.time(8, 45),
                datetime.time(13, 45),
            )
        )

    def test_window_needs_fetch_on_large_gap(self):
        bars = [
            KBarRecord(datetime.datetime(2026, 6, 18, 8, 45), 1, 1, 1, 1, 1),
            KBarRecord(datetime.datetime(2026, 6, 18, 13, 45), 1, 1, 1, 1, 1),
        ]
        self.assertTrue(
            _kbar_window_needs_fetch(
                bars,
                datetime.time(8, 45),
                datetime.time(13, 45),
            )
        )


class TestDownloadAndCacheKbarsTimeFilter(unittest.TestCase):
    def test_backfill_filters_kbars_after_fetch(self):
        api = MagicMock()
        api.usage.return_value = MagicMock(
            bytes=0, limit_bytes=2_000_000_000, remaining_bytes=1_900_000_000
        )
        contract = MagicMock(code="TXFR1")
        date = datetime.date(2026, 6, 18)
        wall_in = datetime.datetime(2026, 6, 18, 10, 0, tzinfo=datetime.timezone.utc)
        wall_out = datetime.datetime(2026, 6, 18, 15, 0, tzinfo=datetime.timezone.utc)
        api.kbars.return_value = MagicMock(
            ts=[
                int(wall_in.timestamp() * 1_000_000_000),
                int(wall_out.timestamp() * 1_000_000_000),
            ],
            Open=[100.0, 101.0],
            High=[101.0, 102.0],
            Low=[99.0, 100.0],
            Close=[100.5, 101.5],
            Volume=[10, 11],
        )
        with tempfile.TemporaryDirectory() as d:
            cache_dir = Path(d)
            download_and_cache_kbars(
                api,
                contract,
                [date],
                cache_dir=cache_dir,
                simulation=True,
                time_start=datetime.time(8, 45),
                time_end=datetime.time(13, 45),
            )
            from storage.kbar_loader import kbars_cache_path, load_kbars_csv

            bars = load_kbars_csv(kbars_cache_path(cache_dir, "TXFR1", date))
            self.assertEqual(len(bars), 1)
            self.assertEqual(bars[0].ts, datetime.datetime(2026, 6, 18, 10, 0))

    def test_skip_path_does_not_overwrite_existing_tick_cache_mirror(self):
        api = MagicMock()
        api.usage.return_value = MagicMock(
            bytes=0, limit_bytes=2_000_000_000, remaining_bytes=1_900_000_000
        )
        contract = MagicMock(code="TXFR1")
        date = datetime.date(2026, 6, 18)
        with tempfile.TemporaryDirectory() as kd, tempfile.TemporaryDirectory() as td:
            kbar_dir = Path(kd)
            tick_dir = Path(td)
            save_kbars_csv(
                [KBarRecord(datetime.datetime(2026, 6, 18, 9, 0), 1, 1, 1, 1, 1)],
                kbars_cache_path(kbar_dir, "TXFR1", date),
            )
            rich_tick_cache = kbars_cache_path(tick_dir, "TXFR1", date)
            save_kbars_csv(
                [KBarRecord(datetime.datetime(2026, 6, 18, 1, 0), 9, 9, 9, 9, 9)],
                rich_tick_cache,
            )
            download_and_cache_kbars(
                api,
                contract,
                [date],
                cache_dir=kbar_dir,
                mirror_cache_dir=tick_dir,
                overwrite=False,
                simulation=True,
                time_start=datetime.time(8, 45),
                time_end=datetime.time(13, 45),
            )
            bars = load_kbars_csv(rich_tick_cache)
            self.assertEqual(len(bars), 1)
            self.assertEqual(bars[0].ts, datetime.datetime(2026, 6, 18, 1, 0))

    def test_all_day_refetches_session_only_kbar_cache(self):
        api = MagicMock()
        api.usage.return_value = MagicMock(
            bytes=0, limit_bytes=2_000_000_000, remaining_bytes=1_900_000_000
        )
        contract = MagicMock(code="TXFR1")
        date = datetime.date(2026, 6, 18)
        api.kbars.return_value = MagicMock(
            ts=[], Open=[], High=[], Low=[], Close=[], Volume=[]
        )
        with tempfile.TemporaryDirectory() as d:
            cache_dir = Path(d)
            save_kbars_csv(
                [KBarRecord(datetime.datetime(2026, 6, 18, 9, 0), 1, 1, 1, 1, 1)],
                kbars_cache_path(cache_dir, "TXFR1", date),
            )
            download_and_cache_kbars(
                api,
                contract,
                [date],
                cache_dir=cache_dir,
                simulation=True,
                time_start=None,
                time_end=None,
            )
            api.kbars.assert_called_once()
            self.assertTrue(_all_day_kbar_needs_fetch(
                [KBarRecord(datetime.datetime(2026, 6, 18, 9, 0), 1, 1, 1, 1, 1)]
            ))


class TestKbarGzCache(unittest.TestCase):
    def test_iter_kbars_in_range_reads_gz_only_mirror(self):
        bars = [
            KBarRecord(datetime.datetime(2026, 6, 22, 9, 0), 100, 101, 99, 100, 10),
            KBarRecord(datetime.datetime(2026, 6, 22, 9, 1), 101, 102, 100, 101, 11),
        ]
        with tempfile.TemporaryDirectory() as d:
            cache_dir = Path(d)
            date = datetime.date(2026, 6, 22)
            _write_gz_kbars_only(cache_dir, "TMFR1", date, bars)
            loaded = iter_kbars_in_range("TMFR1", date, date, cache_dir=cache_dir)
            self.assertEqual(len(loaded), 2)
            self.assertEqual(loaded[0].Close, 100.0)
            self.assertEqual(loaded[1].Close, 101.0)

    def test_kbar_cache_satisfies_request_reads_gz_only(self):
        date = datetime.date(2026, 6, 22)
        with tempfile.TemporaryDirectory() as d:
            cache_dir = Path(d)
            _write_gz_kbars_only(cache_dir, "TMFR1", date, _session_kbars(date))
            self.assertTrue(
                kbar_cache_satisfies_request(
                    cache_dir,
                    "TMFR1",
                    date,
                    time_start=datetime.time(8, 45),
                    time_end=datetime.time(13, 45),
                )
            )

    def test_download_skips_fetch_when_gz_only_cache_covers_window(self):
        api = MagicMock()
        api.usage.return_value = MagicMock(
            bytes=0, limit_bytes=2_000_000_000, remaining_bytes=1_900_000_000
        )
        contract = MagicMock(code="TXFR1")
        date = datetime.date(2026, 6, 18)
        with tempfile.TemporaryDirectory() as d:
            cache_dir = Path(d)
            _write_gz_kbars_only(cache_dir, "TXFR1", date, _session_kbars(date))
            written = download_and_cache_kbars(
                api,
                contract,
                [date],
                cache_dir=cache_dir,
                overwrite=False,
                simulation=True,
                time_start=datetime.time(8, 45),
                time_end=datetime.time(13, 45),
            )
            api.kbars.assert_not_called()
            self.assertEqual(len(written), 1)
            self.assertTrue(written[0].name.endswith(".csv.gz"))


if __name__ == "__main__":
    unittest.main()
