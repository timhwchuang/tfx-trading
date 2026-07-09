"""Replay plan types for CF-aligned kernel backtest."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


LegTag = Literal["long_entry", "long_exit", "short_entry", "short_exit"]


@dataclass(frozen=True)
class TradeEvent:
    """Timed order event derived from counterfactual stack pick."""

    ts: int
    action: Literal["Buy", "Sell"]
    price: float
    leg: LegTag
    reason: str = ""


@dataclass
class DayReplayPlan:
  """Per-day replay schedule for GudtRouteAStrategy."""

  day: str
  path: str
  events: list[TradeEvent] = field(default_factory=list)
  meta: dict[str, Any] = field(default_factory=dict)
  skipped: bool = False

  @property
  def route_a_extended(self) -> bool:
    return bool(self.meta.get("route_a_extended"))

  @property
  def hedge(self) -> str:
    return str(self.meta.get("hedge", "none"))

  @property
  def dist_confirm(self) -> str | None:
    v = self.meta.get("dist_confirm")
    return str(v) if v is not None else None

  @property
  def expected_net(self) -> float:
    return float(self.meta.get("net", 0.0))
