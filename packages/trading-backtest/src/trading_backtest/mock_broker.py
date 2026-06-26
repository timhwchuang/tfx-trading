"""Heuristic IOC matching for backtesting (close-based, latency + slippage)."""

from __future__ import annotations

import datetime
from collections.abc import Callable
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from trading_engine.calendar.taifex import is_at_or_after
from trading_engine.core.order_events import FUTURES_DEAL, FUTURES_ORDER

from trading_backtest.loader import DEFAULT_CACHE_DIR, iter_kbars_in_range


@dataclass
class _KBars:
    High: list[float]
    Low: list[float]
    Close: list[float]
    ts: list[datetime.datetime] = field(default_factory=list)


class MockBroker:
    """Minimal Shioaji api stand-in for backtest replay."""

    def __init__(
        self,
        clock: Callable[[], float],
        *,
        latency_ms: int = 15,
        NORMAL_SLIP: float = 0.5,
        BLOWOUT_VOL: int = 50,
        BLOWOUT_SLIP: float = 2.5,
        FLATTEN_SLIP: float = 8.0,
        session_force_flatten_time: datetime.time = datetime.time(13, 44),
        cache_dir=DEFAULT_CACHE_DIR,
        spread_calibration: bool = False,
        position_report_delay_sec: float = 0.0,
        deal_report_delay_sec: float = 0.0,
    ) -> None:
        self.clock = clock
        self.latency_ms = latency_ms
        self.NORMAL_SLIP = NORMAL_SLIP
        self.BLOWOUT_VOL = BLOWOUT_VOL
        self.BLOWOUT_SLIP = BLOWOUT_SLIP
        self.FLATTEN_SLIP = FLATTEN_SLIP
        self.session_force_flatten_time = session_force_flatten_time
        self.cache_dir = cache_dir
        self.spread_calibration = spread_calibration
        self.futopt_account = None
        self._seq = 0
        self.inflight: list[dict[str, Any]] = []
        self.current_dt: datetime.datetime | None = None
        # P0-5: track net broker position so list_positions() reflects truth.
        # Signed net lots (Buy = +, Sell = -) and the last establishing price.
        self._net_qty = 0
        self._last_fill_price = 0.0
        self._position_code = "TMFR1"
        # P0-5 fault injection: model the live venue's report latency so tests can
        # reproduce the "stale flat list_positions while a fill is in flight" race.
        # position_report_delay_sec: how long after a fill list_positions reflects it.
        # deal_report_delay_sec: how long after a fill the FUTURES_DEAL callback fires.
        self.position_report_delay_sec = position_report_delay_sec
        self.deal_report_delay_sec = deal_report_delay_sec
        # (apply_at, action, qty, price) position updates pending their report delay.
        self._position_updates: list[tuple[float, str, int, float]] = []
        # (deliver_at, msg) deal callbacks pending their report delay.
        self._delayed_deals: list[tuple[float, dict]] = []

    def resolve_contract(self, code: str) -> SimpleNamespace:
        self._position_code = code
        return SimpleNamespace(code=code)

    def _apply_due_position_updates(self) -> None:
        now = self.clock()
        due = [u for u in self._position_updates if u[0] <= now]
        if not due:
            return
        self._position_updates = [u for u in self._position_updates if u[0] > now]
        for _, action, qty, price in due:
            delta = qty if action == "Buy" else -qty
            self._net_qty += delta
            if self._net_qty != 0:
                self._last_fill_price = price

    def list_positions(self, account: Any = None) -> list[SimpleNamespace]:
        """P0-5: broker position snapshot reflecting net fills (truth source).

        Fills only become visible after ``position_report_delay_sec`` to model
        the live broker's snapshot latency.
        """
        self._apply_due_position_updates()
        if self._net_qty == 0:
            return []
        direction = "Buy" if self._net_qty > 0 else "Sell"
        return [
            SimpleNamespace(
                code=self._position_code,
                quantity=abs(self._net_qty),
                direction=direction,
                price=self._last_fill_price,
            )
        ]

    def _record_fill(self, action: str, qty: int, price: float) -> None:
        """Schedule a net broker position update, delayed by the report latency."""
        apply_at = self.clock() + self.position_report_delay_sec
        self._position_updates.append((apply_at, action, qty, price))
        self._apply_due_position_updates()

    def _deliver_due_deals(self, host: Any) -> None:
        now = self.clock()
        due = [d for d in self._delayed_deals if d[0] <= now]
        if not due:
            return
        self._delayed_deals = [d for d in self._delayed_deals if d[0] > now]
        for _, msg in due:
            host.handle_order_event(FUTURES_DEAL, msg)

    def place_order(self, contract: Any, order: Any, timeout: int = 0) -> SimpleNamespace:
        self._seq += 1
        order_id = f"BT{self._seq}"
        self.inflight.append(
            {
                "order_id": order_id,
                "action": (
                    order.action
                    if isinstance(order.action, str)
                    else ("Buy" if getattr(order.action, "name", None) == "Buy" else "Sell")
                ),
                "limit_price": float(order.price),
                "quantity": int(order.quantity),
                "market": bool(getattr(order, "market", False)),
                "arrive_after": self.clock() + self.latency_ms / 1000.0,
            }
        )
        return SimpleNamespace(order=SimpleNamespace(id=order_id))

    def update_status(self, trade: Any = None, **kwargs: Any) -> None:
        # No-op: backtest resolves via list_positions. Accept **kwargs (e.g. the
        # bounded ``timeout`` Layer 2 passes) so the call is harmless if the flag
        # is ever enabled in a sim/backtest run.
        pass

    def order_deal_records(self) -> list:
        return []

    def usage(self) -> SimpleNamespace:
        return SimpleNamespace(bytes=0, limit_bytes=0, remaining_bytes=0, connections=0)

    def kbars(self, contract: Any, start: str, end: str) -> _KBars:
        code = getattr(contract, "code", str(contract))
        start_date = datetime.date.fromisoformat(start)
        end_date = datetime.date.fromisoformat(end)
        bars = iter_kbars_in_range(code, start_date, end_date, cache_dir=self.cache_dir)
        current = self.current_dt
        highs: list[float] = []
        lows: list[float] = []
        closes: list[float] = []
        tss: list[datetime.datetime] = []
        for bar in bars:
            if current is not None:
                if bar.ts > current:
                    continue
                if bar.ts + datetime.timedelta(minutes=1) > current:
                    continue
            highs.append(bar.High)
            lows.append(bar.Low)
            closes.append(bar.Close)
            tss.append(bar.ts)
        return _KBars(High=highs, Low=lows, Close=closes, ts=tss)

    def _slippage_for(
        self,
        tick: Any,
        intent: str | None,
        base_slippage: float,
    ) -> float:
        slippage = base_slippage
        if tick.volume > self.BLOWOUT_VOL:
            slippage = self.BLOWOUT_SLIP
        if intent == "exit" and is_at_or_after(tick.datetime, self.session_force_flatten_time):
            slippage = self.FLATTEN_SLIP
        if self.spread_calibration:
            ask = getattr(tick, "ask_price", None)
            bid = getattr(tick, "bid_price", None)
            if ask and bid and ask > bid:
                half_spread = (ask - bid) / 2.0
                slippage = max(slippage, half_spread)
        return slippage

    def _intent_for(self, host: Any, order_id: str) -> str | None:
        if getattr(host, "pending_order_id", None) == order_id:
            return getattr(host, "pending_intent", None)
        return None

    @staticmethod
    def _tick_close(tick: Any) -> float:
        """CSV replay uses str close; live ticks may already be float."""
        return float(tick.close)

    def process_matching_queue(self, tick: Any, host: Any) -> None:
        tick_ts = tick.datetime.timestamp()
        # Deliver any deal callbacks whose report delay has now elapsed.
        self._deliver_due_deals(host)
        for ord in list(self.inflight):
            if tick_ts < ord["arrive_after"]:
                continue
            self.inflight.remove(ord)
            intent = self._intent_for(host, ord["order_id"])
            slippage = self._slippage_for(tick, intent, self.NORMAL_SLIP)
            close = self._tick_close(tick)
            limit = ord["limit_price"]
            is_buy = ord["action"] == "Buy"
            if ord.get("market"):
                # Emergency market order: guaranteed fill at close ± slippage
                # (models paying the spread/impact to get out, no limit cross gate).
                fill = close + slippage if is_buy else close - slippage
            elif is_buy:
                if close <= limit:
                    fill = min(limit, close + slippage)
                else:
                    fill = None
            else:
                if close >= limit:
                    fill = max(limit, close - slippage)
                else:
                    fill = None
            if fill is None:
                host.handle_order_event(
                    FUTURES_ORDER,
                    {
                        "operation": {"op_code": "00", "op_type": "Cancel"},
                        "status": {"status": "Cancelled", "deal_quantity": 0},
                        "trade_id": ord["order_id"],
                    },
                )
            else:
                # Record the fill against the broker's own net position first so
                # list_positions() reflects truth even if the kernel callback path
                # drops/ignores it (P0-5 reconcile relies on this). Subject to the
                # configured report delays.
                self._record_fill(ord["action"], ord["quantity"], fill)
                msg = {
                    "price": fill,
                    "quantity": ord["quantity"],
                    "action": ord["action"],
                    "trade_id": ord["order_id"],
                }
                if self.deal_report_delay_sec > 0:
                    self._delayed_deals.append(
                        (self.clock() + self.deal_report_delay_sec, msg)
                    )
                else:
                    host.handle_order_event(FUTURES_DEAL, msg)


__all__ = ["MockBroker"]
