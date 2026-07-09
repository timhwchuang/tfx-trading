"""Incremental tick → 1m kbar aggregation for live SessionBars feed."""

from __future__ import annotations

import datetime

from storage.kbar_loader import KBarRecord

DAY_ANCHOR = datetime.time(8, 45)
DAY_END = datetime.time(13, 45)
DAY_SETTLEMENT_TAIL = datetime.time(13, 46)
NIGHT_ANCHOR = datetime.time(15, 0)
DAWN_END = datetime.time(5, 0)
DAWN_SETTLEMENT_TAIL = datetime.time(5, 1)


def minute_floor(ts: datetime.datetime) -> datetime.datetime:
    return ts.replace(second=0, microsecond=0)


def kbar_ts_for_tick_minute(minute: datetime.datetime) -> datetime.datetime:
    """Map tick calendar minute to on-disk kbar ``ts`` (close minute label)."""
    return minute + datetime.timedelta(minutes=1)


def _contiguous_tradable_minutes(
    start: datetime.datetime,
    end: datetime.datetime,
) -> bool:
    """True when every calendar minute in [start, end) is tradable."""
    cur = start
    while cur < end:
        if not tick_minute_tradable(cur):
            return False
        cur += datetime.timedelta(minutes=1)
    return True


def tick_minute_tradable(minute: datetime.datetime) -> bool:
    """True when a calendar minute lies in a Yuanta tradable session leg."""
    t = minute.time()
    if t >= NIGHT_ANCHOR:
        return True
    if t <= DAWN_END or t == DAWN_SETTLEMENT_TAIL:
        return True
    if DAY_ANCHOR <= t <= DAY_END or t == DAY_SETTLEMENT_TAIL:
        return True
    return False


class MinuteBarAggregator:
    """Stream ticks into closed 1m ``KBarRecord`` bars on minute rollover."""

    def __init__(self) -> None:
        self._minute: datetime.datetime | None = None
        self._open = 0.0
        self._high = 0.0
        self._low = 0.0
        self._close = 0.0
        self._volume = 0

    def seed_minute(
        self,
        minute: datetime.datetime,
        *,
        open_: float,
        high: float,
        low: float,
        close: float,
        volume: int,
    ) -> None:
        """Resume aggregation from the open tick-minute (warm-load path)."""
        self._minute = minute_floor(minute)
        self._open = float(open_)
        self._high = float(high)
        self._low = float(low)
        self._close = float(close)
        self._volume = int(volume)

    def on_tick(
        self,
        exchange_dt: datetime.datetime,
        price: float,
        volume: int,
    ) -> list[KBarRecord]:
        minute = minute_floor(exchange_dt)
        if self._minute is not None and minute < self._minute:
            return []
        closed: list[KBarRecord] = []
        rolled = False
        if self._minute is not None and minute > self._minute:
            rolled = True
            closed.append(self._emit())
            self._minute += datetime.timedelta(minutes=1)
            if _contiguous_tradable_minutes(self._minute, minute):
                while self._minute < minute:
                    last_close = closed[-1].Close
                    closed.append(
                        KBarRecord(
                            ts=kbar_ts_for_tick_minute(self._minute),
                            Open=last_close,
                            High=last_close,
                            Low=last_close,
                            Close=last_close,
                            Volume=0,
                        )
                    )
                    self._minute += datetime.timedelta(minutes=1)
            else:
                self._minute = minute
        if self._minute != minute:
            self._minute = minute
            self._open = self._high = self._low = self._close = float(price)
            self._volume = int(volume)
        elif rolled:
            self._open = self._high = self._low = self._close = float(price)
            self._volume = int(volume)
        else:
            p = float(price)
            self._high = max(self._high, p)
            self._low = min(self._low, p)
            self._close = p
            self._volume += int(volume)
        return closed

    def flush(self) -> KBarRecord | None:
        """Emit the in-progress minute bar (session shutdown)."""
        if self._minute is None:
            return None
        bar = self._emit()
        self._minute = None
        self._volume = 0
        return bar

    def _emit(self) -> KBarRecord:
        if self._minute is None:
            raise RuntimeError("aggregator minute not set")
        return KBarRecord(
            ts=kbar_ts_for_tick_minute(self._minute),
            Open=self._open,
            High=self._high,
            Low=self._low,
            Close=self._close,
            Volume=self._volume,
        )


__all__ = [
    "MinuteBarAggregator",
    "kbar_ts_for_tick_minute",
    "minute_floor",
    "tick_minute_tradable",
]