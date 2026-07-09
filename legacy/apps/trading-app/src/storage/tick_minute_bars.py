"""Batch tick → per-minute OHLCV (offline repair / audit helpers)."""

from __future__ import annotations

import datetime
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from storage.tick_loader import ReplayTick


@dataclass(frozen=True)
class MinuteBar:
    minute: datetime.datetime
    Open: float
    High: float
    Low: float
    Close: float
    Volume: int


def _minute_floor(ts: datetime.datetime) -> datetime.datetime:
    return ts.replace(second=0, microsecond=0)


def aggregate_ticks_to_minute_bars(
    ticks: Iterable[ReplayTick],
) -> dict[datetime.datetime, MinuteBar]:
    """Build OHLCV per calendar minute from raw ticks (volume = sum, no dedupe)."""
    ordered = sorted(ticks, key=lambda t: t.datetime)
    vol: dict[datetime.datetime, int] = defaultdict(int)
    o: dict[datetime.datetime, float] = {}
    h: dict[datetime.datetime, float] = {}
    l: dict[datetime.datetime, float] = {}
    c: dict[datetime.datetime, float] = {}
    for tick in ordered:
        m = _minute_floor(tick.datetime)
        price = float(tick.close)
        vol[m] += int(tick.volume)
        if m not in o:
            o[m] = price
            h[m] = price
            l[m] = price
            c[m] = price
        else:
            h[m] = max(h[m], price)
            l[m] = min(l[m], price)
            c[m] = price
    return {
        m: MinuteBar(
            minute=m, Open=o[m], High=h[m], Low=l[m], Close=c[m], Volume=vol[m]
        )
        for m in sorted(vol)
    }


__all__ = ["MinuteBar", "aggregate_ticks_to_minute_bars"]
