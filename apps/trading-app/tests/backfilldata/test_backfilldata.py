"""Tests for backfilldata CLI and orchestration."""

from __future__ import annotations

import datetime
import gzip
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backfilldata.core import (
    BackfillError,
    BackfillResult,
    backfill_dates,
    parse_date_args,
    resolve_contract,
    validate_kbar_day_count,
    validate_past_dates,
    validate_tick_day_count,
)
from storage.kbar_loader import (
    KBarRecord,
    download_and_cache_kbars,
    kbar_path,
    save_kbars_csv,
)
from storage.tick_loader import ReplayTick, cache_gz_path, cache_path, save_ticks_csv


def _mock_api_usage(api: MagicMock) -> None:
    api.usage.return_value = MagicMock(bytes=0, limit_bytes=2_000_000_000, remaining_bytes=1_900_000_000)


def _day_session_minute_count() -> int:
    return (13 * 60 + 45) - (8 * 60 + 45) + 1


def _full_session_kbar_records(date: datetime.date) -> list[KBarRecord]:
    return [
        KBarRecord(
            ts=datetime.datetime(date.year, date.month, date.day, 8, 45)
            + datetime.timedelta(minutes=i),
            Open=100.0,
            High=101.0,
            Low=99.0,
            Close=100.5,
            Volume=10,
        )
        for i in range(_day_session_minute_count())
    ]


def _simulation_kbar_raw(date: datetime.date) -> MagicMock:
    base = datetime.datetime(
        date.year, date.month, date.day, 8, 45, tzinfo=datetime.timezone.utc
    )
    ts = [
        int((base + datetime.timedelta(minutes=i)).timestamp() * 1_000_000_000)
        for i in range(_day_session_minute_count())
    ]
    n = len(ts)
    return MagicMock(
        ts=ts,
        Open=[100.0] * n,
        High=[101.0] * n,
        Low=[99.0] * n,
        Close=[100.5] * n,
        Volume=[10] * n,
    )


def _simulation_tick_raw(date: datetime.date) -> MagicMock:
    base = datetime.datetime(
        date.year, date.month, date.day, 8, 45, tzinfo=datetime.timezone.utc
    )
    ts = [
        int((base + datetime.timedelta(minutes=i)).timestamp() * 1_000_000_000)
        for i in range(_day_session_minute_count())
    ]
    n = len(ts)
    return MagicMock(
        ts=ts,
        close=[18000.0] * n,
        volume=[1] * n,
        bid_price=[17999.0] * n,
        ask_price=[18001.0] * n,
        tick_type=[1] * n,
    )


class TestParseDateArgs(unittest.TestCase):
    def test_single_date(self):
        self.assertEqual(
            parse_date_args(["2026-06-20"]),
            [datetime.date(2026, 6, 20)],
        )

    def test_inclusive_range(self):
        days = parse_date_args(["2026-06-18", "2026-06-20"])
        self.assertEqual(len(days), 3)

    def test_rejects_inverted_range(self):
        with self.assertRaises(BackfillError):
            parse_date_args(["2026-06-20", "2026-06-18"])

    def test_rejects_too_many_tokens(self):
        with self.assertRaises(BackfillError):
            parse_date_args(["2026-06-18", "2026-06-19", "2026-06-20"])


class TestValidatePastDates(unittest.TestCase):
    def test_rejects_today_before_session_close(self):
        today = datetime.date(2026, 6, 22)
        before_close = datetime.datetime(
            2026, 6, 22, 11, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=8))
        )
        with self.assertRaises(BackfillError):
            validate_past_dates([today], today=today, now=before_close)

    def test_accepts_today_after_session_close(self):
        today = datetime.date(2026, 6, 22)
        after_close = datetime.datetime(
            2026, 6, 22, 14, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=8))
        )
        validate_past_dates([today], today=today, now=after_close)

    def test_accepts_today_exactly_at_session_close(self):
        today = datetime.date(2026, 6, 22)
        at_close = datetime.datetime(
            2026, 6, 22, 13, 45, tzinfo=datetime.timezone(datetime.timedelta(hours=8))
        )
        validate_past_dates([today], today=today, now=at_close)

    def test_rejects_future_date(self):
        today = datetime.date(2026, 6, 22)
        with self.assertRaises(BackfillError):
            validate_past_dates([datetime.date(2026, 6, 23)], today=today)

    def test_accepts_yesterday(self):
        today = datetime.date(2026, 6, 22)
        validate_past_dates([datetime.date(2026, 6, 21)], today=today)


class TestValidateTickDayCount(unittest.TestCase):
    def test_rejects_more_than_ten_days(self):
        days = [datetime.date(2026, 6, 1) + datetime.timedelta(days=i) for i in range(11)]
        with self.assertRaises(BackfillError):
            validate_tick_day_count(days)


class TestValidateKbarDayCount(unittest.TestCase):
    def test_rejects_more_than_two_seventy_days(self):
        days = [datetime.date(2026, 1, 1) + datetime.timedelta(days=i) for i in range(271)]
        with self.assertRaises(BackfillError):
            validate_kbar_day_count(days)


class TestResolveContract(unittest.TestCase):
    def test_category_path(self):
        api = MagicMock()
        tmfr1 = object()
        api.Contracts.Futures.TMF.TMFR1 = tmfr1
        self.assertIs(resolve_contract(api, "TMFR1"), tmfr1)

    def test_flat_fallback(self):
        tx = object()

        class Futures:
            def __getitem__(self, key: str):
                return tx

        api = MagicMock()
        api.Contracts.Futures = Futures()
        self.assertIs(resolve_contract(api, "TXFR1"), tx)


class TestBackfillDates(unittest.TestCase):
    def test_writes_ticks_and_kbars(self):
        api = MagicMock()
        _mock_api_usage(api)
        contract = MagicMock()
        contract.code = "TXFR1"
        api.Contracts.Futures.TXF.TXFR1 = contract

        tick_raw = _simulation_tick_raw(datetime.date(2026, 6, 12))
        kbar_raw = _simulation_kbar_raw(datetime.date(2026, 6, 12))
        api.ticks.return_value = tick_raw
        api.kbars.return_value = kbar_raw

        with tempfile.TemporaryDirectory() as td:
            tick_dir = Path(td)
            today = datetime.date(2026, 6, 15)
            dates = [datetime.date(2026, 6, 12)]
            result = backfill_dates(
                dates,
                code="TXFR1",
                simulation=True,
                cache_dir=tick_dir,
                api=api,
                today=today,
            )
            tick_file = cache_path(tick_dir, "TXFR1", dates[0])
            kbar_file = kbar_path(tick_dir, "TXFR1", dates[0])
            self.assertTrue(tick_file.is_file())
            self.assertTrue(kbar_file.is_file())
            self.assertEqual(len(result.ticks), 1)
            self.assertGreaterEqual(len(result.kbars), 1)
            self.assertTrue(result.ok)
            _, kwargs = api.ticks.call_args
            self.assertEqual(kwargs["time_start"], "08:45:00")
            self.assertEqual(kwargs["time_end"], "13:45:00")

    def test_skips_existing_without_overwrite(self):
        api = MagicMock()
        _mock_api_usage(api)
        contract = MagicMock()
        contract.code = "TXFR1"
        api.Contracts.Futures.TXF.TXFR1 = contract

        with tempfile.TemporaryDirectory() as td:
            tick_dir = Path(td)
            date = datetime.date(2026, 6, 12)
            save_ticks_csv(
                [
                    ReplayTick(
                        datetime.datetime(2026, 6, 12, 8, 45)
                        + datetime.timedelta(minutes=30 * i),
                        str(i),
                        1,
                        0,
                    )
                    for i in range(11)
                ],
                cache_path(tick_dir, "TXFR1", date),
            )
            save_kbars_csv(
                [
                    KBarRecord(
                        ts=datetime.datetime(2026, 6, 12, 9, 0),
                        Open=1,
                        High=1,
                        Low=1,
                        Close=1,
                        Volume=1,
                    )
                ],
                kbar_path(tick_dir, "TXFR1", date),
            )
            today = datetime.date(2026, 6, 15)
            backfill_dates(
                [date],
                code="TXFR1",
                simulation=True,
                fetch_kbars=False,
                cache_dir=tick_dir,
                api=api,
                today=today,
            )
            api.ticks.assert_not_called()

    def test_merges_partial_gzip_tick_cache(self):
        api = MagicMock()
        _mock_api_usage(api)
        contract = MagicMock()
        contract.code = "TXFR1"
        api.Contracts.Futures.TXF.TXFR1 = contract
        date = datetime.date(2026, 6, 22)
        morning_ns = int(
            datetime.datetime(
                2026, 6, 22, 8, 45, 0, tzinfo=datetime.timezone.utc
            ).timestamp()
            * 1_000_000_000
        )
        api.ticks.return_value = MagicMock(
            ts=[morning_ns],
            close=[18000.0],
            volume=[1],
            bid_price=[17999.0],
            ask_price=[18001.0],
            tick_type=[1],
        )
        with tempfile.TemporaryDirectory() as td:
            tick_dir = Path(td)
            plain = cache_path(tick_dir, "TXFR1", date)
            save_ticks_csv(
                [ReplayTick(datetime.datetime(2026, 6, 22, 11, 14), "1", 1, 0)],
                plain,
            )
            gz = cache_gz_path(tick_dir, "TXFR1", date)
            with plain.open("rb") as src, gzip.open(gz, "wb") as dst:
                dst.writelines(src)
            plain.unlink()
            today = datetime.date(2026, 6, 23)
            result = backfill_dates(
                [date],
                code="TXFR1",
                simulation=True,
                fetch_kbars=False,
                cache_dir=tick_dir,
                api=api,
                today=today,
            )
            api.ticks.assert_called_once()
            self.assertFalse(result.ok)
            self.assertEqual(result.missing_tick_dates, [date])
            out = cache_path(tick_dir, "TXFR1", date)
            self.assertTrue(out.is_file())
            self.assertFalse(gz.is_file())
            from storage.tick_loader import load_ticks_csv

            self.assertEqual(len(load_ticks_csv(out)), 2)

    @patch("backfilldata.core.repair_kbars_batch")
    @patch("backfilldata.core.merge_rollover_afternoon_batch")
    @patch("backfilldata.core.download_and_cache")
    def test_ticks_only_repairs_kbars_after_rollover_merge(
        self, download_ticks, merge_batch, repair_kbars
    ):
        api = MagicMock()
        _mock_api_usage(api)
        contract = MagicMock()
        contract.code = "TMFR1"
        api.Contracts.Futures.TMF.TMFR1 = contract
        date = datetime.date(2026, 1, 21)
        download_ticks.return_value = [cache_path(Path("/tmp"), "TMFR1", date)]
        merge_batch.return_value = [date]

        with tempfile.TemporaryDirectory() as td:
            tick_dir = Path(td)
            today = datetime.date(2026, 1, 22)
            backfill_dates(
                [date],
                code="TMFR1",
                simulation=True,
                fetch_kbars=False,
                cache_dir=tick_dir,
                api=api,
                today=today,
            )
            merge_batch.assert_called_once()
            repair_kbars.assert_called_once()
            _, kwargs = repair_kbars.call_args
            self.assertEqual(kwargs["rollover_dates"], {date})


class TestBackfillCli(unittest.TestCase):
    def test_help_without_shioaji_import(self):
        sys.modules.pop("backfilldata.__main__", None)
        mods_before = set(sys.modules)
        from backfilldata.__main__ import main

        self.assertNotIn("shioaji", set(sys.modules) - mods_before)
        with self.assertRaises(SystemExit) as ctx:
            main(["--help"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertNotIn("shioaji", set(sys.modules) - mods_before)

    def test_missing_credentials(self):
        from backfilldata.__main__ import main

        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(main(["date", "2026-06-12"]), 1)

    def test_simulation_production_mutually_exclusive(self):
        from backfilldata.__main__ import main

        with self.assertRaises(SystemExit) as ctx:
            main(["date", "2026-06-12", "--simulation", "--production"])
        self.assertEqual(ctx.exception.code, 2)

    @patch("backfilldata.__main__.backfill_dates")
    def test_main_success_return_code(self, mock_backfill):
        from backfilldata.__main__ import main

        mock_backfill.return_value = BackfillResult(
            ticks=[Path("tick.csv")],
            kbars=[Path("kbar.csv")],
        )
        self.assertEqual(main(["date", "2026-06-12"]), 0)
        mock_backfill.assert_called_once()
        _, kwargs = mock_backfill.call_args
        self.assertEqual(kwargs["tick_time_start"], datetime.time(8, 45))
        self.assertEqual(kwargs["tick_time_end"], datetime.time(13, 45))

    @patch("backfilldata.__main__.backfill_dates")
    def test_main_all_day_ticks_disables_range(self, mock_backfill):
        from backfilldata.__main__ import main

        mock_backfill.return_value = BackfillResult(ticks=[Path("tick.csv")])
        self.assertEqual(main(["date", "2026-06-12", "--all-day-ticks"]), 0)
        _, kwargs = mock_backfill.call_args
        self.assertIsNone(kwargs["tick_time_start"])
        self.assertIsNone(kwargs["tick_time_end"])

    def test_rejects_inverted_tick_time_window(self):
        from backfilldata.__main__ import main

        self.assertEqual(
            main(["date", "2026-06-12", "--time-start", "13:45:00", "--time-end", "08:45:00"]),
            2,
        )

    @patch("backfilldata.__main__.backfill_dates")
    def test_main_missing_files_return_code(self, mock_backfill):
        from backfilldata.__main__ import main

        mock_backfill.return_value = BackfillResult(
            missing_tick_dates=[datetime.date(2026, 6, 12)],
        )
        self.assertEqual(main(["date", "2026-06-12"]), 1)


def _pin_yi_day(date: str, *, is_holiday: bool, caption: str = "") -> dict:
    return {"date": date, "isHoliday": is_holiday, "caption": caption}


_APRIL_2026_PIN_YI_CALENDAR = [
    _pin_yi_day("20260401", is_holiday=False),
    _pin_yi_day("20260402", is_holiday=False),
    _pin_yi_day("20260403", is_holiday=True, caption="補假"),
    _pin_yi_day("20260404", is_holiday=True, caption="兒童節"),
    _pin_yi_day("20260405", is_holiday=True, caption="清明節"),
    _pin_yi_day("20260406", is_holiday=True, caption="補假"),
    _pin_yi_day("20260407", is_holiday=False),
    _pin_yi_day("20260408", is_holiday=False),
    _pin_yi_day("20260409", is_holiday=False),
    _pin_yi_day("20260410", is_holiday=False),
    _pin_yi_day("20260411", is_holiday=True),
    _pin_yi_day("20260412", is_holiday=True),
    _pin_yi_day("20260413", is_holiday=False),
    _pin_yi_day("20260414", is_holiday=False),
    _pin_yi_day("20260415", is_holiday=False),
    _pin_yi_day("20260416", is_holiday=False),
    _pin_yi_day("20260417", is_holiday=False),
    _pin_yi_day("20260418", is_holiday=True),
    _pin_yi_day("20260419", is_holiday=True),
    _pin_yi_day("20260420", is_holiday=False),
    _pin_yi_day("20260421", is_holiday=False),
    _pin_yi_day("20260422", is_holiday=False),
    _pin_yi_day("20260423", is_holiday=False),
    _pin_yi_day("20260424", is_holiday=False),
    _pin_yi_day("20260425", is_holiday=True),
    _pin_yi_day("20260426", is_holiday=True),
    _pin_yi_day("20260427", is_holiday=False),
    _pin_yi_day("20260428", is_holiday=False),
    _pin_yi_day("20260429", is_holiday=False),
    _pin_yi_day("20260430", is_holiday=False),
]


class TestTaiwanCalendar(unittest.TestCase):
    def test_parse_month_arg(self):
        from backfilldata.taiwan_calendar import parse_month_arg

        self.assertEqual(parse_month_arg("2026-04"), (2026, 4))

    def test_april_2026_trading_days_skip_holidays(self):
        from backfilldata.taiwan_calendar import resolve_month_trading_days

        trading, skipped = resolve_month_trading_days(
            2026,
            4,
            calendar_year=_APRIL_2026_PIN_YI_CALENDAR,
        )
        self.assertIn(datetime.date(2026, 4, 1), trading)
        self.assertNotIn(datetime.date(2026, 4, 3), trading)
        self.assertNotIn(datetime.date(2026, 4, 6), trading)
        self.assertIn(datetime.date(2026, 4, 3), skipped["holiday"])
        self.assertGreaterEqual(len(skipped["weekend"]), 8)

    def test_cny_holidays_and_resume_trading(self):
        from backfilldata.taiwan_calendar import resolve_month_trading_days

        calendar = [
            _pin_yi_day("20260216", is_holiday=True, caption="農曆除夕"),
            _pin_yi_day("20260217", is_holiday=True, caption="春節"),
            _pin_yi_day("20260218", is_holiday=True, caption="春節"),
            _pin_yi_day("20260219", is_holiday=True, caption="春節"),
            _pin_yi_day("20260220", is_holiday=True, caption="補假"),
            _pin_yi_day("20260223", is_holiday=False),
        ]
        trading, skipped = resolve_month_trading_days(
            2026,
            2,
            calendar_year=calendar,
        )
        self.assertIn(datetime.date(2026, 2, 23), trading)
        self.assertNotIn(datetime.date(2026, 2, 16), trading)
        self.assertIn(datetime.date(2026, 2, 16), skipped["holiday"])

    def test_empty_calendar_raises(self):
        from backfilldata.core import BackfillError
        from backfilldata.taiwan_calendar import resolve_month_trading_days

        with self.assertRaises(BackfillError) as ctx:
            resolve_month_trading_days(2026, 4, calendar_year=[])
        self.assertIn("行事曆", str(ctx.exception))

    def test_reads_bundled_trade_days_cache(self):
        from backfilldata.taiwan_calendar import resolve_month_trading_days
        from storage.cache_paths import DEFAULT_TRADE_DAYS_DIR

        cache_path = DEFAULT_TRADE_DAYS_DIR / "2026.json"
        if not cache_path.is_file():
            self.skipTest("trade_days/2026.json not present")

        trading, skipped = resolve_month_trading_days(2026, 4, calendar_dir=DEFAULT_TRADE_DAYS_DIR)
        self.assertIn(datetime.date(2026, 4, 1), trading)
        self.assertNotIn(datetime.date(2026, 4, 3), trading)
        self.assertIn(datetime.date(2026, 4, 3), skipped["holiday"])
        self.assertEqual(skipped["missing_calendar"], [])

    def test_weekday_without_calendar_entry_not_trading(self):
        from backfilldata.taiwan_calendar import resolve_month_trading_days

        calendar = [_pin_yi_day("20260401", is_holiday=False)]
        trading, skipped = resolve_month_trading_days(
            2026,
            4,
            calendar_year=calendar,
        )
        self.assertEqual(trading, [datetime.date(2026, 4, 1)])
        self.assertIn(datetime.date(2026, 4, 2), skipped["missing_calendar"])

    def test_invalid_cache_refetches_api(self):
        from backfilldata.taiwan_calendar import get_taiwan_calendar_year

        with tempfile.TemporaryDirectory() as tmp:
            calendar_dir = Path(tmp)
            (calendar_dir / "2026.json").write_text("[]\n", encoding="utf-8")
            sample = [_pin_yi_day("20260101", is_holiday=True)]
            with patch(
                "backfilldata.taiwan_calendar.fetch_taiwan_calendar_year",
                return_value=sample,
            ) as mock_fetch:
                data = get_taiwan_calendar_year(2026, calendar_dir=calendar_dir)
            self.assertEqual(data, sample)
            mock_fetch.assert_called_once()

    def test_resolve_month_trading_days_with_fallback(self):
        from backfilldata.taiwan_calendar import resolve_month_trading_days_with_fallback

        with patch(
            "backfilldata.taiwan_calendar.resolve_month_trading_days",
            side_effect=[
                BackfillError("Taiwan 行事曆 API 無法連線"),
                ([datetime.date(2026, 4, 1)], {"weekend": [], "holiday": [], "missing_calendar": []}),
            ],
        ) as mock_resolve:
            trading, skipped = resolve_month_trading_days_with_fallback(2026, 4)
        self.assertEqual(trading, [datetime.date(2026, 4, 1)])
        self.assertEqual(mock_resolve.call_count, 2)
        self.assertFalse(mock_resolve.call_args_list[1].kwargs["use_holiday_calendar"])


class TestBackfillMonth(unittest.TestCase):
    @patch("backfilldata.core.backfill_dates")
    @patch("backfilldata.core.create_and_login_api")
    def test_backfill_month_batches_tick_days(self, mock_login, mock_backfill):
        from backfilldata.core import BackfillResult, backfill_month

        mock_login.return_value = MagicMock()
        mock_backfill.return_value = BackfillResult(ticks=[Path("tick.csv")])

        trading_days = [datetime.date(2026, 4, day) for day in range(1, 23)]
        buckets = {"weekend": [], "holiday": [], "missing_calendar": []}
        with patch(
            "backfilldata.taiwan_calendar.resolve_month_trading_days_with_fallback",
            return_value=(trading_days, buckets),
        ):
            result, meta = backfill_month(
                2026,
                4,
                code="TMFR1",
                simulation=True,
                today=datetime.date(2026, 6, 30),
            )

        self.assertEqual(mock_backfill.call_count, 3)
        self.assertEqual(len(meta["eligible_days"]), 22)
        self.assertTrue(result.ok)

    @patch("backfilldata.core.backfill_dates")
    @patch("backfilldata.core.create_and_login_api")
    def test_backfill_month_reuses_api_session(self, mock_login, mock_backfill):
        from unittest.mock import MagicMock

        from backfilldata.core import BackfillResult, backfill_month

        mock_api = MagicMock()
        mock_login.return_value = mock_api
        mock_backfill.return_value = BackfillResult(ticks=[Path("tick.csv")])

        trading_days = [datetime.date(2026, 4, day) for day in range(1, 23)]
        buckets = {"weekend": [], "holiday": [], "missing_calendar": []}
        with patch(
            "backfilldata.taiwan_calendar.resolve_month_trading_days_with_fallback",
            return_value=(trading_days, buckets),
        ):
            backfill_month(
                2026,
                4,
                code="TMFR1",
                simulation=True,
                today=datetime.date(2026, 6, 30),
            )

        mock_login.assert_called_once()
        self.assertEqual(mock_backfill.call_count, 3)
        for call in mock_backfill.call_args_list:
            self.assertIs(call.kwargs["api"], mock_api)
        mock_api.logout.assert_called_once()

    @patch("backfilldata.core.backfill_dates")
    @patch("backfilldata.core.create_and_login_api")
    def test_backfill_month_calendar_fallback(self, mock_login, mock_backfill):
        from backfilldata.core import BackfillResult, backfill_month

        mock_login.return_value = MagicMock()
        mock_backfill.return_value = BackfillResult(ticks=[Path("tick.csv")])
        weekdays = [datetime.date(2026, 4, 1), datetime.date(2026, 4, 2)]
        buckets = {"weekend": [], "holiday": [], "missing_calendar": []}

        with patch(
            "backfilldata.taiwan_calendar.resolve_month_trading_days_with_fallback",
            return_value=(weekdays, buckets),
        ) as mock_resolve:
            result, meta = backfill_month(
                2026,
                4,
                code="TMFR1",
                simulation=True,
                today=datetime.date(2026, 6, 30),
            )

        mock_resolve.assert_called_once()
        self.assertTrue(result.ok)
        self.assertEqual(meta["eligible_days"], weekdays)

    @patch("backfilldata.__main__.resolve_month_trading_days_with_fallback")
    def test_month_dry_run_lists_days(self, mock_resolve):
        from backfilldata.__main__ import main

        days = [datetime.date(2026, 4, 1), datetime.date(2026, 4, 2)]
        mock_resolve.return_value = (days, {"weekend": [], "holiday": [], "missing_calendar": []})
        with patch("backfilldata.__main__.backfill_month") as mock_month:
            rc = main(["month", "2026-04", "--dry-run"])
        self.assertEqual(rc, 0)
        mock_month.assert_not_called()


if __name__ == "__main__":
    unittest.main()
