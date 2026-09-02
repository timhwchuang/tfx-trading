from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal

IntentKind = Literal["place_limit", "place_stop", "cancel", "flatten"]
OrderKind = Literal["limit", "stop", "flatten"]
Side = Literal["long", "short"]
OrderStatus = Literal["pending", "filled", "cancelled", "expired", "rejected"]
RejectReason = Literal["dynamic_price_band", "limit_lock", "other"]
TradeReason = Literal["stop", "target", "flatten", "entry_stopped"]

_TERMINAL: frozenset[OrderStatus] = frozenset({"filled", "cancelled", "expired", "rejected"})
_PLACE_KINDS: frozenset[IntentKind] = frozenset({"place_limit", "place_stop"})


@dataclass(frozen=True)
class Intent:
    """Strategy output. side is buy/sell direction, not the held position.

    Enter long limit → side=long (buy). Flatten a long → kind=flatten, side=short
    (sell to close), price=None. Cancel → side=None.
    """

    intent_id: str
    kind: IntentKind
    side: Side | None
    price: float | None
    qty: int
    expire_at: datetime | None
    target_intent_id: str | None

    def __post_init__(self) -> None:
        if not self.intent_id:
            raise ValueError("intent_id must be non-empty")
        if self.qty != 1:
            raise ValueError("qty must be 1")
        if self.kind == "cancel":
            if self.side is not None:
                raise ValueError("cancel side must be None")
            if self.price is not None:
                raise ValueError("cancel price must be None")
            if not self.target_intent_id:
                raise ValueError("cancel requires target_intent_id")
            return
        if self.side is None:
            raise ValueError("side is required unless cancel")
        if self.target_intent_id is not None:
            raise ValueError("target_intent_id is only valid on cancel")
        if self.kind == "flatten":
            if self.price is not None:
                raise ValueError("flatten price must be None")
            return
        if self.kind in _PLACE_KINDS and self.price is None:
            raise ValueError(f"{self.kind} requires price")


@dataclass(frozen=True)
class Order:
    """Working order. kind is limit/stop/flatten (no place_ prefix).

    side is who is buying or selling. Flatten a long uses side=short.
    """

    order_id: str
    intent_id: str
    kind: OrderKind
    side: Side
    price: float | None
    qty: int
    expire_at: datetime | None
    status: OrderStatus
    reject_reason: RejectReason | None

    def __post_init__(self) -> None:
        if not self.order_id:
            raise ValueError("order_id must be non-empty")
        if not self.intent_id:
            raise ValueError("intent_id must be non-empty")
        if self.qty < 1:
            raise ValueError("qty must be >= 1")
        rejected = self.status == "rejected"
        has_reason = self.reject_reason is not None
        if rejected != has_reason:
            raise ValueError("reject_reason is set if and only if status is rejected")
        if self.kind == "flatten":
            if self.price is not None:
                raise ValueError("flatten price must be None")
        elif self.price is None:
            raise ValueError(f"{self.kind} requires price")


def transition(
    order: Order,
    new_status: OrderStatus,
    reject_reason: RejectReason | None = None,
) -> Order:
    if order.status != "pending":
        raise ValueError(f"cannot transition from {order.status}")
    if new_status not in _TERMINAL:
        raise ValueError(f"cannot transition to {new_status}")
    if new_status == "rejected":
        if reject_reason is None:
            raise ValueError("rejected requires reject_reason")
        return replace(order, status="rejected", reject_reason=reject_reason)
    if reject_reason is not None:
        raise ValueError("reject_reason is only valid when transitioning to rejected")
    return replace(order, status=new_status, reject_reason=None)


@dataclass(frozen=True)
class Fill:
    ts: datetime
    price: float
    qty: int
    intent_id: str
    order_id: str

    def __post_init__(self) -> None:
        if self.qty < 1:
            raise ValueError("qty must be >= 1")


@dataclass(frozen=True)
class Position:
    side: Side | None
    qty: int
    avg_price: float | None

    def __post_init__(self) -> None:
        if self.side is None:
            if self.qty != 0 or self.avg_price is not None:
                raise ValueError("flat position requires qty=0 and avg_price=None")
            return
        if self.qty < 1 or self.avg_price is None:
            raise ValueError("open position requires qty>=1 and avg_price")


@dataclass(frozen=True)
class TradeRecord:
    """Closed round trip. side is the position that was held, not the exit order.

    A stopped-out long is side='long'. That differs from Intent/Order.side, which
    is buy/sell (flatten a long → Order.side='short').
    """

    side: Side
    entry_ts: datetime
    entry_price: float
    exit_ts: datetime
    exit_price: float
    qty: int
    pnl_nt: float
    r_multiple: float | None
    reason: TradeReason


__all__ = [
    "Fill",
    "Intent",
    "IntentKind",
    "Order",
    "OrderKind",
    "OrderStatus",
    "Position",
    "RejectReason",
    "Side",
    "TradeReason",
    "TradeRecord",
    "transition",
]
