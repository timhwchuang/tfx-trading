"""Gap cohort and liquidity pools for OSF long setup."""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from reporting.osf_session_context import dawn_bars, overnight_bars_before_open, session_day_bars
from reporting.volatility_baseline import atr_series_from_bars
from storage.kbar_loader import KBarRecord
from storage.session_bar_cache import DAY_ANCHOR

GapCohort = Literal["gap_up", "gap_down", "flat"]
LiquidityPool = Literal["or_low", "dawn_low", "overnight_low", "none"]

DAY_OPEN = datetime.time(8, 46)
OR_DEFAULT_END = datetime.time(9, 14)
DEFAULT_GAP_FLAT_POINTS = 8.0
DEFAULT_ATR_PERIOD = 14
DEFAULT_MIN_ATR = 25.0


@dataclass(frozen=True)
class OpeningRange:
    high: float
    low: float
    width: float
    end_ts: datetime.datetime
    valid: bool


@dataclass(frozen=True)
class LiquidityLevels:
    or_range: OpeningRange
    dawn_low: float | None
    overnight_low: float | None
    gap_cohort: GapCohort
    gap_points: float
    day_open: float | None
    ref_close: float | None


def _atr_from_bars(bars: Sequence[KBarRecord], idx: int) -> float:
    tuples = [
        (b.High, b.Low, b.Close, b.High - b.Low, float(b.Volume))
        for b in bars[: idx + 1]
    ]
    series = atr_series_from_bars(tuples, period=DEFAULT_ATR_PERIOD)
    if not series:
        return DEFAULT_MIN_ATR
    return max(float(series[-1]), DEFAULT_MIN_ATR)


def compute_opening_range(
    bars_1m: Sequence[KBarRecord],
    day: datetime.date,
    *,
    or_minutes: int = 30,
    min_width_atr_k: float = 0.5,
) -> OpeningRange:
    start = datetime.datetime.combine(day, DAY_ANCHOR)
    or_end_t = (
        datetime.datetime.combine(day, DAY_ANCHOR) + datetime.timedelta(minutes=or_minutes)
    ).time()
    or_end = datetime.datetime.combine(day, or_end_t)
    window = [
        b
        for b in bars_1m
        if start < b.ts <= or_end and b.ts.time() >= DAY_OPEN
    ]
    if not window:
        return OpeningRange(0.0, 0.0, 0.0, or_end, False)
    hi = max(float(b.High) for b in window)
    lo = min(float(b.Low) for b in window)
    width = hi - lo
    atr = _atr_from_bars(list(bars_1m), len(bars_1m) - 1)
    valid = width >= min_width_atr_k * atr
    return OpeningRange(hi, lo, width, or_end, valid)


def compute_gap_cohort(
    bars_1m: Sequence[KBarRecord],
    day: datetime.date,
    *,
    flat_band_points: float = DEFAULT_GAP_FLAT_POINTS,
) -> tuple[GapCohort, float, float | None, float | None]:
    """Gap vs last overnight close before 08:45 day session."""
    overnight = overnight_bars_before_open(list(bars_1m), day)
    day_sess = session_day_bars(list(bars_1m), day)
    if not overnight or not day_sess:
        return "flat", 0.0, None, None
    ref_close = float(overnight[-1].Close)
    day_open_bar = next((b for b in day_sess if b.ts.time() >= DAY_OPEN), None)
    if day_open_bar is None:
        return "flat", 0.0, ref_close, None
    day_open = float(day_open_bar.Open)
    gap = day_open - ref_close
    if gap > flat_band_points:
        return "gap_up", gap, day_open, ref_close
    if gap < -flat_band_points:
        return "gap_down", gap, day_open, ref_close
    return "flat", gap, day_open, ref_close


def compute_liquidity_levels(
    bars_1m: Sequence[KBarRecord],
    day: datetime.date,
    *,
    or_minutes: int = 30,
) -> LiquidityLevels:
    or_range = compute_opening_range(bars_1m, day, or_minutes=or_minutes)
    dawn = dawn_bars(list(bars_1m), day)
    overnight = overnight_bars_before_open(list(bars_1m), day)
    dawn_low = min((float(b.Low) for b in dawn), default=None)
    overnight_low = min((float(b.Low) for b in overnight), default=None)
    gap_cohort, gap_pts, day_open, ref_close = compute_gap_cohort(bars_1m, day)
    return LiquidityLevels(
        or_range=or_range,
        dawn_low=dawn_low,
        overnight_low=overnight_low,
        gap_cohort=gap_cohort,
        gap_points=gap_pts,
        day_open=day_open,
        ref_close=ref_close,
    )


def sweep_pool_hit(
    bar_low: float,
    bar_close: float,
    pool: float,
) -> bool:
    """Sweep below pool and reclaim above pool close."""
    return bar_low < pool and bar_close > pool


def deepest_sweep_pool(hits: list[tuple[LiquidityPool, float]]) -> LiquidityPool:
    """Prefer deepest liquidity grab (lowest pool price swept)."""
    if not hits:
        return "none"
    return min(hits, key=lambda item: item[1])[0]


def classify_sweep_pool(
    bar: KBarRecord,
    levels: LiquidityLevels,
) -> LiquidityPool:
    low = float(bar.Low)
    close = float(bar.Close)
    hits: list[tuple[LiquidityPool, float]] = []
    if levels.or_range.valid and sweep_pool_hit(low, close, levels.or_range.low):
        hits.append(("or_low", levels.or_range.low))
    if levels.dawn_low is not None and sweep_pool_hit(low, close, levels.dawn_low):
        hits.append(("dawn_low", levels.dawn_low))
    if levels.overnight_low is not None and sweep_pool_hit(
        low, close, levels.overnight_low
    ):
        hits.append(("overnight_low", levels.overnight_low))
    return deepest_sweep_pool(hits)