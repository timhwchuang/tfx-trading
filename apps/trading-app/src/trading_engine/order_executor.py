"""Order lifecycle facade — implementation in ``trading_engine.orders`` (Phase E/G3).

Import stability:
  ``from trading_engine.order_executor import OrderExecutor``
  ``from trading_engine.order_executor import OrderExecutorMixin``  # alias

Re-exports the shared pipeline ``logger`` so tests may patch
``trading_engine.order_executor.logger`` (same object as ``orders.logutil.logger``).
"""

from trading_engine.orders import OrderExecutor, OrderExecutorMixin
from trading_engine.orders.logutil import logger

__all__ = ["OrderExecutor", "OrderExecutorMixin", "logger"]
