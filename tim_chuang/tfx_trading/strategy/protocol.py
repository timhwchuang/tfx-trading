from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from tfx_trading.kbar import KBar
from tfx_trading.trading.models import Intent, Order, Position


@dataclass(frozen=True)
class DecisionContext:
    bar_1m: KBar
    bars_5m: tuple[KBar, ...]
    position: Position
    pending: tuple[Order, ...]


class Strategy(Protocol):
    def decide(self, ctx: DecisionContext) -> list[Intent]: ...


__all__ = [
    "DecisionContext",
    "Strategy",
]
