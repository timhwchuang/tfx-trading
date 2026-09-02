from __future__ import annotations

from datetime import datetime

from tfx_trading.strategy.protocol import DecisionContext
from tfx_trading.trading.models import Intent


class FixedTimeStrategy:
    """Emit a fixed intent list at given 5m-close timestamps; otherwise []."""

    def __init__(self, schedule: dict[datetime, list[Intent]]) -> None:
        self._schedule = schedule

    def decide(self, ctx: DecisionContext) -> list[Intent]:
        return list(self._schedule.get(ctx.bar_1m.timestamp, []))


__all__ = [
    "FixedTimeStrategy",
]
