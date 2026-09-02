from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from tfx_trading.kbar import KBar
from tfx_trading.trading.models import Intent, Order, Position, TradeRecord


@dataclass(frozen=True)
class DecisionContext:
    bar_1m: KBar
    bars_5m: tuple[KBar, ...]
    position: Position
    pending: tuple[Order, ...]
    closed_trades: tuple[TradeRecord, ...]
    entry_ts: datetime | None


class Strategy(Protocol):
    def decide(self, ctx: DecisionContext) -> list[Intent]: ...


__all__ = [
    "DecisionContext",
    "Strategy",
]
