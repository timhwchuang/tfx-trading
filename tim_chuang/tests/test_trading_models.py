from __future__ import annotations

from datetime import datetime

import pytest

from tfx_trading.trading.models import (
    Intent,
    IntentKind,
    Order,
    OrderKind,
    OrderStatus,
    Position,
    RejectReason,
    Side,
    transition,
)


def _intent(
    *,
    intent_id: str = "i1",
    kind: IntentKind = "place_limit",
    side: Side | None = "long",
    price: float | None = 20000.0,
    qty: int = 1,
    expire_at: datetime | None = None,
    target_intent_id: str | None = None,
) -> Intent:
    return Intent(
        intent_id=intent_id,
        kind=kind,
        side=side,
        price=price,
        qty=qty,
        expire_at=expire_at,
        target_intent_id=target_intent_id,
    )


def _pending_order(
    *,
    order_id: str = "o1",
    intent_id: str = "i1",
    kind: OrderKind = "limit",
    side: Side = "long",
    price: float | None = 20000.0,
    qty: int = 1,
    expire_at: datetime | None = None,
    status: OrderStatus = "pending",
    reject_reason: RejectReason | None = None,
) -> Order:
    return Order(
        order_id=order_id,
        intent_id=intent_id,
        kind=kind,
        side=side,
        price=price,
        qty=qty,
        expire_at=expire_at,
        status=status,
        reject_reason=reject_reason,
    )


def test_intent_qty_must_be_one() -> None:
    with pytest.raises(ValueError, match="qty"):
        _intent(qty=2)


def test_intent_cancel_requires_target() -> None:
    with pytest.raises(ValueError, match="target_intent_id"):
        _intent(kind="cancel", side=None, price=None, target_intent_id=None)


def test_intent_place_limit_requires_price() -> None:
    with pytest.raises(ValueError, match="price"):
        _intent(kind="place_limit", price=None)


def test_intent_flatten_rejects_price() -> None:
    with pytest.raises(ValueError, match="price"):
        _intent(kind="flatten", side="short", price=20000.0)


def test_flatten_long_uses_sell_side() -> None:
    # Flatten a long: sell to close. side is buy/sell, not the held position.
    intent = _intent(kind="flatten", side="short", price=None)
    assert intent.kind == "flatten"
    assert intent.side == "short"
    assert intent.price is None


def test_order_rejected_requires_reason() -> None:
    with pytest.raises(ValueError, match="reject_reason"):
        _pending_order(status="rejected", reject_reason=None)


def test_order_filled_cannot_carry_reason() -> None:
    with pytest.raises(ValueError, match="reject_reason"):
        _pending_order(status="filled", reject_reason="other")


def test_transition_only_from_pending() -> None:
    filled = transition(_pending_order(), "filled")
    assert filled.status == "filled"
    with pytest.raises(ValueError, match="cannot transition"):
        transition(filled, "rejected", reject_reason="other")


def test_transition_rejected_requires_reason() -> None:
    with pytest.raises(ValueError, match="reject_reason"):
        transition(_pending_order(), "rejected")


def test_transition_filled_rejects_reason() -> None:
    with pytest.raises(ValueError, match="reject_reason"):
        transition(_pending_order(), "filled", reject_reason="other")


def test_transition_rejected_to_pending_fails() -> None:
    rejected = transition(_pending_order(), "rejected", reject_reason="limit_lock")
    with pytest.raises(ValueError, match="cannot transition"):
        transition(rejected, "pending")


def test_position_flat_invariants() -> None:
    flat = Position(side=None, qty=0, avg_price=None)
    assert flat.side is None
    with pytest.raises(ValueError):
        Position(side=None, qty=1, avg_price=None)
    with pytest.raises(ValueError):
        Position(side=None, qty=0, avg_price=20000.0)


def test_position_open_invariants() -> None:
    open_pos = Position(side="long", qty=1, avg_price=20000.0)
    assert open_pos.qty == 1
    with pytest.raises(ValueError):
        Position(side="long", qty=0, avg_price=20000.0)
    with pytest.raises(ValueError):
        Position(side="short", qty=1, avg_price=None)


def test_expire_at_is_naive() -> None:
    expire_at = datetime(2026, 6, 15, 13, 40)
    assert expire_at.tzinfo is None
    intent = _intent(expire_at=expire_at)
    assert intent.expire_at == expire_at
