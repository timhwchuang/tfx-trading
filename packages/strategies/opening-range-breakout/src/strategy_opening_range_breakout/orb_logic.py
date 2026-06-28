"""ORB bar logic — shared with unit tests."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Literal

from strategy_opening_range_breakout.atr_utils import frozen_bar_atr


OrbDir = Literal["Long", "Short"]


@dataclass
class MinuteBar:
    bar_time: dt.time
    open: float
    high: float
    low: float
    close: float
    atr: float = 0.0


@dataclass
class OrbDayState:
    trading_date: dt.date | None = None
    range_high: float = 0.0
    range_low: float = 0.0
    range_bars: int = 0
    range_atr: float = 0.0
    range_finalized: bool = False
    range_skipped: bool = False
    traded: bool = False


def range_end_time(session_start: dt.time, range_minutes: int) -> dt.time:
    base = dt.datetime.combine(dt.date(2000, 1, 1), session_start)
    return (base + dt.timedelta(minutes=range_minutes)).time()


def reset_day_state(state: OrbDayState, day: dt.date) -> None:
    state.trading_date = day
    state.range_high = 0.0
    state.range_low = 0.0
    state.range_bars = 0
    state.range_atr = 0.0
    state.range_finalized = False
    state.range_skipped = False
    state.traded = False


def finalize_range(
    state: OrbDayState,
    *,
    min_range_atr_k: float,
    range_minutes: int,
    min_atr_floor: float,
) -> None:
    state.range_finalized = True
    if state.range_bars < max(1, range_minutes // 2):
        state.range_skipped = True
        return
    if state.range_bars <= 0:
        state.range_skipped = True
        return
    width = state.range_high - state.range_low
    frozen_atr = frozen_bar_atr(state.range_atr, min_atr_floor=min_atr_floor)
    if width < min_range_atr_k * frozen_atr:
        state.range_skipped = True


def absorb_range_bar(
    state: OrbDayState,
    bar: MinuteBar,
    *,
    atr: float = 0.0,
    min_atr_floor: float = 25.0,
) -> None:
    state.range_high = max(state.range_high, bar.high) if state.range_bars else bar.high
    state.range_low = min(state.range_low, bar.low) if state.range_bars else bar.low
    state.range_bars += 1
    if atr > 0:
        state.range_atr = frozen_bar_atr(atr, min_atr_floor=min_atr_floor)


def breakout_direction(
    close: float,
    *,
    range_high: float,
    range_low: float,
    buffer_atr_k: float,
    atr: float,
) -> OrbDir | None:
    threshold = buffer_atr_k * atr
    if close > range_high + threshold:
        return "Long"
    if close < range_low - threshold:
        return "Short"
    return None


def on_bar_closed(
    state: OrbDayState,
    bar: MinuteBar,
    *,
    session_start: dt.time,
    range_minutes: int,
    buffer_atr_k: float,
    min_range_atr_k: float,
    atr: float,
    min_atr_floor: float,
) -> OrbDir | None:
    """Update ORB state; return entry direction if this bar triggers first break."""
    range_end = range_end_time(session_start, range_minutes)
    bar_atr = frozen_bar_atr(bar.atr if bar.atr > 0 else atr, min_atr_floor=min_atr_floor)

    if session_start <= bar.bar_time < range_end:
        absorb_range_bar(state, bar, atr=bar_atr, min_atr_floor=min_atr_floor)
        return None

    if not state.range_finalized:
        finalize_range(
            state,
            min_range_atr_k=min_range_atr_k,
            range_minutes=range_minutes,
            min_atr_floor=min_atr_floor,
        )

    if state.range_skipped or state.traded:
        return None

    range_atr = frozen_bar_atr(
        state.range_atr if state.range_atr > 0 else bar_atr,
        min_atr_floor=min_atr_floor,
    )
    direction = breakout_direction(
        bar.close,
        range_high=state.range_high,
        range_low=state.range_low,
        buffer_atr_k=buffer_atr_k,
        atr=range_atr,
    )
    if direction is not None:
        state.traded = True
    return direction
