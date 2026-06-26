"""Tests for data_loader (Phase 0) and injected-clock seam (Phase 1)."""

from __future__ import annotations

import datetime
import gzip
import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from storage.tick_loader import (
    DEFAULT_TICK_RANGE_END,
    DEFAULT_TICK_RANGE_START,
    _window_needs_fetch,
    ReplayTick,
    cache_gz_path,
    cache_path,
    commit_ticks_cache,
    date_range,
    download_and_cache,
    fetch_ticks_for_date,
    iter_replay_ticks,
    list_cached_tick_dates,
    load_merged_tick_cache,
    load_ticks_csv,
    merge_ticks,
    parse_cli_cache_date_range,
    parse_optional_iso_date,
    resolve_cli_tick_cache_dates,
    resolve_tick_cache_dates,
    save_ticks_csv,
    shioaji_historical_ts_from_ns,
)
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
    def test_lists_tick_files_excludes_kbars_and_dedupes_gz(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            d1 = datetime.date(2026, 6, 15)
            d2 = datetime.date(2026, 6, 16)
            save_ticks_csv(
                [ReplayTick(datetime.datetime(2026, 6, 15, 9), "18000", 1, 0)],
                cache_path(root, "TMFR1", d1),
            )
            cache_gz_path(root, "TMFR1", d2).write_bytes(b"not real gzip")
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


class TestBacktestDatesFromCache(unittest.TestCase):
    def test_main_dates_from_cache(self):
        from backtest.__main__ import main

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            dt = datetime.date(2026, 6, 22)
            save_ticks_csv(
                [ReplayTick(datetime.datetime(2026, 6, 22, 9), "18000", 1, 0)],
                cache_path(root, "TMFR1", dt),
            )
            with patch("backtest.__main__.BacktestEngine") as engine_cls:
                rc = main(
                    [
                        "--code",
                        "TMFR1",
                        "--dates-from-cache",
                        "--cache-dir",
                        str(root),
                    ]
                )
            self.assertEqual(rc, 0)
            engine_cls.assert_called_once()
            self.assertEqual(engine_cls.call_args[0][1], [dt])

    def test_main_invalid_from_date_exits_1(self):
        from backtest.__main__ import main

        rc = main(
            [
                "--code",
                "TMFR1",
                "--dates",
                "2026-06-22",
                "--from-date",
                "not-a-date",
            ]
        )
        self.assertEqual(rc, 1)

    def test_main_report_invokes_emit_report(self):
        from backtest.__main__ import main

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            dt = datetime.date(2026, 6, 22)
            save_ticks_csv(
                [ReplayTick(datetime.datetime(2026, 6, 22, 9), "18000", 1, 0)],
                cache_path(root, "TMFR1", dt),
            )
            with patch("backtest.__main__.BacktestEngine") as engine_cls:
                with patch("backtest.__main__.emit_report") as emit_report:
                    with patch(
                        "backtest.__main__.configure_backtest_session_logging"
                    ) as configure_logging:
                        rc = main(
                            [
                                "--code",
                                "TMFR1",
                                "--dates",
                                "2026-06-22",
                                "--cache-dir",
                                str(root),
                                "--report",
                            ]
                        )
            self.assertEqual(rc, 0)
            engine_cls.assert_called_once()
            emit_report.assert_called_once()
            log_path = emit_report.call_args[0][0]
            self.assertEqual(log_path.name, "backtest_TMFR1_20260622.log")
            json_path = emit_report.call_args.kwargs["json_path"]
            self.assertEqual(json_path.name, "backtest_TMFR1_20260622.json")
            self.assertTrue(emit_report.call_args.kwargs["print_report"])
            configure_logging.assert_called_once()
            self.assertEqual(configure_logging.call_args[0][0], str(log_path))
            self.assertTrue(configure_logging.call_args.kwargs["truncate"])

    def test_main_plain_backtest_uses_log_file_from_config(self):
        from backtest.__main__ import main

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            log_path = root / "uat.log"
            dt = datetime.date(2026, 6, 22)
            save_ticks_csv(
                [ReplayTick(datetime.datetime(2026, 6, 22, 9), "18000", 1, 0)],
                cache_path(root, "TMFR1", dt),
            )
            with patch("backtest.__main__.LOG_FILE", str(log_path)):
                with patch("backtest.__main__.BacktestEngine") as engine_cls:
                    with patch("backtest.__main__.configure_backtest_session_logging") as configure_logging:
                        rc = main(
                            [
                                "--code",
                                "TMFR1",
                                "--dates",
                                "2026-06-22",
                                "--cache-dir",
                                str(root),
                            ]
                        )
            self.assertEqual(rc, 0)
            engine_cls.assert_called_once()
            configure_logging.assert_called_once_with(
                str(log_path),
                console_level=None,
                truncate=False,
            )

    def test_cache_dir_output_tag_disambiguates_outside_tick_cache(self):
        from backtest.__main__ import _cache_dir_output_tag

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            outside = root / "runA" / "2026_05"
            outside.mkdir(parents=True)
            self.assertEqual(_cache_dir_output_tag(outside), "runA_2026_05")

    def test_default_report_paths_filtered_cache_appends_date_range(self):
        from backtest.__main__ import default_report_paths
        from storage.cache_paths import DEFAULT_TICK_CACHE_DIR

        month_dir = DEFAULT_TICK_CACHE_DIR / "2026_05"
        dates = [datetime.date(2026, 5, 1), datetime.date(2026, 5, 15)]
        log_path, json_path = default_report_paths(
            dates_from_cache=True,
            code="TMFR1",
            dates=dates,
            cache_dir=month_dir,
            date_range_filtered=True,
        )
        self.assertEqual(log_path.name, "backtest_2026_05_20260501_20260515.log")
        self.assertEqual(json_path.name, "backtest_2026_05_20260501_20260515.json")

    def test_main_dates_from_cache_report_uses_cache_dir_name(self):
        from backtest.__main__ import main

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            tick_root = root / "tick_cache"
            month_dir = tick_root / "2026_05"
            month_dir.mkdir(parents=True)
            dt = datetime.date(2026, 5, 2)
            save_ticks_csv(
                [ReplayTick(datetime.datetime(2026, 5, 2, 9), "18000", 1, 0)],
                cache_path(month_dir, "TMFR1", dt),
            )
            with patch.dict(os.environ, {"FT003_HOLDOUT_UNSEAL": "1"}):
                with patch("backtest.__main__.DEFAULT_TICK_CACHE_DIR", tick_root):
                    with patch("backtest.__main__.BacktestEngine"):
                        with patch("backtest.__main__.emit_report") as emit_report:
                            with patch(
                                "backtest.__main__.configure_backtest_session_logging"
                            ):
                                rc = main(
                                    [
                                        "--code",
                                        "TMFR1",
                                        "--dates-from-cache",
                                        "--cache-dir",
                                        str(month_dir),
                                        "--report",
                                    ]
                                )
            self.assertEqual(rc, 0)
            emit_report.assert_called_once()
            log_path = emit_report.call_args[0][0]
            json_path = emit_report.call_args.kwargs["json_path"]
            self.assertEqual(log_path.name, "backtest_2026_05.log")
            self.assertEqual(json_path.name, "backtest_2026_05.json")
            self.assertTrue(emit_report.call_args.kwargs["print_report"])

    def test_main_dates_from_cache_default_tick_cache_naming(self):
        from backtest.__main__ import main

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            tick_root = root / "tick_cache"
            tick_root.mkdir()
            dt = datetime.date(2026, 6, 22)
            save_ticks_csv(
                [ReplayTick(datetime.datetime(2026, 6, 22, 9), "18000", 1, 0)],
                cache_path(tick_root, "TMFR1", dt),
            )
            with patch("backtest.__main__.DEFAULT_TICK_CACHE_DIR", tick_root):
                with patch("backtest.__main__.BacktestEngine"):
                    with patch("backtest.__main__.emit_report") as emit_report:
                        with patch(
                            "backtest.__main__.configure_backtest_session_logging"
                        ):
                            rc = main(
                                [
                                    "--code",
                                    "TMFR1",
                                    "--dates-from-cache",
                                    "--cache-dir",
                                    str(tick_root),
                                    "--report",
                                ]
                            )
            self.assertEqual(rc, 0)
            emit_report.assert_called_once()
            log_path = emit_report.call_args[0][0]
            json_path = emit_report.call_args.kwargs["json_path"]
            self.assertEqual(log_path.name, "backtest_tick_cache.log")
            self.assertEqual(json_path.name, "backtest_tick_cache.json")

    def test_main_dates_from_cache_filtered_range_suffix(self):
        from backtest.__main__ import main

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            tick_root = root / "tick_cache"
            month_dir = tick_root / "2026_05"
            month_dir.mkdir(parents=True)
            for day in (1, 15):
                dt = datetime.date(2026, 5, day)
                save_ticks_csv(
                    [ReplayTick(datetime.datetime(2026, 5, day, 9), "18000", 1, 0)],
                    cache_path(month_dir, "TMFR1", dt),
                )
            with patch.dict(os.environ, {"FT003_HOLDOUT_UNSEAL": "1"}):
                with patch("backtest.__main__.DEFAULT_TICK_CACHE_DIR", tick_root):
                    with patch("backtest.__main__.BacktestEngine"):
                        with patch("backtest.__main__.emit_report") as emit_report:
                            with patch(
                                "backtest.__main__.configure_backtest_session_logging"
                            ):
                                rc = main(
                                    [
                                        "--code",
                                        "TMFR1",
                                        "--dates-from-cache",
                                        "--cache-dir",
                                        str(month_dir),
                                        "--from-date",
                                        "2026-05-01",
                                        "--to-date",
                                        "2026-05-01",
                                        "--report",
                                    ]
                                )
            self.assertEqual(rc, 0)
            emit_report.assert_called_once()
            log_path = emit_report.call_args[0][0]
            json_path = emit_report.call_args.kwargs["json_path"]
            self.assertEqual(log_path.name, "backtest_2026_05_20260501.log")
            self.assertEqual(json_path.name, "backtest_2026_05_20260501.json")

    def test_main_report_with_custom_log_file_pairs_json_stem(self):
        from backtest.__main__ import main

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            custom_log = root / "custom_run.log"
            dt = datetime.date(2026, 6, 22)
            save_ticks_csv(
                [ReplayTick(datetime.datetime(2026, 6, 22, 9), "18000", 1, 0)],
                cache_path(root, "TMFR1", dt),
            )
            with patch("backtest.__main__.BacktestEngine"):
                with patch("backtest.__main__.emit_report") as emit_report:
                    with patch("backtest.__main__.configure_backtest_session_logging"):
                        rc = main(
                            [
                                "--code",
                                "TMFR1",
                                "--dates",
                                "2026-06-22",
                                "--cache-dir",
                                str(root),
                                "--log-file",
                                str(custom_log),
                                "--report",
                            ]
                        )
            self.assertEqual(rc, 0)
            emit_report.assert_called_once()
            log_path = emit_report.call_args[0][0]
            json_path = emit_report.call_args.kwargs["json_path"]
            self.assertEqual(log_path, custom_log)
            self.assertEqual(json_path.name, "custom_run.json")

    def test_session_logging_writes_audits_before_engine_wiring(self):
        from backtest.__main__ import configure_backtest_session_logging
        from trading_engine.logging_setup import shutdown_async_logging

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "backtest.log"
            configure_backtest_session_logging(str(path), truncate=True)
            logging.getLogger("trading_engine").info("SIGNAL_AUDIT smoke")
            shutdown_async_logging()
            text = path.read_text(encoding="utf-8")
            self.assertIn("SIGNAL_AUDIT", text)

    def test_session_logging_overwrites_previous_run(self):
        from backtest.__main__ import configure_backtest_session_logging
        from trading_engine.logging_setup import shutdown_async_logging

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "backtest.log"
            configure_backtest_session_logging(str(path), truncate=True)
            logging.getLogger("trading_engine").info("first-run-marker")
            shutdown_async_logging()
            configure_backtest_session_logging(str(path), truncate=True)
            logging.getLogger("trading_engine").info("second-run-marker")
            shutdown_async_logging()
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("first-run-marker", text)
            self.assertIn("second-run-marker", text)


if __name__ == "__main__":
    unittest.main()
