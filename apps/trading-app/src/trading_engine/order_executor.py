"""Order lifecycle facade — implementation in ``trading_engine.orders`` (Phase E Wave 3).

Kept for import stability: ``from trading_engine.order_executor import OrderExecutorMixin``.
Re-exports the shared pipeline ``logger`` so tests may patch
``trading_engine.order_executor.logger`` (same object as ``orders.logutil.logger``).
"""

from trading_engine.orders import OrderExecutorMixin
from trading_engine.orders.logutil import logger

__all__ = ["OrderExecutorMixin", "logger"]
