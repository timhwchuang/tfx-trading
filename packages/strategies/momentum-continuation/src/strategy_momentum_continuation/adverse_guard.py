"""Adverse-move guard for continuation entry (fake vol spike filter)."""

from __future__ import annotations


def adverse_blocks_continuation(
    direction: str,
    *,
    price: float,
    vwap: float,
    atr: float,
    max_adverse_atr_k: float,
) -> bool:
    """True when price is too far against continuation direction vs VWAP.

    Long: skip if price < vwap - k×ATR (buy spike but price still weak).
    Short: skip if price > vwap + k×ATR.
    k<=0 disables the guard.
    """
    if max_adverse_atr_k <= 0:
        return False
    eff_atr = atr if atr > 0 else 25.0
    dist = price - vwap
    limit = max_adverse_atr_k * eff_atr
    if direction == "Long":
        return dist < -limit
    if direction == "Short":
        return dist > limit
    return False
