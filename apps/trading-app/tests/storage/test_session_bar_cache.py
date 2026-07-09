"""Tests for Yuanta-anchored SessionBarCache."""

from __future__ import annotations

import datetime
import json
import os
import tempfile
import unittest
from pathlib import Path

from storage.kbar_loader import KBarRecord, kbar_path, save_kbars_csv
from storage.session_bar_cache import (
    DEFAULT_TF_TABLE,
    EXPECTED_DAWN_BARS,
    EXPECTED_DAY_BARS,
    SessionBarCache,
    assess_calendar_day_readiness,
    assess_today_from_bars,
    assess_today_kbar_file,
    build_session_daily_bars,
    count_session_bars,
    kbar_file_date,
    session_label_date,
    yuanta_resample,
    yuanta_resample_instance,
)


def _minute_bars(
    start: datetime.datetime,
    n: int,
    *,
    price: float = 100.0,
) -> list[KBarRecord]:
    bars: list[KBarRecord] = []
    cur = start
    for i in range(n):
        p = price + i * 0.1
        bars.append(KBarRecord(cur, p, p + 1, p - 1, p, 10))
        cur += datetime.timedelta(minutes=1)
    return bars


def _day_session_bars(day: datetime.date) -> list[KBarRecord]:
    """08:46–13:44 style minutes (299 bars) like on-disk kbars."""
    start = datetime.datetime.combine(day, datetime.time(8, 46))
    return _minute_bars(start, EXPECTED_DAY_BARS - 1)


def _dawn_session_bars(day: datetime.date) -> list[KBarRecord]:
    start = datetime.datetime.combine(day, datetime.time(0, 0))
    return _minute_bars(start, EXPECTED_DAWN_BARS)


def _evening_bars(day: datetime.date, n: int = 60) -> list[KBarRecord]:
    start = datetime.datetime.combine(day, datetime.time(15, 0))
    return _minute_bars(start, n)


class TestYuantaResample(unittest.TestCase):
    def test_day_1h_close_times(self):
        day = datetime.date(2026, 4, 8)
        bars = _day_session_bars(day)
        anchor = datetime.datetime.combine(day, datetime.time(8, 45))
        end = datetime.datetime.combine(day, datetime.time(13, 45))
        as_of = datetime.datetime.combine(day, datetime.time(13, 45))
        closed, current = yuanta_resample_instance(bars, anchor, end, 60, as_of)
        self.assertEqual([b.ts.time() for b in closed], [datetime.time(9, 45), datetime.time(10, 45), datetime.time(11, 45), datetime.time(12, 45), datetime.time(13, 45)])
        self.assertIsNone(current)

    def test_day_4h_truncated_tail(self):
        day = datetime.date(2026, 4, 8)
        bars = _day_session_bars(day)
        as_of = datetime.datetime.combine(day, datetime.time(13, 45))
        closed, _ = yuanta_resample(bars, 240, "day", as_of)
        self.assertEqual([b.ts.time() for b in closed], [datetime.time(12, 45), datetime.time(13, 45)])

    def test_night_4h_close_times(self):
        fri = datetime.date(2026, 4, 10)
        sat = datetime.date(2026, 4, 11)
        bars = _evening_bars(fri, 9 * 60) + _minute_bars(
            datetime.datetime.combine(sat, datetime.time(0, 0)),
            5 * 60,
        )
        as_of = datetime.datetime.combine(sat, datetime.time(5, 0))
        closed, _ = yuanta_resample(bars, 240, "night", as_of)
        self.assertEqual(
            [b.ts.time() for b in closed],
            [datetime.time(19, 0), datetime.time(23, 0), datetime.time(3, 0), datetime.time(5, 0)],
        )


class TestTodayKbarStatus(unittest.TestCase):
    def test_saturday_requires_dawn_bars(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            sat = datetime.date(2026, 4, 11)
            save_kbars_csv(_dawn_session_bars(sat), kbar_path(cache, "TX", sat))
            status = assess_today_kbar_file(
                "TX",
                sat,
                cache_dir=cache,
                trading_days=[sat],
            )
            self.assertTrue(status.file_exists)
            self.assertTrue(status.is_saturday)
            self.assertTrue(status.ready)
            self.assertEqual(status.reason, "ok")

    def test_saturday_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            sat = datetime.date(2026, 4, 11)
            status = assess_today_kbar_file(
                "TX",
                sat,
                cache_dir=Path(tmp),
                trading_days=[sat],
            )
            self.assertFalse(status.file_exists)
            self.assertFalse(status.ready)
            self.assertEqual(status.reason, "missing_file")

    def test_saturday_dawn_short(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            sat = datetime.date(2026, 4, 11)
            save_kbars_csv(
                _minute_bars(datetime.datetime.combine(sat, datetime.time(0, 0)), 100),
                kbar_path(cache, "TX", sat),
            )
            status = assess_today_kbar_file(
                "TX",
                sat,
                cache_dir=cache,
                trading_days=[sat],
            )
            self.assertTrue(status.file_exists)
            self.assertFalse(status.ready)
            self.assertTrue(status.reason.startswith("dawn_short:"))

    def test_trading_day_needs_day_bars(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            day = datetime.date(2026, 4, 8)
            save_kbars_csv(_day_session_bars(day), kbar_path(cache, "TX", day))
            status = assess_today_kbar_file(
                "TX",
                day,
                cache_dir=cache,
                trading_days=[day],
            )
            self.assertTrue(status.ready)
            self.assertGreaterEqual(status.day_bars, EXPECTED_DAY_BARS - 1)

    def test_monday_dawn_only_before_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            mon = datetime.date(2026, 4, 13)
            save_kbars_csv(_dawn_session_bars(mon), kbar_path(cache, "TX", mon))
            as_of = datetime.datetime.combine(mon, datetime.time(8, 44))
            status = assess_today_kbar_file(
                "TX",
                mon,
                cache_dir=cache,
                trading_days=[mon],
                as_of=as_of,
            )
            self.assertTrue(status.ready)
            self.assertEqual(status.reason, "dawn_only_ok")


class TestSessionBarCache(unittest.TestCase):
    def _write_calendar(self, calendar_dir: Path, year: int, trading: list[str]) -> None:
        calendar_dir.mkdir(parents=True, exist_ok=True)
        entries = []
        for token in trading:
            entries.append({"date": token, "isHoliday": False})
        (calendar_dir / f"{year}.json").write_text(
            json.dumps(entries, ensure_ascii=False),
            encoding="utf-8",
        )

    def test_holiday_gap_no_placeholder_bars(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            cal = cache / "trade_days"
            fri = datetime.date(2026, 4, 10)
            mon = datetime.date(2026, 4, 13)
            self._write_calendar(
                cal,
                2026,
                ["20260408", "20260409", "20260410", "20260413"],
            )
            save_kbars_csv(
                _evening_bars(fri, 9 * 60) + _dawn_session_bars(fri + datetime.timedelta(days=1)),
                kbar_path(cache, "TX", fri),
            )
            save_kbars_csv(_day_session_bars(mon), kbar_path(cache, "TX", mon))

            as_of = datetime.datetime.combine(mon, datetime.time(10, 30))
            sc = SessionBarCache.load(
                "TX",
                as_of,
                cache_dir=cache,
                calendar_dir=cal,
                tf_table={"4h": DEFAULT_TF_TABLE["4h"]},
            )
            bars_4h = sc.closed("4h")
            self.assertGreater(len(bars_4h), 0)
            for i in range(1, len(bars_4h)):
                self.assertLess(bars_4h[i - 1].ts, bars_4h[i].ts)

    @unittest.skipUnless(os.environ.get("RUN_SLOW_STORAGE"), "set RUN_SLOW_STORAGE=1 to run")
    def test_daily_ma60(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            cal = cache / "trade_days"
            days: list[datetime.date] = []
            cur = datetime.date(2026, 1, 1)
            while len(days) < 90:
                if cur.weekday() < 5:
                    days.append(cur)
                cur += datetime.timedelta(days=1)
            self._write_calendar(
                cal,
                2026,
                [d.strftime("%Y%m%d") for d in days],
            )
            for i, day in enumerate(days):
                evening = _evening_bars(day, 30)
                nxt = day + datetime.timedelta(days=1)
                dawn = _minute_bars(datetime.datetime.combine(nxt, datetime.time(0, 0)), 30)
                day_bars = _minute_bars(
                    datetime.datetime.combine(nxt, datetime.time(8, 46)),
                    100,
                    price=100 + i,
                )
                save_kbars_csv(evening + dawn + day_bars, kbar_path(cache, "TX", day))

            as_of = datetime.datetime.combine(days[-1], datetime.time(13, 45))
            sc = SessionBarCache.load("TX", as_of, cache_dir=cache, calendar_dir=cal)
            mas = sc.daily_mas()
            self.assertIn("ma5", mas)
            self.assertIn("ma20", mas)
            self.assertIn("ma60", mas)
            if len(sc.daily_closed()) >= 60:
                self.assertIsNotNone(mas["ma60"])

    def test_as_of_current_5m(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            cal = cache / "trade_days"
            day = datetime.date(2026, 4, 8)
            self._write_calendar(cal, 2026, ["20260408"])
            bars = _day_session_bars(day)
            save_kbars_csv(bars, kbar_path(cache, "TX", day))
            as_of = datetime.datetime.combine(day, datetime.time(10, 32))
            sc = SessionBarCache.load("TX", as_of, cache_dir=cache, calendar_dir=cal)
            self.assertIsNotNone(sc.current("5m"))


class TestKbarFileDate(unittest.TestCase):
    def test_dawn_maps_to_evening_open_file(self):
        fri = datetime.date(2026, 5, 8)
        sat = datetime.date(2026, 5, 9)
        trading = [fri, datetime.date(2026, 5, 11)]
        bar = KBarRecord(datetime.datetime(2026, 5, 9, 3, 0), 1, 2, 0, 1, 5)
        self.assertEqual(kbar_file_date(bar, trading), fri)

    def test_day_session_maps_to_bundle_file(self):
        wed = datetime.date(2026, 5, 20)
        thu = datetime.date(2026, 5, 21)
        trading = [wed, thu]
        bar = KBarRecord(datetime.datetime(2026, 5, 21, 10, 31), 1, 2, 0, 1, 5)
        self.assertEqual(kbar_file_date(bar, trading), wed)


class TestSessionLabel(unittest.TestCase):
    def test_monday_evening_labels_tuesday(self):
        trading = [datetime.date(2026, 4, 13), datetime.date(2026, 4, 14)]
        ts = datetime.datetime(2026, 4, 13, 16, 0)
        self.assertEqual(session_label_date(ts, trading), datetime.date(2026, 4, 14))

    def test_tuesday_evening_labels_wednesday(self):
        trading = [
            datetime.date(2026, 7, 7),
            datetime.date(2026, 7, 8),
        ]
        ts = datetime.datetime(2026, 7, 7, 15, 30)
        self.assertEqual(session_label_date(ts, trading), datetime.date(2026, 7, 8))

    def test_saturday_dawn_labels_monday_close(self):
        trading = [
            datetime.date(2026, 5, 8),
            datetime.date(2026, 5, 11),
        ]
        ts = datetime.datetime(2026, 5, 9, 3, 0)
        self.assertEqual(session_label_date(ts, trading), datetime.date(2026, 5, 11))


class TestSettlementTail(unittest.TestCase):
    def test_day_settlement_tail_used_for_daily_close(self):
        day = datetime.date(2026, 5, 21)
        trading = [day]
        bars = _minute_bars(datetime.datetime.combine(day, datetime.time(8, 46)), 299)
        bars[-1] = KBarRecord(
            datetime.datetime.combine(day, datetime.time(13, 45)),
            100.0,
            101.0,
            99.0,
            41496.0,
            10,
        )
        bars.append(
            KBarRecord(
                datetime.datetime.combine(day, datetime.time(13, 46)),
                41496.0,
                41498.0,
                41496.0,
                41497.0,
                4,
            )
        )
        as_of = datetime.datetime.combine(day, datetime.time(13, 46))
        daily = build_session_daily_bars(bars, trading, as_of)
        self.assertEqual(len(daily), 1)
        self.assertEqual(daily[0].Close, 41497.0)


class TestOnNew1m(unittest.TestCase):
    def _write_calendar(self, calendar_dir: Path, year: int, trading: list[str]) -> None:
        calendar_dir.mkdir(parents=True, exist_ok=True)
        entries = [{"date": token, "isHoliday": False} for token in trading]
        (calendar_dir / f"{year}.json").write_text(
            json.dumps(entries, ensure_ascii=False),
            encoding="utf-8",
        )

    def test_dedupes_same_ts_last_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            cal = cache / "trade_days"
            day = datetime.date(2026, 4, 8)
            self._write_calendar(cal, 2026, ["20260408"])
            bars = _day_session_bars(day)
            save_kbars_csv(bars, kbar_path(cache, "TX", day))
            as_of = datetime.datetime.combine(day, datetime.time(10, 30))
            sc = SessionBarCache.load(
                "TX",
                as_of,
                cache_dir=cache,
                calendar_dir=cal,
                tf_table={"1m": DEFAULT_TF_TABLE["1m"]},
            )
            ts = datetime.datetime.combine(day, datetime.time(10, 30))
            sc.on_new_1m(KBarRecord(ts, 100.0, 101.0, 99.0, 100.0, 10))
            sc.on_new_1m(KBarRecord(ts, 200.0, 210.0, 190.0, 205.0, 99))
            self.assertIn(ts, sc._bars_1m_map)
            self.assertEqual(sc._bars_1m_map[ts].Volume, 99)

    def test_today_status_from_memory_without_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            cal = cache / "trade_days"
            day = datetime.date(2026, 4, 8)
            self._write_calendar(cal, 2026, ["20260408"])
            as_of = datetime.datetime.combine(day, datetime.time(8, 46))
            sc = SessionBarCache.load("TX", as_of, cache_dir=cache, calendar_dir=cal)
            self.assertFalse(sc.today_status.file_exists)
            bar = KBarRecord(as_of, 100.0, 101.0, 99.0, 100.5, 10)
            sc.on_new_1m(bar)
            self.assertTrue(sc.today_status.file_exists)
            self.assertEqual(sc.today_status.day_bars, 1)
            self.assertFalse(sc.today_status.ready)


class TestIncrementalBuild(unittest.TestCase):
    def _write_calendar(self, calendar_dir: Path, year: int, trading: list[str]) -> None:
        calendar_dir.mkdir(parents=True, exist_ok=True)
        entries = [{"date": token, "isHoliday": False} for token in trading]
        (calendar_dir / f"{year}.json").write_text(
            json.dumps(entries, ensure_ascii=False),
            encoding="utf-8",
        )

    def test_tail_resample_matches_full_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            cal = cache / "trade_days"
            day = datetime.date(2026, 4, 8)
            self._write_calendar(cal, 2026, ["20260408"])
            save_kbars_csv(_day_session_bars(day), kbar_path(cache, "TX", day))
            as_of = datetime.datetime.combine(day, datetime.time(10, 30))
            sc = SessionBarCache.load("TX", as_of, cache_dir=cache, calendar_dir=cal)
            new_bar = KBarRecord(
                datetime.datetime.combine(day, datetime.time(10, 31)),
                200.0,
                210.0,
                190.0,
                205.0,
                42,
            )
            sc.on_new_1m(new_bar)
            incr = {
                tf: (sc.closed(tf), sc.current(tf)) for tf in sc.tf_table
            }
            sc._build()
            full = {
                tf: (sc.closed(tf), sc.current(tf)) for tf in sc.tf_table
            }
            self.assertEqual(incr, full)

    @unittest.skipUnless(os.environ.get("RUN_SLOW_STORAGE"), "set RUN_SLOW_STORAGE=1 to run")
    def test_live_ingest_preserves_long_tf_lookback(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            cal = cache / "trade_days"
            days: list[datetime.date] = []
            cur = datetime.date(2026, 1, 1)
            while len(days) < 25:
                if cur.weekday() < 5:
                    days.append(cur)
                cur += datetime.timedelta(days=1)
            self._write_calendar(
                cal,
                2026,
                [d.strftime("%Y%m%d") for d in days],
            )
            for i, day in enumerate(days):
                evening = _evening_bars(day, 30)
                nxt = day + datetime.timedelta(days=1)
                dawn = _minute_bars(datetime.datetime.combine(nxt, datetime.time(0, 0)), 30)
                day_bars = _minute_bars(
                    datetime.datetime.combine(nxt, datetime.time(8, 46)),
                    100,
                    price=100 + i,
                )
                save_kbars_csv(evening + dawn + day_bars, kbar_path(cache, "TX", day))
            as_of = datetime.datetime.combine(days[-1], datetime.time(10, 30))
            sc = SessionBarCache.load(
                "TX",
                as_of,
                cache_dir=cache,
                calendar_dir=cal,
                tf_table={"4h": DEFAULT_TF_TABLE["4h"]},
            )
            before = sc.closed("4h")
            self.assertGreater(len(before), 1)
            sc.on_new_1m(
                KBarRecord(
                    datetime.datetime.combine(days[-1], datetime.time(10, 31)),
                    200.0,
                    210.0,
                    190.0,
                    205.0,
                    1,
                )
            )
            after = sc.closed("4h")
            self.assertEqual(len(after), len(before))
            self.assertEqual(after[0].ts, before[0].ts)
            sc._build()
            full = sc.closed("4h")
            self.assertEqual(after, full)

    def test_intraday_ingest_skips_daily_rebuild(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            cal = cache / "trade_days"
            day = datetime.date(2026, 4, 8)
            self._write_calendar(cal, 2026, ["20260408"])
            save_kbars_csv(_day_session_bars(day), kbar_path(cache, "TX", day))
            as_of = datetime.datetime.combine(day, datetime.time(10, 30))
            sc = SessionBarCache.load("TX", as_of, cache_dir=cache, calendar_dir=cal)
            before = sc.daily_closed()
            sc.on_new_1m(
                KBarRecord(
                    datetime.datetime.combine(day, datetime.time(10, 31)),
                    100.0,
                    101.0,
                    99.0,
                    100.5,
                    10,
                )
            )
            self.assertEqual(sc.daily_closed(), before)


class TestAssessTodayFromBars(unittest.TestCase):
    def test_matches_disk_assessment(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            wed = datetime.date(2026, 5, 20)
            thu = datetime.date(2026, 5, 21)
            save_kbars_csv(_day_session_bars(thu), kbar_path(cache, "TX", wed))
            from_disk = assess_today_kbar_file(
                "TX",
                thu,
                cache_dir=cache,
                trading_days=[wed, thu],
            )
            from_mem = assess_today_from_bars(
                _day_session_bars(thu),
                thu,
                trading_days=[wed, thu],
            )
            self.assertEqual(from_mem.ready, from_disk.ready)
            self.assertEqual(from_mem.day_bars, from_disk.day_bars)
            self.assertTrue(from_disk.file_exists)


class TestCalendarDayReadinessContract(unittest.TestCase):
    def _write_calendar(self, calendar_dir: Path, year: int, trading: list[str]) -> None:
        calendar_dir.mkdir(parents=True, exist_ok=True)
        entries = [{"date": token, "isHoliday": False} for token in trading]
        (calendar_dir / f"{year}.json").write_text(
            json.dumps(entries, ensure_ascii=False),
            encoding="utf-8",
        )

    def test_three_paths_agree_for_bundle_thursday(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            cal = cache / "trade_days"
            wed = datetime.date(2026, 5, 20)
            thu = datetime.date(2026, 5, 21)
            self._write_calendar(cal, 2026, ["20260520", "20260521"])
            save_kbars_csv(_day_session_bars(thu), kbar_path(cache, "TX", wed))
            as_of = datetime.datetime.combine(thu, datetime.time(13, 45))
            from_disk = assess_today_kbar_file(
                "TX",
                thu,
                cache_dir=cache,
                trading_days=[wed, thu],
                as_of=as_of,
            )
            from_load = SessionBarCache.load(
                "TX", as_of, cache_dir=cache, calendar_dir=cal
            ).today_status
            self.assertEqual(from_disk.ready, from_load.ready)
            self.assertEqual(from_disk.day_bars, from_load.day_bars)
            self.assertEqual(from_disk.file_exists, from_load.file_exists)

            intraday = datetime.datetime.combine(thu, datetime.time(10, 35))
            sc = SessionBarCache.load("TX", intraday, cache_dir=cache, calendar_dir=cal)
            baseline = sc.today_status.day_bars
            sc.on_new_1m(
                KBarRecord(
                    datetime.datetime.combine(thu, datetime.time(10, 31)),
                    200.0,
                    210.0,
                    190.0,
                    205.0,
                    99,
                )
            )
            self.assertTrue(sc.today_status.file_exists)
            self.assertEqual(sc.today_status.day_bars, baseline)

    def test_wednesday_assessment_excludes_thursday_day_bars(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            cal = cache / "trade_days"
            wed = datetime.date(2026, 5, 20)
            thu = datetime.date(2026, 5, 21)
            self._write_calendar(cal, 2026, ["20260520", "20260521"])
            save_kbars_csv(
                _evening_bars(wed, 60) + _day_session_bars(thu),
                kbar_path(cache, "TX", wed),
            )
            status = assess_today_kbar_file(
                "TX",
                wed,
                cache_dir=cache,
                trading_days=[wed, thu],
            )
            self.assertTrue(status.file_exists)
            self.assertLess(status.day_bars, EXPECTED_DAY_BARS - 1)


class TestRolloverTodayCounts(unittest.TestCase):
    def _write_calendar(self, calendar_dir: Path, year: int, trading: list[str]) -> None:
        calendar_dir.mkdir(parents=True, exist_ok=True)
        entries = [{"date": token, "isHoliday": False} for token in trading]
        (calendar_dir / f"{year}.json").write_text(
            json.dumps(entries, ensure_ascii=False),
            encoding="utf-8",
        )

    def test_rollover_hydrates_from_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            cal = cache / "trade_days"
            thu = datetime.date(2026, 5, 21)
            fri = datetime.date(2026, 5, 22)
            self._write_calendar(cal, 2026, ["20260521", "20260522"])
            save_kbars_csv(_day_session_bars(thu), kbar_path(cache, "TX", thu))
            save_kbars_csv(_dawn_session_bars(fri), kbar_path(cache, "TX", thu))
            thu_close = datetime.datetime.combine(thu, datetime.time(13, 45))
            sc = SessionBarCache.load(
                "TX", thu_close, cache_dir=cache, calendar_dir=cal
            )
            fri_open = datetime.datetime.combine(fri, datetime.time(8, 46))
            sc.on_new_1m(
                KBarRecord(fri_open, 100.0, 101.0, 99.0, 100.5, 10)
            )
            from_disk = assess_today_kbar_file(
                "TX",
                fri,
                cache_dir=cache,
                trading_days=[thu, fri],
                as_of=fri_open,
            )
            expected = assess_calendar_day_readiness(
                fri,
                trading_days=[thu, fri],
                as_of=fri_open,
                memory_bars=sc._bars_1m_map.values(),
                code="TX",
                cache_dir=cache,
            )
            self.assertTrue(sc.today_status.file_exists)
            self.assertGreaterEqual(sc.today_status.dawn_bars, EXPECTED_DAWN_BARS - 1)
            self.assertEqual(sc.today_status.dawn_bars, expected.dawn_bars)
            self.assertEqual(sc.today_status.day_bars, expected.day_bars)
            self.assertEqual(sc.today_status.ready, expected.ready)
            self.assertGreaterEqual(from_disk.dawn_bars, EXPECTED_DAWN_BARS - 1)

    def test_rollover_extends_trading_days_for_ready_status(self):
        """Live session past load as_of must not report not_trading_day when bars exist."""
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            cal = cache / "trade_days"
            thu = datetime.date(2026, 5, 21)
            fri = datetime.date(2026, 5, 22)
            self._write_calendar(cal, 2026, ["20260521", "20260522"])
            save_kbars_csv(
                _day_session_bars(thu) + _day_session_bars(fri),
                kbar_path(cache, "TX", thu),
            )
            thu_close = datetime.datetime.combine(thu, datetime.time(13, 45))
            sc = SessionBarCache.load(
                "TX", thu_close, cache_dir=cache, calendar_dir=cal
            )
            self.assertNotIn(fri, sc.trading_days)

            fri_close = datetime.datetime.combine(fri, datetime.time(13, 45))
            sc.on_new_1m(
                KBarRecord(fri_close, 100.0, 101.0, 99.0, 100.5, 10)
            )
            self.assertIn(fri, sc.trading_days)
            self.assertTrue(sc.today_status.is_trading_day)
            self.assertTrue(sc.today_status.file_exists)
            self.assertGreaterEqual(sc.today_status.day_bars, EXPECTED_DAY_BARS - 1)
            self.assertTrue(sc.today_status.ready)
            self.assertEqual(sc.today_status.reason, "ok")


class TestBundleAwareLoad(unittest.TestCase):
    def _write_calendar(self, calendar_dir: Path, year: int, trading: list[str]) -> None:
        calendar_dir.mkdir(parents=True, exist_ok=True)
        entries = [{"date": token, "isHoliday": False} for token in trading]
        (calendar_dir / f"{year}.json").write_text(
            json.dumps(entries, ensure_ascii=False),
            encoding="utf-8",
        )

    def test_load_today_status_from_bundle_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            cal = cache / "trade_days"
            wed = datetime.date(2026, 5, 20)
            thu = datetime.date(2026, 5, 21)
            self._write_calendar(cal, 2026, ["20260520", "20260521"])
            save_kbars_csv(_day_session_bars(thu), kbar_path(cache, "TX", wed))
            as_of = datetime.datetime.combine(thu, datetime.time(13, 45))
            sc = SessionBarCache.load("TX", as_of, cache_dir=cache, calendar_dir=cal)
            self.assertTrue(sc.today_status.file_exists)
            self.assertGreaterEqual(sc.today_status.day_bars, EXPECTED_DAY_BARS - 1)
            self.assertTrue(sc.today_status.ready)

    def test_missing_trading_days_bundle_aware(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            cal = cache / "trade_days"
            wed = datetime.date(2026, 5, 20)
            thu = datetime.date(2026, 5, 21)
            self._write_calendar(cal, 2026, ["20260520", "20260521"])
            save_kbars_csv(_day_session_bars(thu), kbar_path(cache, "TX", wed))
            as_of = datetime.datetime.combine(thu, datetime.time(10, 30))
            sc = SessionBarCache.load("TX", as_of, cache_dir=cache, calendar_dir=cal)
            self.assertNotIn(thu, sc.missing_trading_days)


class TestCountSessionBars(unittest.TestCase):
    def test_counts(self):
        day = datetime.date(2026, 4, 8)
        bars = _dawn_session_bars(day) + _day_session_bars(day)
        total, dawn, day_n = count_session_bars(bars)
        self.assertEqual(total, len(bars))
        self.assertEqual(dawn, EXPECTED_DAWN_BARS)
        self.assertEqual(day_n, EXPECTED_DAY_BARS - 1)


if __name__ == "__main__":
    unittest.main()