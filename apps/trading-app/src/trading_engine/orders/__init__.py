"""Order pipeline (Phase E Wave 3 + Phase G3 OrderExecutor service)."""

from __future__ import annotations

import threading

from trading_engine.core.host_service import HostBoundService
from trading_engine.orders.callbacks import OrderCallbackMixin
from trading_engine.orders.fill import OrderFillMixin
from trading_engine.orders.flight import OrderFlightMixin
from trading_engine.orders.flatten import OrderFlattenMixin
from trading_engine.orders.host import OrderHost
from trading_engine.orders.place import OrderPlaceMixin
from trading_engine.orders.settle import OrderSettleMixin
from trading_engine.orders.strategy_host import StrategyHostMixin

_ORDER_MIXINS = (
    OrderFlightMixin,
    OrderPlaceMixin,
    OrderCallbackMixin,
    OrderFillMixin,
    OrderFlattenMixin,
    OrderSettleMixin,
    StrategyHostMixin,
)


class OrderExecutor(HostBoundService):
    """Order lifecycle service (flight → place → callback → fill → settle).

    Methods are host-bound: ``self`` inside pipeline code is TradingEngine.
    Lifecycle ``start``/``stop`` also look up callables on the **host** so
    ``host._start_order_worker = mock`` / ``patch.object(host, ...)`` work.
    """

    _STOP_JOIN_SEC = 5.0

    def __init__(self, host: OrderHost) -> None:
        super().__init__(host, *_ORDER_MIXINS)

    def start(self) -> None:
        h = self._host
        if h._order_sync_mode:
            return
        # Host lookup (not service dict) so test doubles on host are honored.
        starter = getattr(h, "_start_order_worker", None)
        if starter is None:
            return
        starter()

    def stop(self) -> None:
        h = self._host
        if h._order_sync_mode:
            return
        try:
            h._order_queue.put_nowait(None)
        except Exception:
            pass
        t = getattr(h, "_order_worker_thread", None)
        if t is not None and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=self._STOP_JOIN_SEC)
            if t.is_alive():
                h._order_worker_join_timed_out = True


# Historical name (MRO era) — prefer OrderExecutor.
OrderExecutorMixin = OrderExecutor


__all__ = [
    "OrderExecutor",
    "OrderExecutorMixin",
    "OrderHost",
    "OrderFlightMixin",
    "OrderPlaceMixin",
    "OrderCallbackMixin",
    "OrderFillMixin",
    "OrderFlattenMixin",
    "OrderSettleMixin",
    "StrategyHostMixin",
]
