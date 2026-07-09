"""Tests for SessionBars query facade."""

from __future__ import annotations

import datetime
import os
import unittest
from dataclasses import dataclass, field

from storage.bars import SessionBars
from storage.bars.spec import parse_query
from storage.kbar_loader import KBarRecord
from storage.session_bar_cache import TodayKbarStatus


def _bar(ts: datetime.datetime, close: float) -> KBarRecord:
    return KBarRecord(ts, close, close + 1, close - 1, close, 10)


@dataclass
class FakeBarStore:
    code: str = "TX"
    as_of: datetime.datetime = field(
        default_factory=lambda: datetime.datetime(2026, 5, 21, 13, 46)
    )
    today_status: TodayKbarStatus = field(
        default_factory=lambda: TodayKbarStatus(
            date=datetime.date(2026, 5, 21),
            file_exists=True,
            total_bars=1,
            dawn_bars=0,
            day_bars=1,
            is_saturday=False,
            is_trading_day=True,
            ready=True,
            reason="ok",
        )
    )
    _closed: dict[str, list[KBarRecord]] = field(default_factory=dict)
    _current: dict[str, KBarRecord | None] = field(default_factory=dict)
    _daily: list[KBarRecord] = field(default_factory=list)

    def closed(self, tf: str) -> list[KBarRecord]:
        return list(self._closed.get(tf, []))

    def current(self, tf: str) -> KBarRecord | None:
        return self._current.get(tf)

    def daily_closed(self) -> list[KBarRecord]:
        return list(self._daily)

    def daily_ma(self, period: int) -> float | None:
        closes = [float(b.Close) for b in self._daily]
        if len(closes) < period:
            return None
        return sum(closes[-period:]) / period

    def daily_mas(self) -> dict[str, float | None]:
        return {
            "ma5": self.daily_ma(5),
            "ma20": self.daily_ma(20),
            "ma60": self.daily_ma(60),
        }

    def on_new_1m(self, bar: KBarRecord) -> None:
        self._closed.setdefault("1m", []).append(bar)


class TestQueryParser(unittest.TestCase):
    def test_ma_aliases(self):
        q = parse_query("1m", "20ma")
        self.assertEqual(q.kind, "ma")
        self.assertEqual(q.ma_period, 20)
        q2 = parse_query("1m", "ma20")
        self.assertEqual(q2.ma_period, 20)

    def test_daily_alias(self):
        q = parse_query("1d", "ma20")
        self.assertEqual(q.tf, "daily")
        self.assertEqual(q.kind, "ma")


class TestSessionBarsFakeStore(unittest.TestCase):
    def setUp(self) -> None:
        self.store = FakeBarStore()
        base = datetime.datetime(2026, 5, 21, 10, 0)
        self.store._closed["5m"] = [_bar(base + datetime.timedelta(minutes=i * 5), 100 + i) for i in range(10)]
        self.store._current["5m"] = _bar(base + datetime.timedelta(minutes=50), 199)
        self.store._daily = [_bar(datetime.datetime(2026, 5, d, 13, 45), 4000 + d) for d in range(1, 25)]
        self.bars = SessionBars(self.store)

    def test_get_series(self):
        series = self.bars.get("5m")
        self.assertEqual(len(series), 10)
        self.assertEqual(self.bars.get("5m", 3)[-1].Close, 109)

    def test_get_last_and_current(self):
        self.assertEqual(self.bars.get("5m", "last").Close, 109)
        self.assertEqual(self.bars.get("5m", "current").Close, 199)

    def test_get_ma(self):
        self.assertEqual(self.bars.get("5m", "ma3"), 108.0)

    def test_series_and_closes(self):
        self.assertEqual(len(self.bars.series("5m", n=4)), 4)
        self.assertEqual(self.bars.closes("5m", n=2), [108.0, 109.0])

    def test_daily_ma(self):
        self.assertIsNotNone(self.bars.get("daily", "ma20"))

    def test_today(self):
        status = self.bars.get("today")
        self.assertTrue(status.ready)


class TestSessionBarsIntegration(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("RUN_SLOW_STORAGE"), "set RUN_SLOW_STORAGE=1 to run")
    def test_may_ohlc_regression(self):
        try:
            from storage.cache_paths import DEFAULT_TICK_CACHE_DIR
        except ImportError:
            self.skipTest("cache paths unavailable")
        path = DEFAULT_TICK_CACHE_DIR / "TMFR1_kbars_2026-05-11.csv"
        if not path.exists():
            self.skipTest("TMFR1 May cache not on disk")

        as_of = datetime.datetime(2026, 5, 11, 13, 45)
        bars = SessionBars.load("TMFR1", as_of, cache_dir=DEFAULT_TICK_CACHE_DIR)
        last11 = bars.get("daily", "last")
        self.assertIsNotNone(last11)
        self.assertEqual(
            (int(last11.Open), int(last11.High), int(last11.Low), int(last11.Close)),
            (41997, 42297, 41669, 41955),
        )

        bars21 = SessionBars.load(
            "TMFR1",
            datetime.datetime(2026, 5, 21, 13, 46),
            cache_dir=DEFAULT_TICK_CACHE_DIR,
        )
        last21 = bars21.get("daily", "last")
        self.assertEqual(last21.ts.date(), datetime.date(2026, 5, 21))
        self.assertEqual(
            (int(last21.Open), int(last21.High), int(last21.Low), int(last21.Close)),
            (40273, 41666, 40219, 41497),
        )


if __name__ == "__main__":
    unittest.main()