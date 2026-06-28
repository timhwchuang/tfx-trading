"""ATR helpers — match FT-009 counterfactual / volatility_baseline semantics."""

from __future__ import annotations

DEFAULT_ATR_PERIOD = 20

BarHLC = tuple[float, float, float]


def frozen_bar_atr(atr: float, *, min_atr_floor: float) -> float:
    """Match counterfactual _atr_at_bar_index floor (DEFAULT_MIN_ATR)."""
    return max(atr, min_atr_floor)


def atr_series_from_bars(
    bars: list[BarHLC],
    *,
    period: int = DEFAULT_ATR_PERIOD,
) -> list[float]:
    """Rolling SMA(TR, period) — matches reporting.volatility_baseline."""
    if len(bars) < 2:
        return []
    trs: list[float] = []
    for i in range(1, len(bars)):
        h, low, close = bars[i]
        prev_c = bars[i - 1][2]
        tr = max(h - low, abs(h - prev_c), abs(low - prev_c))
        trs.append(tr)
    if len(trs) < period:
        return []
    out: list[float] = []
    for i in range(period - 1, len(trs)):
        out.append(sum(trs[i - period + 1 : i + 1]) / period)
    return out


def atr_at_bar_index(
    bars: list[BarHLC],
    idx: int,
    *,
    period: int = DEFAULT_ATR_PERIOD,
    min_atr_floor: float = 25.0,
) -> float:
    """ATR at bar idx using bars[0:idx+1] — matches orb_counterfactual."""
    if idx < 0 or idx >= len(bars):
        return min_atr_floor
    atrs = atr_series_from_bars(bars[: idx + 1], period=period)
    if not atrs:
        return min_atr_floor
    return frozen_bar_atr(atrs[-1], min_atr_floor=min_atr_floor)


def dynamic_atr_distance(atr: float, *, floor: float, atr_k: float) -> float:
    if atr <= 0:
        return floor
    return max(floor, atr_k * atr)
