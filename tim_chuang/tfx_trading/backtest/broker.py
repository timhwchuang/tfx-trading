from __future__ import annotations

from datetime import datetime

from tfx_trading.backtest.config import BacktestConfig
from tfx_trading.kbar import KBar
from tfx_trading.trading.costs import (
    POINT_VALUE_NT,
    TICK_SIZE,
    CostConfig,
    apply_slippage,
    close_trade,
)
from tfx_trading.trading.models import (
    Fill,
    Intent,
    Order,
    OrderKind,
    Position,
    Side,
    TradeReason,
    TradeRecord,
    apply_fill,
    transition,
)


def _opposite(side: Side) -> Side:
    return "short" if side == "long" else "long"


class Broker:
    """Simulated book. Owns working orders and Position. Calls close_trade."""

    def __init__(self, cost_cfg: CostConfig, backtest_cfg: BacktestConfig) -> None:
        self._cost = cost_cfg
        self._bt = backtest_cfg
        self._book: dict[str, Order] = {}
        self._position = Position(side=None, qty=0, avg_price=None)
        self._entry_side: Side | None = None
        self._entry_ts: datetime | None = None
        self._entry_price: float | None = None
        self._risk_nt: float | None = None

    @property
    def position(self) -> Position:
        return self._position

    @property
    def pending(self) -> tuple[Order, ...]:
        return tuple(o for o in self._book.values() if o.status == "pending")

    def submit(self, intents: list[Intent], now: object) -> tuple[Order, ...]:
        del now
        created: list[Order] = []
        for intent in intents:
            created.append(self._submit_one(intent))
        return tuple(created)

    def on_bar(self, bar: KBar) -> tuple[tuple[Fill, ...], TradeRecord | None]:
        self._expire(bar)
        flatten = self._pending_flatten()
        if flatten is not None:
            pos = self._position.side
            if pos is None or flatten.side == pos:
                self._set(transition(flatten, "rejected", reject_reason="other"))
            else:
                fill, trade = self._fill_exit(
                    bar, flatten, "flatten", self._flatten_px(bar, flatten)
                )
                return (fill,), trade
        if self._position.side is None:
            return self._fill_while_flat(bar)
        return self._fill_while_open(bar)

    def _submit_one(self, intent: Intent) -> Order:
        if intent.intent_id in self._book:
            return self._reject_untracked(intent)
        if intent.kind == "cancel":
            return self._cancel(intent)
        if intent.kind == "flatten":
            return self._submit_flatten(intent)
        if intent.kind == "place_stop":
            return self._submit_stop(intent)
        return self._submit_limit(intent)

    def _reject_untracked(self, intent: Intent) -> Order:
        side: Side = intent.side if intent.side is not None else "long"
        kind: OrderKind = "limit"
        if intent.kind == "place_stop":
            kind = "stop"
        elif intent.kind == "flatten":
            kind = "flatten"
        price = None if kind == "flatten" else (intent.price if intent.price is not None else 0.0)
        return Order(
            order_id=intent.intent_id,
            intent_id=intent.intent_id,
            kind=kind,
            side=side,
            price=price,
            qty=intent.qty,
            expire_at=intent.expire_at,
            status="rejected",
            reject_reason="other",
        )

    def _cancel(self, intent: Intent) -> Order:
        target_id = intent.target_intent_id or ""
        target = self._book.get(target_id)
        if target is None or target.status != "pending":
            return self._reject_untracked(intent)
        updated = transition(target, "cancelled")
        self._set(updated)
        self._drop_orphan_bracket()
        return updated

    def _submit_flatten(self, intent: Intent) -> Order:
        assert intent.side is not None
        pos = self._position.side
        if pos is None or intent.side == pos or self._pending_flatten() is not None:
            return self._track_reject(intent, "flatten")
        order = self._make_order(intent, "flatten")
        self._set(order)
        return order

    def _submit_limit(self, intent: Intent) -> Order:
        assert intent.side is not None
        pos = self._position.side
        if pos is None:
            entry = self._entry_side
            if entry is None:
                if self._pending_kind("limit", intent.side):
                    return self._track_reject(intent, "limit")
                order = self._make_order(intent, "limit")
                self._set(order)
                self._entry_side = intent.side
                return order
            if intent.side == entry:
                return self._track_reject(intent, "limit")
            if self._pending_kind("limit", intent.side):
                return self._track_reject(intent, "limit")
            order = self._make_order(intent, "limit")
            self._set(order)
            return order
        if intent.side == pos:
            return self._track_reject(intent, "limit")
        if self._pending_kind("limit", intent.side):
            return self._track_reject(intent, "limit")
        order = self._make_order(intent, "limit")
        self._set(order)
        return order

    def _submit_stop(self, intent: Intent) -> Order:
        assert intent.side is not None
        pos = self._position.side
        if pos is None:
            entry = self._entry_side
            if entry is not None and intent.side == entry:
                return self._track_reject(intent, "stop")
            if self._any_pending_stop():
                return self._track_reject(intent, "stop")
            order = self._make_order(intent, "stop")
            self._set(order)
            return order
        if intent.side == pos:
            return self._track_reject(intent, "stop")
        if self._pending_kind("stop", intent.side):
            return self._track_reject(intent, "stop")
        order = self._make_order(intent, "stop")
        self._set(order)
        return order

    def _track_reject(self, intent: Intent, kind: OrderKind) -> Order:
        order = self._make_order(intent, kind, rejected=True)
        self._set(order)
        return order

    def _make_order(self, intent: Intent, kind: OrderKind, *, rejected: bool = False) -> Order:
        assert intent.side is not None
        price = None if kind == "flatten" else intent.price
        if rejected:
            return Order(
                order_id=intent.intent_id,
                intent_id=intent.intent_id,
                kind=kind,
                side=intent.side,
                price=price,
                qty=intent.qty,
                expire_at=intent.expire_at,
                status="rejected",
                reject_reason="other",
            )
        return Order(
            order_id=intent.intent_id,
            intent_id=intent.intent_id,
            kind=kind,
            side=intent.side,
            price=price,
            qty=intent.qty,
            expire_at=intent.expire_at,
            status="pending",
            reject_reason=None,
        )

    def _set(self, order: Order) -> None:
        self._book[order.order_id] = order

    def _pending_kind(self, kind: OrderKind, side: Side) -> list[Order]:
        return [
            o
            for o in self._book.values()
            if o.status == "pending" and o.kind == kind and o.side == side
        ]

    def _any_pending_stop(self) -> bool:
        return any(o.status == "pending" and o.kind == "stop" for o in self._book.values())

    def _pending_flatten(self) -> Order | None:
        for o in self._book.values():
            if o.status == "pending" and o.kind == "flatten":
                return o
        return None

    def _entry_limit(self) -> Order | None:
        if self._entry_side is None:
            return None
        found = self._pending_kind("limit", self._entry_side)
        return found[0] if found else None

    def _expire(self, bar: KBar) -> None:
        for order in list(self._book.values()):
            if order.status != "pending":
                continue
            if order.expire_at is not None and order.expire_at <= bar.timestamp:
                self._set(transition(order, "expired"))
        self._drop_orphan_bracket()

    def _drop_orphan_bracket(self) -> None:
        """If the entry died while flat, cancel resting SL/TP so a new bracket can attach."""
        if self._position.side is not None:
            return
        if self._entry_limit() is not None:
            return
        self._entry_side = None
        for order in list(self._book.values()):
            if order.status != "pending":
                continue
            if order.kind in {"stop", "limit"}:
                self._set(transition(order, "cancelled"))

    def _limit_hit(self, order: Order, bar: KBar) -> bool:
        assert order.price is not None
        if order.side == "long":
            if self._bt.fill_mode == "optimistic":
                return bar.low <= order.price
            return bar.low <= order.price - TICK_SIZE
        if self._bt.fill_mode == "optimistic":
            return bar.high >= order.price
        return bar.high >= order.price + TICK_SIZE

    def _stop_hit(self, order: Order, bar: KBar) -> bool:
        assert order.price is not None
        if order.side == "short":
            return bar.low <= order.price
        return bar.high >= order.price

    def _stop_px(self, bar: KBar, order: Order) -> float:
        assert order.price is not None
        slipped = apply_slippage("stop", order.side, order.price, self._cost)
        if order.side == "short":
            return min(slipped, bar.open)
        return max(slipped, bar.open)

    def _flatten_px(self, bar: KBar, order: Order) -> float:
        return apply_slippage("flatten", order.side, bar.open, self._cost)

    def _fill_while_flat(self, bar: KBar) -> tuple[tuple[Fill, ...], TradeRecord | None]:
        entry = self._entry_limit()
        if entry is None or not self._limit_hit(entry, bar):
            return (), None
        assert entry.price is not None
        open_fill = self._fill_order(bar, entry, entry.price)
        pos_side = entry.side
        self._position = apply_fill(self._position, open_fill, entry.side)
        self._entry_ts = bar.timestamp
        self._entry_price = entry.price
        self._entry_side = pos_side
        self._risk_nt = self._snapshot_risk(entry.price, pos_side)
        stop = self._resting_stop(_opposite(pos_side))
        if stop is not None and self._stop_hit(stop, bar):
            exit_fill, trade = self._fill_exit(bar, stop, "entry_stopped", self._stop_px(bar, stop))
            return (open_fill, exit_fill), trade
        return (open_fill,), None

    def _fill_while_open(self, bar: KBar) -> tuple[tuple[Fill, ...], TradeRecord | None]:
        pos = self._position.side
        assert pos is not None
        opp = _opposite(pos)
        stop = self._resting_stop(opp)
        tp = self._pending_kind("limit", opp)
        sl_hit = stop is not None and self._stop_hit(stop, bar)
        tp_hit = bool(tp) and self._limit_hit(tp[0], bar)
        if sl_hit:
            assert stop is not None
            fill, trade = self._fill_exit(bar, stop, "stop", self._stop_px(bar, stop))
            return (fill,), trade
        if tp_hit:
            target = tp[0]
            assert target.price is not None
            fill, trade = self._fill_exit(bar, target, "target", target.price)
            return (fill,), trade
        return (), None

    def _resting_stop(self, side: Side) -> Order | None:
        found = self._pending_kind("stop", side)
        return found[0] if found else None

    def _snapshot_risk(self, entry_price: float, pos_side: Side) -> float | None:
        stop = self._resting_stop(_opposite(pos_side))
        if stop is None or stop.price is None:
            return None
        return abs(entry_price - stop.price) * POINT_VALUE_NT * stop.qty

    def _fill_order(self, bar: KBar, order: Order, price: float) -> Fill:
        filled = transition(order, "filled")
        self._set(filled)
        return Fill(
            ts=bar.timestamp,
            price=price,
            qty=order.qty,
            intent_id=order.intent_id,
            order_id=order.order_id,
        )

    def _fill_exit(
        self,
        bar: KBar,
        order: Order,
        reason: TradeReason,
        price: float,
    ) -> tuple[Fill, TradeRecord]:
        pos = self._position
        assert pos.side is not None
        assert pos.avg_price is not None
        assert self._entry_ts is not None
        assert self._entry_price is not None
        fill = self._fill_order(bar, order, price)
        trade = close_trade(
            pos.side,
            self._entry_ts,
            self._entry_price,
            bar.timestamp,
            price,
            pos.qty,
            reason,
            self._cost,
            risk_nt=self._risk_nt,
        )
        self._position = apply_fill(pos, fill, order.side)
        self._cancel_exits()
        self._entry_side = None
        self._entry_ts = None
        self._entry_price = None
        self._risk_nt = None
        return fill, trade

    def _cancel_exits(self) -> None:
        for order in list(self._book.values()):
            if order.status != "pending":
                continue
            if order.kind in {"limit", "stop", "flatten"}:
                self._set(transition(order, "cancelled"))
