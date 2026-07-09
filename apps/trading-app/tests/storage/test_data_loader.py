"""Tests for data_loader (Phase 0) and injected-clock seam (Phase 1)."""

from __future__ import annotations

import datetime
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from storage.tick_loader import (
    DEFAULT_TICK_RANGE_END,
    DEFAULT_TICK_RANGE_START,
    _window_needs_fetch,
    ReplayTick,
    cache_path,
    date_range,
    download_and_cache,
    fetch_calendar_day_ticks,
    fetch_ticks_for_date,
    iter_replay_ticks,
    list_cached_tick_dates,
    load_ticks_csv,
    load_merged_tick_cache,
    merge_ticks,
    parse_cli_cache_date_range,
    parse_optional_iso_date,
    resolve_cli_tick_cache_dates,
    resolve_tick_cache_dates,
    save_ticks_csv,
)
from trading_engine.calendar.shioaji_ts import shioaji_historical_ts_from_ns
from tests.test_helpers import make_host


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
        raw = MagicMock(ts=[1], close=[18000], volume=[1], bid_price=[], ask_price=[], tick_type=[])
        api.ticks.return_value = raw
        contract = MagicMock(code="TXFR1")
        date = datetime.date(2026, 6, 18)
        with patch(
            "storage.tick_loader._taipei_today",
            return_value=datetime.date(2026, 6, 18),
        ):
            fetch_ticks_for_date(api, contract, date, time_start=None, time_end=None)
        _, kwargs = api.ticks.call_args
        self.assertEqual(str(kwargs["query_type"]), "TicksQueryType.AllDay")
        self.assertNotIn("time_start", kwargs)
        self.assertNotIn("time_end", kwargs)
        # D+1 is future relative to patched today → only one AllDay call
        self.assertEqual(api.ticks.call_count, 1)

    def test_calendar_day_excludes_prior_evening_from_allday_d(self):
        api = MagicMock()
        contract = MagicMock(code="TMFR1")
        query_date = datetime.date(2026, 7, 1)

        def _ns(y, m, d, h, mi, s=0):
            dt = datetime.datetime(y, m, d, h, mi, s, tzinfo=datetime.timezone.utc)
            return int(dt.timestamp() * 1_000_000_000)

        def _ticks_side_effect(**kwargs):
            d = kwargs["date"]
            if d == "2026-07-01":
                ts = [
                    _ns(2026, 6, 30, 15, 0),
                    _ns(2026, 6, 30, 23, 59),
                    _ns(2026, 7, 1, 0, 0),
                    _ns(2026, 7, 1, 13, 44),
                ]
            else:
                ts = []
            return MagicMock(
                ts=ts,
                close=[18000.0] * len(ts),
                volume=[1] * len(ts),
                bid_price=[],
                ask_price=[],
                tick_type=[],
            )

        api.ticks.side_effect = _ticks_side_effect
        with patch(
            "storage.tick_loader._taipei_today",
            return_value=datetime.date(2026, 7, 2),
        ):
            ticks = fetch_calendar_day_ticks(api, contract, query_date)
        self.assertEqual(len(ticks), 2)
        self.assertEqual(ticks[0].datetime, datetime.datetime(2026, 7, 1, 0, 0))
        self.assertEqual(ticks[1].datetime, datetime.datetime(2026, 7, 1, 13, 44))
        for t in ticks:
            self.assertEqual(t.datetime.date(), query_date)

    def test_calendar_day_includes_same_day_night_from_allday_d_plus_1(self):
        api = MagicMock()
        contract = MagicMock(code="TMFR1")
        query_date = datetime.date(2026, 7, 1)

        def _ns(y, m, d, h, mi, s=0):
            dt = datetime.datetime(y, m, d, h, mi, s, tzinfo=datetime.timezone.utc)
            return int(dt.timestamp() * 1_000_000_000)

        def _ticks_side_effect(**kwargs):
            d = kwargs["date"]
            if d == "2026-07-01":
                ts = [
                    _ns(2026, 6, 30, 15, 0),
                    _ns(2026, 7, 1, 9, 0),
                ]
            elif d == "2026-07-02":
                ts = [
                    _ns(2026, 7, 1, 15, 0),
                    _ns(2026, 7, 1, 22, 0),
                    _ns(2026, 7, 2, 0, 30),
                ]
            else:
                ts = []
            return MagicMock(
                ts=ts,
                close=[18000.0] * len(ts),
                volume=[1] * len(ts),
                bid_price=[],
                ask_price=[],
                tick_type=[],
            )

        api.ticks.side_effect = _ticks_side_effect
        with patch(
            "storage.tick_loader._taipei_today",
            return_value=datetime.date(2026, 7, 2),
        ):
            ticks = fetch_calendar_day_ticks(api, contract, query_date)
        self.assertEqual(
            [t.datetime for t in ticks],
            [
                datetime.datetime(2026, 7, 1, 9, 0),
                datetime.datetime(2026, 7, 1, 15, 0),
                datetime.datetime(2026, 7, 1, 22, 0),
            ],
        )
        self.assertEqual(api.ticks.call_count, 2)

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
            shioaji_historical_ts_from_ns(ts_ns),
            datetime.datetime(2026, 6, 18, 10, 26, 0),
        )
        # Negative reference: the old +8h decode would have produced 18:26 (wrong).
        wrong_plus8 = datetime.datetime.fromtimestamp(
            ts_ns / 1_000_000_000,
            datetime.timezone(datetime.timedelta(hours=8)),
        ).replace(tzinfo=None)
        self.assertEqual(wrong_plus8, datetime.datetime(2026, 6, 18, 18, 26, 0))
        self.assertNotEqual(wrong_plus8, ticks[0].datetime)

    def test_production_tick_ts_uses_wall_clock_not_plus_eight(self):
        """Production api.ticks: same wall-as-UTC encoding as simulation."""
        wall_as_utc = datetime.datetime(
            2026, 6, 25, 10, 26, 0, tzinfo=datetime.timezone.utc
        )
        ts_ns = int(wall_as_utc.timestamp() * 1_000_000_000)
        api = MagicMock()
        raw = MagicMock(ts=[ts_ns], close=[18000], volume=[1])
        api.ticks.return_value = raw
        contract = MagicMock(code="TXFR1")
        date = datetime.date(2026, 6, 25)
        ticks = fetch_ticks_for_date(api, contract, date, simulation=False)
        self.assertEqual(ticks[0].datetime, datetime.datetime(2026, 6, 25, 10, 26, 0))
        self.assertEqual(
            shioaji_historical_ts_from_ns(ts_ns),
            datetime.datetime(2026, 6, 25, 10, 26, 0),
        )
        # Negative reference: the old +8h decode would have produced 18:26 (wrong).
        wrong_plus8 = datetime.datetime.fromtimestamp(
            ts_ns / 1_000_000_000,
            datetime.timezone(datetime.timedelta(hours=8)),
        ).replace(tzinfo=None)
        self.assertEqual(wrong_plus8, datetime.datetime(2026, 6, 25, 18, 26, 0))
        self.assertNotEqual(wrong_plus8, ticks[0].datetime)

    @patch("storage.tick_loader.time.sleep")
    def test_retries_on_timeout(self, sleep_mock: MagicMock):
        api = MagicMock()
        wall_as_utc = datetime.datetime(
            2026, 6, 18, 10, 0, 0, tzinfo=datetime.timezone.utc
        )
        ts_ns = int(wall_as_utc.timestamp() * 1_000_000_000)
        raw = MagicMock(ts=[ts_ns], close=[18000], volume=[1])
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
            ReplayTick(datetime.datetime(2026, 6, 12, 0, 0), "dawn0", 1, 0),
            ReplayTick(datetime.datetime(2026, 6, 12, 9, 0), "open", 1, 0),
        ]
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

    def test_all_day_empty_does_not_write_file(self):
        api = MagicMock()
        api.usage.return_value = MagicMock(
            bytes=0, limit_bytes=2_000_000_000, remaining_bytes=1_900_000_000
        )
        contract = MagicMock()
        contract.code = "TXFR1"
        date = datetime.date(2026, 6, 14)  # Sunday
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
            with patch(
                "storage.tick_loader._taipei_today",
                return_value=datetime.date(2026, 6, 15),
            ):
                written = download_and_cache(
                    api,
                    contract,
                    [date],
                    cache_dir=cache_dir,
                    time_start=None,
                    time_end=None,
                )
            self.assertEqual(written, [])
            self.assertFalse(cache_path(cache_dir, "TXFR1", date).exists())
            self.assertEqual(load_merged_tick_cache(cache_dir, "TXFR1", date), [])


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
        host.pending_intent = "entry"
        host.pending_since = 1000.0
        host.pending_trade = None
        # not yet timed out → still in fast (callback) wait.
        host._check_pending_timeout()
        self.assertTrue(host.is_pending)
        # advance past timeout → the injected clock drives the timeout. P0-5: an
        # ENTRY is NEVER resolved as a clean no-fill from a flat snapshot (a stale
        # flat read is not proof of non-fill). Timeout = UNKNOWN → enter SETTLING
        # with the order still in flight (no re-arm). The settle-timeout later
        # routes entry uncertainty to HALT, never back to a re-armable clear.
        clock_value["t"] = 1000.0 + PENDING_TIMEOUT_SEC + 1
        host._check_pending_timeout()
        self.assertTrue(host.is_pending)
        self.assertTrue(host._settling)

    def test_default_clock_is_time_time(self):
        import time

        host = make_host()
        self.assertIs(host._clock, time.time)

    def test_today_prefers_tick_date(self):
        host = make_host()
        self.assertEqual(host._today(), datetime.date.today())
        host._last_tick_exchange_dt = datetime.datetime(2020, 1, 2, 9, 0)
        self.assertEqual(host._today(), datetime.date(2020, 1, 2))


class TestListCachedTickDates(unittest.TestCase):
    def test_lists_tick_files_excludes_kbars_and_gz(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            d1 = datetime.date(2026, 6, 15)
            d2 = datetime.date(2026, 6, 16)
            save_ticks_csv(
                [ReplayTick(datetime.datetime(2026, 6, 15, 9), "18000", 1, 0)],
                cache_path(root, "TMFR1", d1),
            )
            save_ticks_csv(
                [ReplayTick(datetime.datetime(2026, 6, 16, 9), "18010", 1, 0)],
                cache_path(root, "TMFR1", d2),
            )
            (root / "TMFR1_2026-06-17.csv.gz").write_bytes(b"not real gzip")
            (root / "TMFR1_kbars_2026-06-15.csv").write_text("skip", encoding="utf-8")
            (root / "TXFR1_2026-06-15.csv").write_text("skip", encoding="utf-8")

            dates = list_cached_tick_dates("TMFR1", root)
            self.assertEqual(dates, [d1, d2])

    def test_resolve_from_cache_with_range(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for day in (15, 16, 17):
                dt = datetime.date(2026, 6, day)
                save_ticks_csv(
                    [ReplayTick(datetime.datetime(2026, 6, day, 9), "18000", 1, 0)],
                    cache_path(root, "TMFR1", dt),
                )
            dates = resolve_tick_cache_dates(
                explicit=None,
                from_cache=True,
                code="TMFR1",
                cache_dir=root,
                start=datetime.date(2026, 6, 16),
                end=datetime.date(2026, 6, 16),
            )
            self.assertEqual(dates, [datetime.date(2026, 6, 16)])

    def test_resolve_from_cache_empty_raises(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                resolve_tick_cache_dates(
                    explicit=None,
                    from_cache=True,
                    code="TMFR1",
                    cache_dir=Path(d),
                )

    def test_parse_optional_iso_date_invalid_raises(self):
        with self.assertRaises(ValueError) as ctx:
            parse_optional_iso_date("not-a-date", label="--from-date")
        self.assertIn("--from-date", str(ctx.exception))

    def test_parse_cli_cache_date_range_rejects_without_from_cache(self):
        with self.assertRaises(ValueError) as ctx:
            parse_cli_cache_date_range(
                from_date="2026-06-01",
                to_date="",
                dates_from_cache=False,
            )
        self.assertIn("--dates-from-cache", str(ctx.exception))

    def test_parse_cli_cache_date_range_rejects_inverted_range(self):
        with self.assertRaises(ValueError):
            parse_cli_cache_date_range(
                from_date="2026-06-30",
                to_date="2026-06-01",
                dates_from_cache=True,
            )

    def test_resolve_cli_invalid_from_date_returns_error_not_traceback(self):
        with self.assertRaises(ValueError) as ctx:
            resolve_cli_tick_cache_dates(
                explicit=["2026-06-22"],
                from_cache=False,
                code="TMFR1",
                cache_dir="/tmp",
                from_date="bad",
            )
        self.assertIn("--from-date", str(ctx.exception))


if __name__ == "__main__":
    import unittest
    unittest.main()
