"""Tests for live tick → 1m → SessionBars feed."""

from __future__ import annotations

import datetime
import json
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from storage.bars import SessionBars
from unittest import mock

from storage.kbar_loader import (
    KBarRecord,
    append_kbar_csv,
    kbar_path,
    load_kbars_csv,
    read_last_kbar_ts,
    save_kbars_csv,
)
from storage.live_session_bars import LiveSessionBars
from storage.minute_bar_aggregator import MinuteBarAggregator, kbar_ts_for_tick_minute
from storage.session_bar_cache import TodayKbarStatus, kbar_file_date


@dataclass
class _FakeTick:
    datetime: datetime.datetime
    close: float
    volume: int


class TestMinuteBarAggregator(unittest.TestCase):
    def test_minute_rollover_emits_kbar_ts(self):
        agg = MinuteBarAggregator()
        t0 = datetime.datetime(2026, 5, 21, 10, 30, 15)
        self.assertEqual(agg.on_tick(t0, 100.0, 5), [])
        self.assertEqual(agg.on_tick(t0.replace(second=40), 101.0, 3), [])

        t1 = datetime.datetime(2026, 5, 21, 10, 31, 1)
        bars = agg.on_tick(t1, 102.0, 2)
        self.assertEqual(len(bars), 1)
        bar = bars[0]
        self.assertEqual(bar.ts, kbar_ts_for_tick_minute(datetime.datetime(2026, 5, 21, 10, 30)))
        self.assertEqual(bar.ts, datetime.datetime(2026, 5, 21, 10, 31))
        self.assertEqual(bar.Open, 100.0)
        self.assertEqual(bar.High, 101.0)
        self.assertEqual(bar.Low, 100.0)
        self.assertEqual(bar.Close, 101.0)
        self.assertEqual(bar.Volume, 8)

    def test_out_of_order_tick_is_ignored(self):
        agg = MinuteBarAggregator()
        t0 = datetime.datetime(2026, 5, 21, 10, 30, 0)
        t1 = datetime.datetime(2026, 5, 21, 10, 31, 0)
        agg.on_tick(t0, 100.0, 5)
        bars = agg.on_tick(t1, 110.0, 2)
        self.assertEqual(len(bars), 1)
        bar = bars[0]
        late = agg.on_tick(t0.replace(second=30), 50.0, 99)
        self.assertEqual(late, [])
        bars2 = agg.on_tick(
            datetime.datetime(2026, 5, 21, 10, 32, 0),
            120.0,
            1,
        )
        self.assertEqual(len(bars2), 1)
        bar2 = bars2[0]
        self.assertEqual(bar2.Open, 110.0)
        self.assertEqual(bar2.Close, 110.0)
        self.assertEqual(bar2.Volume, 2)

    def test_minute_gap_emits_synthetic_bars(self):
        agg = MinuteBarAggregator()
        t0 = datetime.datetime(2026, 5, 21, 10, 30, 0)
        agg.on_tick(t0, 100.0, 5)
        bars = agg.on_tick(datetime.datetime(2026, 5, 21, 10, 33, 0), 120.0, 1)
        self.assertEqual(len(bars), 3)
        self.assertEqual(bars[0].ts, datetime.datetime(2026, 5, 21, 10, 31))
        self.assertEqual(bars[0].Close, 100.0)
        self.assertEqual(bars[1].ts, datetime.datetime(2026, 5, 21, 10, 32))
        self.assertEqual(bars[1].Volume, 0)
        self.assertEqual(bars[2].ts, datetime.datetime(2026, 5, 21, 10, 33))
        self.assertEqual(bars[2].Close, 100.0)

    def test_gap_skips_closed_session_interval(self):
        agg = MinuteBarAggregator()
        t0 = datetime.datetime(2026, 5, 21, 8, 40, 0)
        agg.on_tick(t0, 100.0, 5)
        bars = agg.on_tick(datetime.datetime(2026, 5, 21, 9, 0, 0), 120.0, 1)
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0].ts, datetime.datetime(2026, 5, 21, 8, 41))
        self.assertEqual(bars[0].Close, 100.0)


class _RecordingBars:
    def __init__(self) -> None:
        self.code = "TX"
        self.as_of = datetime.datetime(2026, 5, 21, 10, 35)
        self.ingested: list[KBarRecord] = []

    def on_bar(self, bar: KBarRecord) -> None:
        self.ingested.append(bar)


class TestLiveSessionBars(unittest.TestCase):
    def test_on_tick_feeds_closed_minute(self):
        recording = _RecordingBars()
        feed = LiveSessionBars(recording)  # type: ignore[arg-type]
        feed.on_tick(_FakeTick(datetime.datetime(2026, 5, 21, 10, 30, 0), 100, 1), 1)
        feed.on_tick(_FakeTick(datetime.datetime(2026, 5, 21, 10, 31, 0), 110, 2), 1)
        self.assertEqual(len(recording.ingested), 1)
        self.assertEqual(recording.ingested[0].Close, 100.0)

    def test_persist_kbar_append(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            store = _RecordingBars()
            store.code = "TX"
            feed = LiveSessionBars(store, cache_dir=cache, persist_kbars=True)  # type: ignore[arg-type]
            feed.on_tick(_FakeTick(datetime.datetime(2026, 5, 21, 10, 30, 0), 100, 1), 1)
            feed.on_tick(_FakeTick(datetime.datetime(2026, 5, 21, 10, 31, 0), 110, 2), 1)
            path = kbar_path(cache, "TX", datetime.date(2026, 5, 21))
            bars = load_kbars_csv(path)
            self.assertEqual(len(bars), 1)
            self.assertEqual(bars[0].ts, datetime.datetime(2026, 5, 21, 10, 31))

    def test_read_last_kbar_ts(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            path = kbar_path(cache, "TX", datetime.date(2026, 5, 21))
            bar = KBarRecord(
                datetime.datetime(2026, 5, 21, 10, 31),
                100.0,
                101.0,
                99.0,
                100.5,
                10,
            )
            save_kbars_csv([bar], path)
            self.assertEqual(read_last_kbar_ts(path), bar.ts)

    def test_append_kbar_skips_via_last_ts(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            path = kbar_path(cache, "TX", datetime.date(2026, 5, 21))
            bar = KBarRecord(
                datetime.datetime(2026, 5, 21, 10, 31),
                100.0,
                101.0,
                99.0,
                100.5,
                10,
            )
            self.assertTrue(append_kbar_csv(bar, path))
            with mock.patch(
                "storage.kbar_loader.load_kbars_csv",
                side_effect=AssertionError("should not load full file"),
            ):
                self.assertFalse(
                    append_kbar_csv(bar, path, last_ts=bar.ts),
                )

    def test_append_kbar_skips_duplicate_ts(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            path = kbar_path(cache, "TX", datetime.date(2026, 5, 21))
            bar = KBarRecord(
                datetime.datetime(2026, 5, 21, 10, 31),
                100.0,
                101.0,
                99.0,
                100.5,
                10,
            )
            self.assertTrue(append_kbar_csv(bar, path))
            self.assertFalse(append_kbar_csv(bar, path))
            self.assertEqual(len(load_kbars_csv(path)), 1)

    def test_persist_uses_kbar_file_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            cal = cache / "trade_days"
            cal.mkdir(parents=True)
            wed = datetime.date(2026, 5, 20)
            thu = datetime.date(2026, 5, 21)
            (cal / "2026.json").write_text(
                json.dumps(
                    [
                        {"date": "20260520", "isHoliday": False},
                        {"date": "20260521", "isHoliday": False},
                    ]
                ),
                encoding="utf-8",
            )
            from tests.storage.test_session_bar_cache import _evening_bars

            save_kbars_csv(_evening_bars(wed, 60), kbar_path(cache, "TX", wed))
            as_of = datetime.datetime.combine(thu, datetime.time(10, 30))
            bars = SessionBars.load("TX", as_of, cache_dir=cache, calendar_dir=cal)
            feed = LiveSessionBars(
                bars,
                cache_dir=cache,
                persist_kbars=True,
                as_of=as_of,
            )
            feed.on_tick(_FakeTick(datetime.datetime(2026, 5, 21, 10, 30, 0), 100, 1), 1)
            feed.on_tick(_FakeTick(datetime.datetime(2026, 5, 21, 10, 31, 0), 110, 2), 1)
            bundle_path = kbar_path(cache, "TX", wed)
            wrong_path = kbar_path(cache, "TX", thu)
            self.assertTrue(bundle_path.is_file())
            self.assertFalse(wrong_path.is_file())
            persisted = load_kbars_csv(bundle_path)
            new_ts = datetime.datetime(2026, 5, 21, 10, 31)
            self.assertIn(new_ts, {b.ts for b in persisted})
            bar = next(b for b in persisted if b.ts == new_ts)
            self.assertEqual(kbar_file_date(bar, bars.cache.trading_days), wed)

    def test_gap_fill_not_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            cal = cache / "trade_days"
            cal.mkdir(parents=True)
            day = datetime.date(2026, 5, 21)
            (cal / "2026.json").write_text(
                json.dumps([{"date": "20260521", "isHoliday": False}]),
                encoding="utf-8",
            )
            from tests.storage.test_session_bar_cache import _day_session_bars

            cutoff = datetime.datetime.combine(day, datetime.time(10, 29))
            save_kbars_csv(
                [b for b in _day_session_bars(day) if b.ts <= cutoff],
                kbar_path(cache, "TX", day),
            )
            as_of = datetime.datetime.combine(day, datetime.time(10, 30))
            bars = SessionBars.load("TX", as_of, cache_dir=cache, calendar_dir=cal)
            baseline_day = bars.get("today").day_bars
            feed = LiveSessionBars(
                bars,
                cache_dir=cache,
                persist_kbars=True,
                as_of=as_of,
            )
            feed.on_tick(_FakeTick(datetime.datetime(2026, 5, 21, 10, 30, 0), 100, 1), 1)
            feed.on_tick(_FakeTick(datetime.datetime(2026, 5, 21, 10, 33, 0), 120, 2), 1)
            feed.on_tick(_FakeTick(datetime.datetime(2026, 5, 21, 10, 34, 0), 130, 1), 1)
            self.assertEqual(bars.get("today").day_bars, baseline_day + 2)
            self.assertNotIn(
                datetime.datetime(2026, 5, 21, 10, 32),
                bars.cache._bars_1m_map,
            )
            persist_path = next(iter(feed._path_last_ts))
            persisted = load_kbars_csv(persist_path)
            ts_set = {b.ts for b in persisted}
            self.assertEqual(len(persisted), 2)
            self.assertTrue(all(b.Volume > 0 for b in persisted))
            self.assertIn(datetime.datetime(2026, 5, 21, 10, 31), ts_set)
            self.assertIn(datetime.datetime(2026, 5, 21, 10, 34), ts_set)
            self.assertNotIn(datetime.datetime(2026, 5, 21, 10, 32), ts_set)

    def test_reload_resets_aggregator_and_dedupe(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            cal = cache / "trade_days"
            cal.mkdir(parents=True)
            day = datetime.date(2026, 5, 21)
            (cal / "2026.json").write_text(
                json.dumps([{"date": "20260521", "isHoliday": False}]),
                encoding="utf-8",
            )
            from tests.storage.test_session_bar_cache import _day_session_bars

            cutoff = datetime.datetime.combine(day, datetime.time(10, 29))
            save_kbars_csv(
                [b for b in _day_session_bars(day) if b.ts <= cutoff],
                kbar_path(cache, "TX", day),
            )
            as_of = datetime.datetime.combine(day, datetime.time(10, 30))
            bars = SessionBars.load("TX", as_of, cache_dir=cache, calendar_dir=cal)
            feed = LiveSessionBars(
                bars,
                cache_dir=cache,
                persist_kbars=True,
                as_of=as_of,
            )
            feed.on_tick(_FakeTick(datetime.datetime(2026, 5, 21, 10, 30, 0), 100, 1), 1)
            feed.on_tick(_FakeTick(datetime.datetime(2026, 5, 21, 10, 31, 0), 110, 2), 1)
            self.assertEqual(feed.bars_written, 1)

            persist_path = next(iter(feed._path_last_ts))
            lines = persist_path.read_text(encoding="utf-8").splitlines()
            patched: list[str] = []
            for line in lines:
                if "2026-05-21T10:31" in line:
                    cols = line.split(",")
                    cols[4] = "999.0"
                    line = ",".join(cols)
                patched.append(line)
            persist_path.write_text("\n".join(patched) + "\n", encoding="utf-8")

            reload_as_of = datetime.datetime.combine(day, datetime.time(10, 31))
            feed.reload(reload_as_of, calendar_dir=cal)
            bar = feed.session_bars.cache._bars_1m_map[
                datetime.datetime(2026, 5, 21, 10, 31)
            ]
            self.assertEqual(bar.Close, 999.0)
            feed.on_tick(_FakeTick(datetime.datetime(2026, 5, 21, 10, 32, 0), 120, 1), 1)
            feed.on_tick(_FakeTick(datetime.datetime(2026, 5, 21, 10, 33, 0), 130, 1), 1)
            self.assertGreater(feed.bars_written, 1)

    def test_start_seeds_aggregator_from_loaded_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            cal = cache / "trade_days"
            cal.mkdir(parents=True)
            day = datetime.date(2026, 5, 21)
            (cal / "2026.json").write_text(
                json.dumps([{"date": "20260521", "isHoliday": False}]),
                encoding="utf-8",
            )
            from tests.storage.test_session_bar_cache import _day_session_bars

            save_kbars_csv(_day_session_bars(day), kbar_path(cache, "TX", day))
            as_of = datetime.datetime.combine(day, datetime.time(10, 30))
            bars = SessionBars.load("TX", as_of, cache_dir=cache, calendar_dir=cal)
            feed = LiveSessionBars(bars, cache_dir=cache, as_of=as_of)
            feed.on_tick(_FakeTick(datetime.datetime(2026, 5, 21, 10, 30, 0), 100, 1), 1)
            feed.on_tick(_FakeTick(datetime.datetime(2026, 5, 21, 10, 31, 0), 110, 2), 1)
            self.assertEqual(feed.bars_written, 1)
            self.assertIn(datetime.datetime(2026, 5, 21, 10, 31), feed.session_bars.cache._bars_1m_map)
            self.assertIn(datetime.datetime(2026, 5, 21, 10, 30), feed._ingested_ts)


class TestArchivePortLiveFeed(unittest.TestCase):
    def test_enqueue_tick_delegates_to_live_bars(self):
        from integrations.archive_port import TradingAppArchivePort

        recording = _RecordingBars()
        feed = LiveSessionBars(recording)  # type: ignore[arg-type]
        port = TradingAppArchivePort(live_bars=feed)
        port.enqueue_tick(_FakeTick(datetime.datetime(2026, 5, 21, 10, 30, 0), 100, 1), 1)
        port.enqueue_tick(_FakeTick(datetime.datetime(2026, 5, 21, 10, 31, 0), 110, 2), 1)
        self.assertEqual(len(recording.ingested), 1)


if __name__ == "__main__":
    unittest.main()