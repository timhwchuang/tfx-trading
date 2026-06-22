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
    kbars_cache_path,
    save_kbars_csv,
)
from storage.tick_loader import ReplayTick, cache_gz_path, cache_path, save_ticks_csv


def _mock_api_usage(api: MagicMock) -> None:
    api.usage.return_value = MagicMock(bytes=0, limit_bytes=2_000_000_000, remaining_bytes=1_900_000_000)


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
    def test_rejects_today(self):
        today = datetime.date(2026, 6, 22)
        with self.assertRaises(BackfillError):
            validate_past_dates([today], today=today)

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


class TestDownloadAndCacheKbarsMirror(unittest.TestCase):
    def test_mirror_copies_to_tick_cache(self):
        api = MagicMock()
        _mock_api_usage(api)
        contract = MagicMock()
        contract.code = "TXFR1"
        date = datetime.date(2026, 6, 12)
        api.kbars.return_value = MagicMock(
            ts=[1],
            Open=[100.0],
            High=[101.0],
            Low=[99.0],
            Close=[100.5],
            Volume=[10],
        )
        with tempfile.TemporaryDirectory() as kd, tempfile.TemporaryDirectory() as td:
            kbar_dir = Path(kd)
            tick_dir = Path(td)
            paths = download_and_cache_kbars(
                api,
                contract,
                [date],
                cache_dir=kbar_dir,
                mirror_cache_dir=tick_dir,
                simulation=True,
            )
            primary = kbars_cache_path(kbar_dir, "TXFR1", date)
            mirror = kbars_cache_path(tick_dir, "TXFR1", date)
            self.assertTrue(primary.is_file())
            self.assertTrue(mirror.is_file())
            self.assertIn(primary, paths)
            self.assertIn(mirror, paths)

    def test_refreshes_stale_mirror_from_existing_primary(self):
        api = MagicMock()
        _mock_api_usage(api)
        contract = MagicMock()
        contract.code = "TXFR1"
        date = datetime.date(2026, 6, 12)
        with tempfile.TemporaryDirectory() as kd, tempfile.TemporaryDirectory() as td:
            kbar_dir = Path(kd)
            tick_dir = Path(td)
            save_kbars_csv(
                [
                    KBarRecord(
                        ts=datetime.datetime(2026, 6, 12, 9, 0),
                        Open=100.0,
                        High=101.0,
                        Low=99.0,
                        Close=100.5,
                        Volume=10,
                    )
                ],
                kbars_cache_path(kbar_dir, "TXFR1", date),
            )
            stale = kbars_cache_path(tick_dir, "TXFR1", date)
            stale.write_text("ts,Open,High,Low,Close,Volume\n", encoding="utf-8")
            download_and_cache_kbars(
                api,
                contract,
                [date],
                cache_dir=kbar_dir,
                mirror_cache_dir=tick_dir,
                simulation=True,
            )
            api.kbars.assert_not_called()
            self.assertGreater(stale.stat().st_size, 20)


class TestBackfillDates(unittest.TestCase):
    def test_writes_ticks_and_mirrored_kbars(self):
        api = MagicMock()
        _mock_api_usage(api)
        contract = MagicMock()
        contract.code = "TXFR1"
        api.Contracts.Futures.TXF.TXFR1 = contract

        tick_raw = MagicMock(
            ts=[1_700_000_000_000_000_000],
            close=[18000.0],
            volume=[1],
            bid_price=[17999.0],
            ask_price=[18001.0],
            tick_type=[1],
        )
        kbar_raw = MagicMock(
            ts=[1],
            Open=[100.0],
            High=[101.0],
            Low=[99.0],
            Close=[100.5],
            Volume=[10],
        )
        api.ticks.return_value = tick_raw
        api.kbars.return_value = kbar_raw

        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as kd:
            tick_dir = Path(td)
            kbar_dir = Path(kd)
            today = datetime.date(2026, 6, 15)
            dates = [datetime.date(2026, 6, 12)]
            result = backfill_dates(
                dates,
                code="TXFR1",
                simulation=True,
                tick_cache_dir=tick_dir,
                kbar_cache_dir=kbar_dir,
                mirror_kbars_to_tick_cache=True,
                api=api,
                today=today,
            )
            tick_file = cache_path(tick_dir, "TXFR1", dates[0])
            kbar_primary = kbars_cache_path(kbar_dir, "TXFR1", dates[0])
            kbar_mirror = kbars_cache_path(tick_dir, "TXFR1", dates[0])
            self.assertTrue(tick_file.is_file())
            self.assertTrue(kbar_primary.is_file())
            self.assertTrue(kbar_mirror.is_file())
            self.assertEqual(len(result.ticks), 1)
            self.assertGreaterEqual(len(result.kbars), 2)
            self.assertTrue(result.ok)

    def test_skips_existing_without_overwrite(self):
        api = MagicMock()
        _mock_api_usage(api)
        contract = MagicMock()
        contract.code = "TXFR1"
        api.Contracts.Futures.TXF.TXFR1 = contract

        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as kd:
            tick_dir = Path(td)
            kbar_dir = Path(kd)
            date = datetime.date(2026, 6, 12)
            save_ticks_csv(
                [ReplayTick(datetime.datetime(2026, 6, 12, 9, 0), "1", 1, 0)],
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
                kbars_cache_path(kbar_dir, "TXFR1", date),
            )
            today = datetime.date(2026, 6, 15)
            backfill_dates(
                [date],
                code="TXFR1",
                simulation=True,
                fetch_kbars=False,
                tick_cache_dir=tick_dir,
                kbar_cache_dir=kbar_dir,
                api=api,
                today=today,
            )
            api.ticks.assert_not_called()

    def test_ok_when_only_gzip_tick_cache(self):
        api = MagicMock()
        _mock_api_usage(api)
        contract = MagicMock()
        contract.code = "TXFR1"
        api.Contracts.Futures.TXF.TXFR1 = contract
        date = datetime.date(2026, 6, 12)
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as kd:
            tick_dir = Path(td)
            kbar_dir = Path(kd)
            gz = cache_gz_path(tick_dir, "TXFR1", date)
            gz.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(gz, "wt", encoding="utf-8", newline="") as f:
                f.write("datetime,close,volume,bid_price,ask_price,tick_type\n")
            today = datetime.date(2026, 6, 15)
            result = backfill_dates(
                [date],
                code="TXFR1",
                simulation=True,
                fetch_kbars=False,
                tick_cache_dir=tick_dir,
                kbar_cache_dir=kbar_dir,
                api=api,
                today=today,
            )
            api.ticks.assert_not_called()
            self.assertTrue(result.ok)
            self.assertEqual(result.ticks, [gz])


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

    @patch("backfilldata.__main__.backfill_dates")
    def test_main_missing_files_return_code(self, mock_backfill):
        from backfilldata.__main__ import main

        mock_backfill.return_value = BackfillResult(
            missing_tick_dates=[datetime.date(2026, 6, 12)],
        )
        self.assertEqual(main(["date", "2026-06-12"]), 1)


if __name__ == "__main__":
    unittest.main()
