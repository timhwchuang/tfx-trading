"""ATR-scaled distance helpers (minimal copy from vwap-momentum trend utils)."""

from __future__ import annotations


def dynamic_atr_distance(
    atr: float,
    *,
    floor: float,
    atr_k: float,
) -> float:
    if atr <= 0:
        return floor
    return max(floor, round(atr * atr_k, 2))
