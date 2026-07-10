"""Tick arrival / type-inference bookkeeping for watchdogs and logs.

Owned by TradingEngine as ``_ticks``. Behavior (no-tick / clock-skew / summary)
lives in ``tick_watchdog.TickWatchdogMixin``.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any

TICK_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "last_tick_price",
        "last_tick_exchange_ts",
        "_last_tick_wall_time",
        "_last_tick_exchange_dt",
        "_tick_type_counts",
        "_tick_type_inferred_counts",
        "_last_tick_type_log_wall",
        "_last_clock_skew_warn_wall",
        "_last_no_tick_resubscribe_wall",
        "_no_tick_resubscribe_streak",
    }
)


@dataclass
class TickState:
    """Last-tick cache + counters for no-tick / type-summary watchdogs."""

    last_tick_price: float = 0.0
    last_tick_exchange_ts: int = 0
    _last_tick_wall_time: float = 0.0
    _last_tick_exchange_dt: datetime.datetime | None = None
    _tick_type_counts: dict[int, int] = field(
        default_factory=lambda: {0: 0, 1: 0, 2: 0}
    )
    _tick_type_inferred_counts: dict[int, int] = field(
        default_factory=lambda: {1: 0, 2: 0}
    )
    _last_tick_type_log_wall: float = 0.0
    _last_clock_skew_warn_wall: float = 0.0
    _last_no_tick_resubscribe_wall: float = 0.0
    _no_tick_resubscribe_streak: int = 0

    def reset_day_counters(self) -> None:
        """Day rollover: clear type histograms (streaks optional)."""
        self._tick_type_counts = {0: 0, 1: 0, 2: 0}
        self._tick_type_inferred_counts = {1: 0, 2: 0}


__all__ = ["TickState", "TICK_FIELD_NAMES"]
