"""TF-agnostic SMC bar helpers for OSF research (Yuanta close-ts bars)."""

from __future__ import annotations

import bisect
import datetime
from dataclasses import dataclass
from typing import Literal, Sequence

from storage.kbar_loader import KBarRecord

SwingLookback = int
ZonePosition = Literal["discount", "premium", "mid"]
BosSide = Literal["bullish", "bearish"]


@dataclass(frozen=True)
class FvgZone:
    side: Literal["bullish", "bearish"]
    fvg_low: float
    fvg_high: float
    created_ts: datetime.datetime


@dataclass(frozen=True)
class BosState:
    last_bos: BosSide | None
    last_bos_ts: datetime.datetime | None
    sweep_reclaim: bool
    sweep_side: Literal["bullish", "bearish"] | None
    last_swing_high: float | None
    last_swing_low: float | None


def _is_swing_high(bars: Sequence[KBarRecord], i: int, lookback: int) -> bool:
    if i < lookback or i + lookback >= len(bars):
        return False
    pivot = bars[i].High
    for k in range(1, lookback + 1):
        if bars[i - k].High >= pivot or bars[i + k].High >= pivot:
            return False
    return True


def _is_swing_low(bars: Sequence[KBarRecord], i: int, lookback: int) -> bool:
    if i < lookback or i + lookback >= len(bars):
        return False
    pivot = bars[i].Low
    for k in range(1, lookback + 1):
        if bars[i - k].Low <= pivot or bars[i + k].Low <= pivot:
            return False
    return True


def _swing_holds_high(bars: Sequence[KBarRecord], i: int, pivot: float, lag: int) -> bool:
    for k in range(1, lag + 1):
        if bars[i + k].High > pivot:
            return False
    return True


def _swing_holds_low(bars: Sequence[KBarRecord], i: int, pivot: float, lag: int) -> bool:
    for k in range(1, lag + 1):
        if bars[i + k].Low < pivot:
            return False
    return True


def detect_fvgs(bars: Sequence[KBarRecord]) -> list[FvgZone]:
    zones: list[FvgZone] = []
    for i in range(2, len(bars)):
        b0, b2 = bars[i - 2], bars[i]
        if b0.High < b2.Low:
            zones.append(
                FvgZone(
                    side="bullish",
                    fvg_low=float(b0.High),
                    fvg_high=float(b2.Low),
                    created_ts=b2.ts,
                )
            )
        elif b0.Low > b2.High:
            zones.append(
                FvgZone(
                    side="bearish",
                    fvg_low=float(b2.High),
                    fvg_high=float(b0.Low),
                    created_ts=b2.ts,
                )
            )
    return zones


def is_fvg_mitigated(zone: FvgZone, bars: Sequence[KBarRecord], *, as_of: datetime.datetime) -> bool:
    for bar in bars:
        if bar.ts <= zone.created_ts or bar.ts > as_of:
            continue
        if bar.Low <= zone.fvg_low and bar.High >= zone.fvg_high:
            return True
    return False


def active_bullish_fvg(
    bars: Sequence[KBarRecord],
    *,
    as_of: datetime.datetime,
    max_age_bars: int,
    tf_minutes: int,
) -> FvgZone | None:
    """Latest unmitigated bullish FVG still valid at ``as_of``."""
    ts_index = [b.ts for b in bars]
    as_of_idx = bisect.bisect_right(ts_index, as_of) - 1
    live: list[FvgZone] = []
    for zone in detect_fvgs(bars):
        if zone.side != "bullish" or is_fvg_mitigated(zone, bars, as_of=as_of):
            continue
        created_idx = bisect.bisect_right(ts_index, zone.created_ts) - 1
        if created_idx < 0 or as_of_idx < created_idx:
            continue
        age = as_of_idx - created_idx
        if 0 <= age <= max_age_bars:
            live.append(zone)
    if not live:
        return None
    return max(live, key=lambda z: z.created_ts)


def analyze_bos(bars: Sequence[KBarRecord], *, swing_lookback: int = 2) -> BosState:
    lookback = max(1, swing_lookback)
    lag = lookback
    last_bos: BosSide | None = None
    last_bos_ts: datetime.datetime | None = None
    sweep_reclaim = False
    sweep_side: Literal["bullish", "bearish"] | None = None
    last_sh: float | None = None
    last_sl: float | None = None
    last_sh_ts: datetime.datetime | None = None
    last_sl_ts: datetime.datetime | None = None
    n = len(bars)

    for j in range(n):
        for i in range(max(0, j - lag), j):
            confirm_idx = i + lag
            if confirm_idx != j:
                continue
            if _is_swing_high(bars, i, lookback) and _swing_holds_high(
                bars, i, bars[i].High, lag
            ):
                last_sh = float(bars[i].High)
                last_sh_ts = bars[j].ts
            if _is_swing_low(bars, i, lookback) and _swing_holds_low(
                bars, i, bars[i].Low, lag
            ):
                last_sl = float(bars[i].Low)
                last_sl_ts = bars[j].ts

        bar = bars[j]
        if last_sh is not None and last_sh_ts is not None and bar.ts > last_sh_ts:
            if bar.Close > last_sh:
                last_bos = "bullish"
                last_bos_ts = bar.ts
        if last_sl is not None and last_sl_ts is not None and bar.ts > last_sl_ts:
            if bar.Close < last_sl:
                last_bos = "bearish"
                last_bos_ts = bar.ts
            if bar.Low < last_sl and bar.Close > last_sl:
                sweep_reclaim = True
                sweep_side = "bullish"

    return BosState(
        last_bos=last_bos,
        last_bos_ts=last_bos_ts,
        sweep_reclaim=sweep_reclaim,
        sweep_side=sweep_side,
        last_swing_high=last_sh,
        last_swing_low=last_sl,
    )


def range_position(
    bars: Sequence[KBarRecord],
    price: float,
    *,
    lookback: int,
) -> ZonePosition:
    if not bars or lookback <= 0:
        return "mid"
    tail = list(bars)[-lookback:]
    hi = max(float(b.High) for b in tail)
    lo = min(float(b.Low) for b in tail)
    if hi <= lo:
        return "mid"
    pos = (price - lo) / (hi - lo)
    if pos < 0.35:
        return "discount"
    if pos > 0.65:
        return "premium"
    return "mid"


def daily_bias_long(
    daily_bars: Sequence[KBarRecord],
    *,
    ma20: float | None,
) -> bool:
    if len(daily_bars) < 2:
        return False
    d0, d1 = daily_bars[-1], daily_bars[-2]
    momentum = float(d0.Close) > float(d1.Close)
    above_ma = ma20 is not None and float(d0.Close) > ma20
    return momentum and above_ma


def higher_lows_1h(bars_1h: Sequence[KBarRecord], *, n: int = 3) -> bool:
    if len(bars_1h) < n + 1:
        return False
    lows = [float(b.Low) for b in bars_1h[-(n + 1) :]]
    return all(lows[i] < lows[i + 1] for i in range(len(lows) - 1))


def displacement_before_fvg(
    bars: Sequence[KBarRecord],
    fvg: FvgZone,
    *,
    min_body_atr_k: float,
    atr: float,
) -> bool:
    """Impulsive leg into FVG: bar before gap body >= k * ATR."""
    if atr <= 0:
        return True
    idx = next((i for i, b in enumerate(bars) if b.ts == fvg.created_ts), None)
    if idx is None or idx < 1:
        return False
    imp = bars[idx - 1]
    body = abs(float(imp.Close) - float(imp.Open))
    return body >= min_body_atr_k * atr