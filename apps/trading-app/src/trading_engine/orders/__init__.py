"""Order pipeline (Phase E Wave 3 + Phase G3 OrderExecutor service)."""

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
    """

    def __init__(self, host: OrderHost) -> None:
        super().__init__(host, *_ORDER_MIXINS)

    def start(self) -> None:
        if self._host._order_sync_mode:
            return
        self._start_order_worker()

    def stop(self) -> None:
        if self._host._order_sync_mode:
            return
        try:
            self._host._order_queue.put_nowait(None)
        except Exception:
            pass


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
