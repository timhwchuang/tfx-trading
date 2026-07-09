"""Tests for slim backfilldata CLI and orchestration."""

from __future__ import annotations

import datetime
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backfilldata.core import (
    BackfillError,
    BackfillResult,
    backfill_dates,
    calendar_days_in_month,
    parse_date_args,
    parse_month_arg,
    resolve_contract,
    validate_kbar_day_count,
    validate_past_dates,
    validate_tick_day_count,
)
from storage.kbar_loader import kbar_path
from storage.tick_loader import cache_path


def _mock_api_usage(api: MagicMock) -> None:
    api.usage.return_value = MagicMock(
        bytes=0, limit_bytes=2_000_000_000, remaining_bytes=1_900_000_000
    )


def _day_session_minute_count() -> int:
    return (13 * 60 + 45) - (8 * 60 + 45) + 1


def _wall_ns(y: int, m: int, d: int, h: int, mi: int, s: int = 0) -> int:
    dt = datetime.datetime(y, m, d, h, mi, s, tzinfo=datetime.timezone.utc)
    return int(dt.timestamp() * 1_000_000_000)


def _simulation_tick_raw(date: datetime.date) -> MagicMock:
    ts = [
        _wall_ns(date.year, date.month, date.day, 0, 0),
        _wall_ns(date.year, date.month, date.day, 9, 0),
        _wall_ns(date.year, date.month, date.day, 15, 0),
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


class TestParseDateArgs(unittest.TestCase):
    def test_single(self):
        self.assertEqual(
            parse_date_args(["2026-06-12"]),
            [datetime.date(2026, 6, 12)],
        )

    def test_range(self):
        days = parse_date_args(["2026-06-12", "2026-06-14"])
        self.assertEqual(len(days), 3)

    def test_parse_month_arg(self):
        self.assertEqual(parse_month_arg("2026-04"), (2026, 4))

    def test_calendar_days_in_month(self):
        days = calendar_days_in_month(2026, 4)
        self.assertEqual(len(days), 30)
        self.assertEqual(days[0], datetime.date(2026, 4, 1))
        self.assertEqual(days[-1], datetime.date(2026, 4, 30))
        self.assertIn(datetime.date(2026, 4, 4), days)  # Saturday kept


class TestValidatePastDates(unittest.TestCase):
    def test_rejects_future(self):
        with self.assertRaises(BackfillError):
            validate_past_dates(
                [datetime.date(2026, 6, 20)],
                today=datetime.date(2026, 6, 15),
            )

    def test_allows_today_after_close(self):
        today = datetime.date(2026, 6, 15)
        now = datetime.datetime(
            2026, 6, 15, 14, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=8))
        )
        validate_past_dates([today], today=today, now=now)

    def test_tick_day_cap(self):
        with self.assertRaises(BackfillError):
            validate_tick_day_count([datetime.date(2026, 4, d) for d in range(1, 12)])

    def test_kbar_day_cap(self):
        with self.assertRaises(BackfillError):
            validate_kbar_day_count(
                [datetime.date(2026, 1, 1) + datetime.timedelta(days=i) for i in range(271)]
            )


class TestResolveContract(unittest.TestCase):
    def test_category_attr(self):
        api = MagicMock()
        contract = MagicMock()
        api.Contracts.Futures.TMF.TMFR1 = contract
        self.assertIs(resolve_contract(api, "TMFR1"), contract)


class TestBackfillDates(unittest.TestCase):
    @patch("backfilldata.core.merge_rollover_afternoon_batch", return_value=[])
    def test_downloads_ticks_and_kbars(self, _merge):
        api = MagicMock()
        _mock_api_usage(api)
        contract = MagicMock()
        contract.code = "TXFR1"
        api.Contracts.Futures.TXF.TXFR1 = contract
        date = datetime.date(2026, 6, 12)
        api.ticks.return_value = _simulation_tick_raw(date)
        api.kbars.return_value = _simulation_kbar_raw(date)

        with tempfile.TemporaryDirectory() as td:
            tick_dir = Path(td)
            with patch(
                "storage.tick_loader._taipei_today",
                return_value=datetime.date(2026, 6, 15),
            ):
                result = backfill_dates(
                    [date],
                    code="TXFR1",
                    simulation=True,
                    cache_dir=tick_dir,
                    api=api,
                    today=datetime.date(2026, 6, 15),
                )
            self.assertTrue(result.ok)
            self.assertTrue(cache_path(tick_dir, "TXFR1", date).is_file())
            self.assertTrue(kbar_path(tick_dir, "TXFR1", date).is_file())

    @patch("backfilldata.core.merge_rollover_afternoon_batch", return_value=[])
    def test_empty_day_ok_no_missing(self, _merge):
        api = MagicMock()
        _mock_api_usage(api)
        contract = MagicMock()
        contract.code = "TXFR1"
        api.Contracts.Futures.TXF.TXFR1 = contract
        date = datetime.date(2026, 6, 14)
        api.ticks.return_value = MagicMock(
            ts=[], close=[], volume=[], bid_price=[], ask_price=[], tick_type=[]
        )
        api.kbars.return_value = MagicMock(
            ts=[], Open=[], High=[], Low=[], Close=[], Volume=[]
        )

        with tempfile.TemporaryDirectory() as td:
            tick_dir = Path(td)
            with patch(
                "storage.tick_loader._taipei_today",
                return_value=datetime.date(2026, 6, 15),
            ):
                result = backfill_dates(
                    [date],
                    code="TXFR1",
                    simulation=True,
                    cache_dir=tick_dir,
                    api=api,
                    today=datetime.date(2026, 6, 15),
                )
            self.assertTrue(result.ok)
            self.assertEqual(result.failed_dates, [])
            self.assertFalse(cache_path(tick_dir, "TXFR1", date).exists())
            self.assertFalse(kbar_path(tick_dir, "TXFR1", date).exists())

    @patch("backfilldata.core.merge_rollover_afternoon_batch")
    @patch("backfilldata.core.download_and_cache")
    def test_rollover_merge_no_kbar_repair(self, download_ticks, merge_batch):
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
            result = backfill_dates(
                [date],
                code="TMFR1",
                simulation=True,
                fetch_kbars=False,
                cache_dir=tick_dir,
                api=api,
                today=datetime.date(2026, 1, 22),
            )
            self.assertTrue(result.ok)
            merge_batch.assert_called_once()


class TestBackfillCli(unittest.TestCase):
    def test_help_without_shioaji_import(self):
        sys.modules.pop("backfilldata.__main__", None)
        mods_before = set(sys.modules)
        from backfilldata.__main__ import main

        self.assertNotIn("shioaji", set(sys.modules) - mods_before)
        with self.assertRaises(SystemExit) as ctx:
            main(["--help"])
        self.assertEqual(ctx.exception.code, 0)

    def test_missing_credentials(self):
        from backfilldata.__main__ import main

        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(main(["date", "2026-06-12"]), 1)

    def test_uat_production_mutually_exclusive(self):
        from backfilldata.__main__ import main

        with self.assertRaises(SystemExit) as ctx:
            main(["date", "2026-06-12", "--uat", "--production"])
        self.assertEqual(ctx.exception.code, 2)

    @patch("backfilldata.__main__.backfill_dates_batched")
    def test_main_success_return_code(self, mock_backfill):
        from backfilldata.__main__ import main

        ok = BackfillResult(ticks=[Path("tick.csv")], kbars=[Path("kbar.csv")])
        mock_backfill.return_value = (ok, [ok])
        self.assertEqual(main(["date", "2026-06-12"]), 0)
        mock_backfill.assert_called_once()
        _, kwargs = mock_backfill.call_args
        self.assertIsNone(kwargs["tick_time_start"])
        self.assertIsNone(kwargs["tick_time_end"])
        self.assertTrue(kwargs["simulation"])

    @patch("backfilldata.__main__.backfill_dates_batched")
    def test_main_production_sets_simulation_false(self, mock_backfill):
        from backfilldata.__main__ import main

        ok = BackfillResult()
        mock_backfill.return_value = (ok, [ok])
        self.assertEqual(main(["date", "2026-06-12", "--production"]), 0)
        self.assertFalse(mock_backfill.call_args.kwargs["simulation"])

    @patch("backfilldata.__main__.filter_backfill_eligible_dates")
    @patch("backfilldata.__main__.backfill_dates_batched")
    def test_main_date_range_all_calendar_days(self, mock_backfill, mock_filter):
        from backfilldata.__main__ import main

        days = [
            datetime.date(2026, 7, d) for d in range(1, 7)
        ]
        mock_filter.return_value = (days, [])
        ok = BackfillResult()
        mock_backfill.return_value = (ok, [ok])
        self.assertEqual(main(["date", "2026-07-01", "2026-07-06"]), 0)
        mock_backfill.assert_called_once()
        self.assertEqual(mock_backfill.call_args.args[0], days)

    @patch("backfilldata.__main__.backfill_dates_batched")
    def test_main_failed_dates_return_code(self, mock_backfill):
        from backfilldata.__main__ import main

        failed = BackfillResult(failed_dates=[datetime.date(2026, 6, 12)])
        mock_backfill.return_value = (failed, [failed])
        self.assertEqual(main(["date", "2026-06-12"]), 1)

    def test_month_dry_run_lists_calendar_days(self):
        from backfilldata.__main__ import main

        with patch("backfilldata.__main__.backfill_month") as mock_month:
            with patch(
                "backfilldata.__main__.filter_backfill_eligible_dates",
                return_value=(
                    [datetime.date(2026, 4, 1), datetime.date(2026, 4, 2)],
                    [],
                ),
            ):
                rc = main(["month", "2026-04", "--dry-run"])
        self.assertEqual(rc, 0)
        mock_month.assert_not_called()


class TestBackfillDatesBatched(unittest.TestCase):
    @patch("backfilldata.core.backfill_dates")
    @patch("backfilldata.core.create_and_login_api")
    def test_backfill_dates_batched_chunks(self, mock_login, mock_backfill):
        from backfilldata.core import backfill_dates_batched

        mock_login.return_value = MagicMock()
        mock_backfill.return_value = BackfillResult(ticks=[Path("tick.csv")])

        dates = [datetime.date(2026, 4, day) for day in range(1, 23)]
        result, batches = backfill_dates_batched(
            dates,
            code="TMFR1",
            simulation=True,
            today=datetime.date(2026, 6, 30),
        )
        tick_calls = [
            c for c in mock_backfill.call_args_list if c.kwargs.get("fetch_kbars") is False
        ]
        kbar_calls = [
            c for c in mock_backfill.call_args_list if c.kwargs.get("fetch_ticks") is False
        ]
        self.assertEqual(len(tick_calls), 3)
        self.assertEqual(len(kbar_calls), 1)
        self.assertEqual(len(batches), 4)
        self.assertTrue(result.ok)


class TestBackfillMonth(unittest.TestCase):
    @patch("backfilldata.core.backfill_dates")
    @patch("backfilldata.core.create_and_login_api")
    def test_backfill_month_all_calendar_days(self, mock_login, mock_backfill):
        from backfilldata.core import backfill_month

        mock_login.return_value = MagicMock()
        mock_backfill.return_value = BackfillResult(ticks=[Path("tick.csv")])

        result, meta = backfill_month(
            2026,
            4,
            code="TMFR1",
            simulation=True,
            today=datetime.date(2026, 6, 30),
        )
        self.assertEqual(len(meta["calendar_days"]), 30)
        self.assertEqual(len(meta["eligible_days"]), 30)
        self.assertTrue(result.ok)
        tick_calls = [
            c for c in mock_backfill.call_args_list if c.kwargs.get("fetch_kbars") is False
        ]
        self.assertEqual(len(tick_calls), 3)


if __name__ == "__main__":
    unittest.main()
