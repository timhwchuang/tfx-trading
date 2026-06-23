"""Order event type constants shared by live and mock brokers."""

from __future__ import annotations

from typing import Any

FUTURES_ORDER = "FuturesOrder"
FUTURES_DEAL = "FuturesDeal"


def normalize_order_stat(stat: Any) -> str:
    # Shioaji OrderState is str-like (isinstance(..., str) is True) but must use .name
    # for stable matching with FUTURES_ORDER / FUTURES_DEAL.
    name = getattr(stat, "name", None)
    if isinstance(name, str) and name:
        return name
    if isinstance(stat, str):
        return stat
    return str(stat)


def is_futures_order(stat: Any) -> bool:
    return normalize_order_stat(stat) == FUTURES_ORDER


def is_futures_deal(stat: Any) -> bool:
    return normalize_order_stat(stat) == FUTURES_DEAL


__all__ = [
    "FUTURES_DEAL",
    "FUTURES_ORDER",
    "is_futures_deal",
    "is_futures_order",
    "normalize_order_stat",
]
