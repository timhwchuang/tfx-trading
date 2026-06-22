"""Tests for data_loader (Phase 0) and injected-clock seam (Phase 1)."""

from __future__ import annotations

import datetime
import gzip
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from storage.tick_loader import (
    DEFAULT_TICK_RANGE_END,
    DEFAULT_TICK_RANGE_START,
    _is_legacy_plus8h_tick_candidate,
    _normalize_simulation_ticks_for_window,
    _window_needs_fetch,
    ReplayTick,
    _ns_to_taipei_naive,
    cache_gz_path,
    cache_path,
    commit_ticks_cache,
    date_range,
    download_and_cache,
    fetch_ticks_for_date,
    iter_replay_ticks,
    load_merged_tick_cache,
    load_ticks_csv,
    merge_ticks,
    save_ticks_csv,
    shioaji_ts_from_ns,
)
from tests.test_helpers import make_host


class TestTaipeiNaive(unittest.TestCase):
    def test_ns_to_taipei_naive(self):
        # 2026-06-12 09:00:00 +08:00
        aware = datetime.datetime(
            2026, 6, 12, 9, 0, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=8))
        )
        ts_ns = int(aware.timestamp() * 1_000_000_000)
        dt = _ns_to_taipei_naive(ts_ns)
        self.assertIsNone(dt.tzinfo)
        self.assertEqual(dt, datetime.datetime(2026, 6, 12, 9, 0, 0))


class TestCsvRoundTrip(unittest.TestCase):
    def test_save_load_roundtrip(self):
        ticks = [
            ReplayTick(
                datetime=datetime.datetime(2026, 6, 12, 8, 45, 1),
                close="18000",
                volume=3,
                tick_type=1,
                bid_price=17999.0,
                ask_price=18001.0,
            ),
            ReplayTick(
                datetime=datetime.datetime(2026, 6, 12, 8, 45, 2),
                close="18002",
                volume=5,
                tick_type=2,
            ),
        ]
        with tempfile.TemporaryDirectory() as d:
            path = cache_path(Path(d), "TXFR1", datetime.date(2026, 6, 12))
            n = save_ticks_csv(ticks, path)
            self.assertEqual(n, 2)
            loaded = load_ticks_csv(path)
            self.assertEqual(len(loaded), 2)
            self.assertEqual(loaded[0].close, "18000")
            self.assertEqual(loaded[0].volume, 3)
            self.assertEqual(loaded[1].tick_type, 2)

    def test_iter_replay_ticks_multi_day(self):
        with tempfile.TemporaryDirectory() as d:
            d1 = datetime.date(2026, 6, 11)
            d2 = datetime.date(2026, 6, 12)
            save_ticks_csv(
                [ReplayTick(datetime.datetime(2026, 6, 11, 9, 0), "18000", 1, 0)],
                cache_path(Path(d), "TXFR1", d1),
            )
            save_ticks_csv(
                [ReplayTick(datetime.datetime(2026, 6, 12, 9, 0), "18010", 1, 0)],
                cache_path(Path(d), "TXFR1", d2),
            )
            ticks = list(iter_replay_ticks("TXFR1", [d1, d2], cache_dir=Path(d)))
            self.assertEqual(len(ticks), 2)
            self.assertEqual(ticks[0].close, "18000")
            self.assertEqual(ticks[1].close, "18010")


class TestFetchTicksForDate(unittest.TestCase):
    def test_defaults_to_rangetime_window(self):
        api = MagicMock()
        raw = MagicMock(ts=[1], close=[18000], volume=[1])
        api.ticks.return_value = raw
        contract = MagicMock(code="TXFR1")
        date = datetime.date(2026, 6, 18)
        fetch_ticks_for_date(api, contract, date)
        api.ticks.assert_called_once()
        _, kwargs = api.ticks.call_args
        self.assertEqual(kwargs["timeout"], 30_000)
        self.assertEqual(str(kwargs["query_type"]), "TicksQueryType.RangeTime")
        self.assertEqual(kwargs["time_start"], DEFAULT_TICK_RANGE_START.isoformat())
        self.assertEqual(kwargs["time_end"], DEFAULT_TICK_RANGE_END.isoformat())

    def test_all_day_when_range_disabled(self):
        api = MagicMock()
        raw = MagicMock(ts=[1], close=[18000], volume=[1])
        api.ticks.return_value = raw
        contract = MagicMock(code="TXFR1")
        date = datetime.date(2026, 6, 18)
        fetch_ticks_for_date(api, contract, date, time_start=None, time_end=None)
        _, kwargs = api.ticks.call_args
        self.assertEqual(str(kwargs["query_type"]), "TicksQueryType.AllDay")
        self.assertNotIn("time_start", kwargs)
        self.assertNotIn("time_end", kwargs)

    def test_simulation_ts_uses_wall_clock_not_plus_eight(self):
        wall_as_utc = datetime.datetime(
            2026, 6, 18, 10, 26, 0, tzinfo=datetime.timezone.utc
        )
        ts_ns = int(wall_as_utc.timestamp() * 1_000_000_000)
        api = MagicMock()
        raw = MagicMock(ts=[ts_ns], close=[18000], volume=[1])
        api.ticks.return_value = raw
        contract = MagicMock(code="TXFR1")
        date = datetime.date(2026, 6, 18)
        ticks = fetch_ticks_for_date(api, contract, date, simulation=True)
        self.assertEqual(ticks[0].datetime, datetime.datetime(2026, 6, 18, 10, 26, 0))
        self.assertEqual(
            shioaji_ts_from_ns(ts_ns, simulation=True),
            datetime.datetime(2026, 6, 18, 10, 26, 0),
        )
        self.assertEqual(
            _ns_to_taipei_naive(ts_ns),
            datetime.datetime(2026, 6, 18, 18, 26, 0),
        )

    @patch("storage.tick_loader.time.sleep")
    def test_retries_on_timeout(self, sleep_mock: MagicMock):
        api = MagicMock()
        raw = MagicMock(ts=[1], close=[18000], volume=[1])
        api.ticks.side_effect = [
            TimeoutError("Timeout Topic: api/v1/data/ticks"),
            raw,
        ]
        contract = MagicMock(code="TXFR1")
        date = datetime.date(2026, 6, 18)
        ticks = fetch_ticks_for_date(api, contract, date)
        self.assertEqual(len(ticks), 1)
        self.assertEqual(api.ticks.call_count, 2)
        sleep_mock.assert_called_once()


class TestTickMergeAndGapDetection(unittest.TestCase):
    def test_window_tolerates_one_minute_edge_slip(self):
        near_full = [
            ReplayTick(
                datetime.datetime(2026, 6, 22, 8, 46) + datetime.timedelta(minutes=i),
                str(i),
                1,
                0,
            )
            for i in range((13 * 60 + 44) - (8 * 60 + 46) + 1)
        ]
        self.assertFalse(
            _window_needs_fetch(
                near_full,
                DEFAULT_TICK_RANGE_START,
                DEFAULT_TICK_RANGE_END,
            )
        )

    def test_window_needs_fetch_when_morning_missing(self):
        afternoon = [
            ReplayTick(datetime.datetime(2026, 6, 22, 11, 14), "1", 1, 0),
            ReplayTick(datetime.datetime(2026, 6, 22, 13, 44), "2", 1, 0),
        ]
        self.assertTrue(
            _window_needs_fetch(
                afternoon,
                DEFAULT_TICK_RANGE_START,
                DEFAULT_TICK_RANGE_END,
            )
        )

    def test_window_covered_skips_fetch(self):
        full = [
            ReplayTick(
                datetime.datetime(2026, 6, 22, 8, 45) + datetime.timedelta(minutes=i),
                str(i),
                1,
                0,
            )
            for i in range((13 * 60 + 45) - (8 * 60 + 45) + 1)
        ]
        self.assertFalse(
            _window_needs_fetch(
                full,
                DEFAULT_TICK_RANGE_START,
                DEFAULT_TICK_RANGE_END,
            )
        )

    def test_merge_fills_gap_without_dropping_afternoon(self):
        existing = [
            ReplayTick(datetime.datetime(2026, 6, 22, 11, 14), "old", 1, 0),
        ]
        fetched = [
            ReplayTick(datetime.datetime(2026, 6, 22, 8, 45), "new", 1, 0),
        ]
        merged = merge_ticks(
            existing,
            fetched,
            time_start=DEFAULT_TICK_RANGE_START,
            time_end=DEFAULT_TICK_RANGE_END,
            replace_window=False,
        )
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0].close, "new")
        self.assertEqual(merged[1].close, "old")

    def test_overwrite_range_replaces_inside_window_only(self):
        existing = [
            ReplayTick(datetime.datetime(2026, 6, 22, 8, 45), "keep", 1, 0),
            ReplayTick(datetime.datetime(2026, 6, 22, 11, 14), "drop", 1, 0),
            ReplayTick(datetime.datetime(2026, 6, 22, 15, 0), "night", 1, 0),
        ]
        fetched = [
            ReplayTick(datetime.datetime(2026, 6, 22, 9, 0), "fresh", 1, 0),
        ]
        merged = merge_ticks(
            existing,
            fetched,
            time_start=DEFAULT_TICK_RANGE_START,
            time_end=DEFAULT_TICK_RANGE_END,
            replace_window=True,
        )
        times = [t.datetime for t in merged]
        self.assertIn(datetime.datetime(2026, 6, 22, 9, 0), times)
        self.assertIn(datetime.datetime(2026, 6, 22, 15, 0), times)
        self.assertNotIn(datetime.datetime(2026, 6, 22, 8, 45), times)
        self.assertNotIn(datetime.datetime(2026, 6, 22, 11, 14), times)

    def test_window_needs_fetch_on_large_midday_gap(self):
        gappy = [
            ReplayTick(datetime.datetime(2026, 6, 22, 8, 45), "1", 1, 0),
            ReplayTick(datetime.datetime(2026, 6, 22, 13, 45), "2", 1, 0),
        ]
        self.assertTrue(
            _window_needs_fetch(
                gappy,
                DEFAULT_TICK_RANGE_START,
                DEFAULT_TICK_RANGE_END,
            )
        )


class TestDownloadAndCache(unittest.TestCase):
    def test_skips_when_all_day_plain_csv_exists(self):
        api = MagicMock()
        api.usage.return_value = MagicMock(
            bytes=0, limit_bytes=2_000_000_000, remaining_bytes=1_900_000_000
        )
        contract = MagicMock()
        contract.code = "TXFR1"
        date = datetime.date(2026, 6, 12)
        day_ticks = [
            ReplayTick(
                datetime.datetime(2026, 6, 12, 8, 45) + datetime.timedelta(minutes=i),
                str(i),
                1,
                0,
            )
            for i in range((13 * 60 + 45) - (8 * 60 + 45) + 1)
        ]
        day_ticks.append(
            ReplayTick(datetime.datetime(2026, 6, 12, 15, 0), "night", 1, 0)
        )
        with tempfile.TemporaryDirectory() as d:
            cache_dir = Path(d)
            save_ticks_csv(day_ticks, cache_path(cache_dir, "TXFR1", date))
            written = download_and_cache(
                api,
                contract,
                [date],
                cache_dir=cache_dir,
                time_start=None,
                time_end=None,
            )
            self.assertEqual(len(written), 1)
            api.ticks.assert_not_called()

    def test_all_day_refetches_session_only_cache(self):
        api = MagicMock()
        api.usage.return_value = MagicMock(
            bytes=0, limit_bytes=2_000_000_000, remaining_bytes=1_900_000_000
        )
        contract = MagicMock()
        contract.code = "TXFR1"
        date = datetime.date(2026, 6, 12)
        api.ticks.return_value = MagicMock(
            ts=[],
            close=[],
            volume=[],
            bid_price=[],
            ask_price=[],
            tick_type=[],
        )
        with tempfile.TemporaryDirectory() as d:
            cache_dir = Path(d)
            save_ticks_csv(
                [ReplayTick(datetime.datetime(2026, 6, 12, 9, 0), "1", 1, 0)],
                cache_path(cache_dir, "TXFR1", date),
            )
            download_and_cache(
                api,
                contract,
                [date],
                cache_dir=cache_dir,
                time_start=None,
                time_end=None,
            )
            api.ticks.assert_called_once()

    def test_partial_gzip_triggers_fetch_and_writes_plain_csv(self):
        api = MagicMock()
        api.usage.return_value = MagicMock(
            bytes=0, limit_bytes=2_000_000_000, remaining_bytes=1_900_000_000
        )
        contract = MagicMock()
        contract.code = "TXFR1"
        date = datetime.date(2026, 6, 22)
        morning_ns = int(
            datetime.datetime(
                2026, 6, 22, 8, 45, 0, tzinfo=datetime.timezone.utc
            ).timestamp()
            * 1_000_000_000
        )
        api.ticks.return_value = MagicMock(
            ts=[morning_ns],
            close=[18000],
            volume=[1],
            bid_price=[],
            ask_price=[],
            tick_type=[1],
        )
        with tempfile.TemporaryDirectory() as d:
            cache_dir = Path(d)
            plain = cache_path(cache_dir, "TXFR1", date)
            save_ticks_csv(
                [ReplayTick(datetime.datetime(2026, 6, 22, 11, 14), "1", 1, 0)],
                plain,
            )
            gz = cache_gz_path(cache_dir, "TXFR1", date)
            with plain.open("rb") as src, gzip.open(gz, "wb") as dst:
                dst.writelines(src)
            plain.unlink()
            written = download_and_cache(
                api,
                contract,
                [date],
                cache_dir=cache_dir,
                simulation=True,
            )
            plain = cache_path(cache_dir, "TXFR1", date)
            self.assertEqual(written, [plain])
            self.assertTrue(plain.is_file())
            self.assertFalse(gz.is_file())
            ticks = load_ticks_csv(plain)
            self.assertEqual(len(ticks), 2)
            api.ticks.assert_called_once()

    def test_simulation_merge_normalizes_legacy_plus8_rows(self):
        api = MagicMock()
        api.usage.return_value = MagicMock(
            bytes=0, limit_bytes=2_000_000_000, remaining_bytes=1_900_000_000
        )
        contract = MagicMock()
        contract.code = "TXFR1"
        date = datetime.date(2026, 6, 22)
        morning_ns = int(
            datetime.datetime(
                2026, 6, 22, 8, 45, 0, tzinfo=datetime.timezone.utc
            ).timestamp()
            * 1_000_000_000
        )
        api.ticks.return_value = MagicMock(
            ts=[morning_ns],
            close=[18000],
            volume=[1],
            bid_price=[],
            ask_price=[],
            tick_type=[1],
        )
        with tempfile.TemporaryDirectory() as d:
            cache_dir = Path(d)
            save_ticks_csv(
                [ReplayTick(datetime.datetime(2026, 6, 22, 19, 14), "legacy", 1, 0)],
                cache_path(cache_dir, "TXFR1", date),
            )
            written = download_and_cache(
                api,
                contract,
                [date],
                cache_dir=cache_dir,
                simulation=True,
            )
            self.assertEqual(len(written), 1)
            ticks = load_ticks_csv(cache_path(cache_dir, "TXFR1", date))
            times = [t.datetime for t in ticks]
            self.assertIn(datetime.datetime(2026, 6, 22, 11, 14), times)
            self.assertNotIn(datetime.datetime(2026, 6, 22, 19, 14), times)

    def test_simulation_legacy_skip_persists_normalized_timestamps(self):
        api = MagicMock()
        api.usage.return_value = MagicMock(
            bytes=0, limit_bytes=2_000_000_000, remaining_bytes=1_900_000_000
        )
        contract = MagicMock()
        contract.code = "TXFR1"
        date = datetime.date(2026, 6, 22)
        full_day = [
            ReplayTick(
                datetime.datetime(2026, 6, 22, 16, 45) + datetime.timedelta(minutes=i),
                str(i),
                1,
                0,
            )
            for i in range((21 * 60 + 45) - (16 * 60 + 45) + 1)
        ]
        with tempfile.TemporaryDirectory() as d:
            cache_dir = Path(d)
            save_ticks_csv(full_day, cache_path(cache_dir, "TXFR1", date))
            written = download_and_cache(
                api,
                contract,
                [date],
                cache_dir=cache_dir,
                simulation=True,
            )
            self.assertEqual(len(written), 1)
            api.ticks.assert_not_called()
            ticks = load_ticks_csv(cache_path(cache_dir, "TXFR1", date))
            self.assertTrue(
                all(
                    DEFAULT_TICK_RANGE_START
                    <= t.datetime.time()
                    <= DEFAULT_TICK_RANGE_END
                    for t in ticks
                )
            )

    def test_evening_tick_not_shifted_when_day_session_present(self):
        ticks = [
            ReplayTick(datetime.datetime(2026, 6, 22, 9, 0), "day", 1, 0),
            ReplayTick(datetime.datetime(2026, 6, 22, 17, 0), "night", 1, 0),
        ]
        normalized = _normalize_simulation_ticks_for_window(
            ticks,
            time_start=DEFAULT_TICK_RANGE_START,
            time_end=DEFAULT_TICK_RANGE_END,
        )
        times = [t.datetime for t in normalized]
        self.assertIn(datetime.datetime(2026, 6, 22, 9, 0), times)
        self.assertIn(datetime.datetime(2026, 6, 22, 17, 0), times)
        self.assertEqual(len(normalized), 2)

    def test_production_mode_skips_legacy_normalization_on_load(self):
        ticks = [
            ReplayTick(datetime.datetime(2026, 6, 22, 9, 0), "day", 1, 0),
            ReplayTick(datetime.datetime(2026, 6, 22, 19, 14), "legacy", 1, 0),
        ]
        with tempfile.TemporaryDirectory() as d:
            cache_dir = Path(d)
            date = datetime.date(2026, 6, 22)
            save_ticks_csv(ticks, cache_path(cache_dir, "TXFR1", date))
            from storage.tick_loader import tick_cache_satisfies_request

            self.assertFalse(
                tick_cache_satisfies_request(
                    cache_dir,
                    "TXFR1",
                    date,
                    time_start=DEFAULT_TICK_RANGE_START,
                    time_end=DEFAULT_TICK_RANGE_END,
                    simulation=False,
                )
            )
            loaded = load_merged_tick_cache(cache_dir, "TXFR1", date)
            self.assertIn(datetime.datetime(2026, 6, 22, 19, 14), [t.datetime for t in loaded])

    def test_legacy_shifts_when_shifted_time_near_but_not_duplicate(self):
        legacy = ReplayTick(datetime.datetime(2026, 6, 22, 19, 14), "legacy", 1, 0)
        morning = ReplayTick(datetime.datetime(2026, 6, 22, 11, 14, 39), "morning", 1, 0)
        self.assertTrue(
            _is_legacy_plus8h_tick_candidate(
                legacy,
                time_start=DEFAULT_TICK_RANGE_START,
                time_end=DEFAULT_TICK_RANGE_END,
                all_ticks=[legacy, morning],
            )
        )
        normalized = _normalize_simulation_ticks_for_window(
            [legacy, morning],
            time_start=DEFAULT_TICK_RANGE_START,
            time_end=DEFAULT_TICK_RANGE_END,
        )
        self.assertIn(datetime.datetime(2026, 6, 22, 11, 14), [t.datetime for t in normalized])
        self.assertNotIn(datetime.datetime(2026, 6, 22, 19, 14), [t.datetime for t in normalized])

    def test_merged_plain_and_gzip_used_for_gap_backfill(self):
        api = MagicMock()
        api.usage.return_value = MagicMock(
            bytes=0, limit_bytes=2_000_000_000, remaining_bytes=1_900_000_000
        )
        contract = MagicMock()
        contract.code = "TXFR1"
        date = datetime.date(2026, 6, 22)
        morning_ns = int(
            datetime.datetime(
                2026, 6, 22, 8, 45, 0, tzinfo=datetime.timezone.utc
            ).timestamp()
            * 1_000_000_000
        )
        api.ticks.return_value = MagicMock(
            ts=[morning_ns],
            close=[18000],
            volume=[1],
            bid_price=[],
            ask_price=[],
            tick_type=[1],
        )
        with tempfile.TemporaryDirectory() as d:
            cache_dir = Path(d)
            plain = cache_path(cache_dir, "TXFR1", date)
            save_ticks_csv(
                [ReplayTick(datetime.datetime(2026, 6, 22, 8, 45), "plain", 1, 0)],
                plain,
            )
            gz = cache_gz_path(cache_dir, "TXFR1", date)
            afternoon = cache_dir / "afternoon.csv"
            save_ticks_csv(
                [ReplayTick(datetime.datetime(2026, 6, 22, 11, 14), "gz", 1, 0)],
                afternoon,
            )
            with afternoon.open("rb") as src, gzip.open(gz, "wb") as dst:
                dst.writelines(src)
            afternoon.unlink()
            download_and_cache(
                api,
                contract,
                [date],
                cache_dir=cache_dir,
                simulation=True,
            )
            merged = load_merged_tick_cache(cache_dir, "TXFR1", date)
            closes = {t.close for t in merged}
            self.assertIn("gz", closes)
            self.assertGreaterEqual(len(merged), 2)
            self.assertFalse(gz.is_file())

    def test_commit_ticks_cache_keeps_gzip_on_write_failure(self):
        with tempfile.TemporaryDirectory() as d:
            cache_dir = Path(d)
            date = datetime.date(2026, 6, 22)
            staging = cache_dir / "staging.csv"
            save_ticks_csv(
                [ReplayTick(datetime.datetime(2026, 6, 22, 11, 14), "1", 1, 0)],
                staging,
            )
            gz = cache_gz_path(cache_dir, "TXFR1", date)
            with staging.open("rb") as src, gzip.open(gz, "wb") as dst:
                dst.writelines(src)
            staging.unlink()
            with patch(
                "storage.tick_loader.save_ticks_csv",
                side_effect=OSError("disk full"),
            ):
                with self.assertRaises(OSError):
                    commit_ticks_cache(
                        cache_dir,
                        "TXFR1",
                        date,
                        [ReplayTick(datetime.datetime(2026, 6, 22, 8, 45), "2", 1, 0)],
                    )
            self.assertTrue(gz.is_file())


class TestDateRange(unittest.TestCase):
    def test_inclusive(self):
        days = date_range(datetime.date(2026, 6, 10), datetime.date(2026, 6, 12))
        self.assertEqual(len(days), 3)


class TestInjectedClock(unittest.TestCase):
    def test_record_tick_arrival_uses_injected_clock(self):
        host = make_host()
        host._clock = MagicMock(return_value=12345.0)
        host._record_tick_arrival(
            100, datetime.datetime(2026, 6, 12, 9, 0), tick_type=1
        )
        self.assertEqual(host._last_tick_wall_time, 12345.0)
        host._clock.assert_called()

    def test_pending_timeout_uses_injected_clock(self):
        from config import PENDING_TIMEOUT_SEC

        host = make_host()
        clock_value = {"t": 1000.0}
        host._clock = lambda: clock_value["t"]
        host.is_pending = True
        host.pending_since = 1000.0
        host.pending_trade = None
        # not yet timed out
        host._check_pending_timeout()
        self.assertTrue(host.is_pending)
        # advance past timeout → no trade object → resets pending
        clock_value["t"] = 1000.0 + PENDING_TIMEOUT_SEC + 1
        host._check_pending_timeout()
        self.assertFalse(host.is_pending)

    def test_default_clock_is_time_time(self):
        import time

        host = make_host()
        self.assertIs(host._clock, time.time)

    def test_today_prefers_tick_date(self):
        host = make_host()
        self.assertEqual(host._today(), datetime.date.today())
        host._last_tick_exchange_dt = datetime.datetime(2020, 1, 2, 9, 0)
        self.assertEqual(host._today(), datetime.date(2020, 1, 2))


if __name__ == "__main__":
    unittest.main()
