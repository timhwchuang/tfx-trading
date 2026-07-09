"""Indicators for SessionBars queries."""

from __future__ import annotations

from typing import Sequence

from storage.session_bar_cache import sma


def moving_average(closes: Sequence[float], period: int) -> float | None:
    return sma(closes, period)


__all__ = ["moving_average"]