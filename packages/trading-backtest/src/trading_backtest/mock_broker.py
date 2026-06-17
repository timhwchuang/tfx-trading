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

    def resolve_contract(self, code: str) -> SimpleNamespace:
        return SimpleNamespace(code=code)

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
                "arrive_after": self.clock() + self.latency_ms / 1000.0,
            }
        )
        return SimpleNamespace(order=SimpleNamespace(id=order_id))

    def update_status(self, trade: Any = None) -> None:
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
        for ord in list(self.inflight):
            if tick_ts < ord["arrive_after"]:
                continue
            self.inflight.remove(ord)
            intent = self._intent_for(host, ord["order_id"])
            slippage = self._slippage_for(tick, intent, self.NORMAL_SLIP)
            close = self._tick_close(tick)
            limit = ord["limit_price"]
            is_buy = ord["action"] == "Buy"
            if is_buy:
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
                host.handle_order_event(
                    FUTURES_DEAL,
                    {
                        "price": fill,
                        "quantity": ord["quantity"],
                        "action": ord["action"],
                        "trade_id": ord["order_id"],
                    },
                )


__all__ = ["MockBroker"]
