"""Order pipeline mixins (Phase E Wave 3).

Composed as ``OrderExecutorMixin`` for TradingEngine MRO compatibility.
"""

from trading_engine.orders.callbacks import OrderCallbackMixin
from trading_engine.orders.fill import OrderFillMixin
from trading_engine.orders.flight import OrderFlightMixin
from trading_engine.orders.flatten import OrderFlattenMixin
from trading_engine.orders.place import OrderPlaceMixin
from trading_engine.orders.settle import OrderSettleMixin
from trading_engine.orders.strategy_host import StrategyHostMixin


class OrderExecutorMixin(
    OrderFlightMixin,
    OrderPlaceMixin,
    OrderCallbackMixin,
    OrderFillMixin,
    OrderFlattenMixin,
    OrderSettleMixin,
    StrategyHostMixin,
):
    """Composite order lifecycle (flight → place → callback → fill → settle)."""


__all__ = [
    "OrderExecutorMixin",
    "OrderFlightMixin",
    "OrderPlaceMixin",
    "OrderCallbackMixin",
    "OrderFillMixin",
    "OrderFlattenMixin",
    "OrderSettleMixin",
    "StrategyHostMixin",
]
