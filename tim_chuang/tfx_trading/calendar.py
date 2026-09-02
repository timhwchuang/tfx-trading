from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

_DEFAULT_DIR = Path(__file__).resolve().parent / "trade_days"


class TradeCalendar:
    def __init__(self, trade_days_dir: Path | None = None) -> None:
        self._dir = trade_days_dir if trade_days_dir is not None else _DEFAULT_DIR
        self._holidays: dict[int, dict[date, bool]] = {}

    def is_holiday(self, day: date) -> bool:
        return self._year_map(day.year)[self._require_day(day)]

    def is_trade_day(self, day: date) -> bool:
        return not self.is_holiday(day)

    def should_have_file(self, day: date) -> bool:
        if self.is_trade_day(day):
            return True
        prev = day - timedelta(days=1)
        try:
            return self.is_trade_day(prev)
        except FileNotFoundError:
            # D-1 落在未 vendor 的年（例如 2025-01-01 → 2024-12-31）。
            # 當天缺曆仍要 raise；不要猜 12/31 有沒有開市。
            return False

    def settlement_day(self, year: int, month: int) -> date:
        day = _third_wednesday(year, month)
        while not self.is_trade_day(day):
            day += timedelta(days=1)
        return day

    def is_settlement_day(self, day: date) -> bool:
        return day == self.settlement_day(day.year, day.month)

    def _year_map(self, year: int) -> dict[date, bool]:
        cached = self._holidays.get(year)
        if cached is not None:
            return cached
        path = self._dir / f"{year}.json"
        if not path.is_file():
            raise FileNotFoundError(f"找不到交易日曆: {path}")
        raw = json.loads(path.read_text(encoding="utf-8"))
        mapping: dict[date, bool] = {}
        for row in raw:
            key = datetime.strptime(str(row["date"]), "%Y%m%d").date()
            mapping[key] = bool(row["isHoliday"])
        self._holidays[year] = mapping
        return mapping

    def _require_day(self, day: date) -> date:
        if day not in self._year_map(day.year):
            raise KeyError(f"交易日曆沒有日期: {day.isoformat()}")
        return day


def _third_wednesday(year: int, month: int) -> date:
    day = date(year, month, 1)
    while day.weekday() != 2:
        day += timedelta(days=1)
    return day + timedelta(weeks=2)


def expected_day_1m(day: date) -> frozenset[datetime]:
    start = datetime(day.year, day.month, day.day, 8, 46)
    return frozenset(start + timedelta(minutes=i) for i in range(300))


def expected_night_1m(day: date) -> frozenset[datetime]:
    start = datetime(day.year, day.month, day.day, 15, 1)
    return frozenset(start + timedelta(minutes=i) for i in range(840))


def expected_day_5m(day: date) -> frozenset[datetime]:
    start = datetime(day.year, day.month, day.day, 8, 50)
    return frozenset(start + timedelta(minutes=5 * i) for i in range(60))


def expected_night_5m(day: date) -> frozenset[datetime]:
    start = datetime(day.year, day.month, day.day, 15, 5)
    return frozenset(start + timedelta(minutes=5 * i) for i in range(168))


def is_day_session_1m(ts: datetime) -> bool:
    minutes = ts.hour * 60 + ts.minute
    return 8 * 60 + 45 < minutes <= 13 * 60 + 45 or (ts.hour == 13 and ts.minute == 46)


def is_night_evening_1m(ts: datetime) -> bool:
    minutes = ts.hour * 60 + ts.minute
    return minutes > 15 * 60


def is_night_dawn_1m(ts: datetime) -> bool:
    minutes = ts.hour * 60 + ts.minute
    return minutes <= 5 * 60 or (ts.hour == 5 and ts.minute == 1)


def minute_floor(ts: datetime) -> datetime:
    return ts.replace(second=0, microsecond=0)


__all__ = [
    "TradeCalendar",
    "expected_day_1m",
    "expected_day_5m",
    "expected_night_1m",
    "expected_night_5m",
    "is_day_session_1m",
    "is_night_dawn_1m",
    "is_night_evening_1m",
    "minute_floor",
]
