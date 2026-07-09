"""Legacy strategy plugin discovery — removed in lean Host Phase A.

Prefer direct construction and injection:
    TradingEngine(strategy=SimpleStrategy(...), ...)
"""

from __future__ import annotations

from typing import Any

ENTRY_POINT_GROUP = "trading_engine.strategies"


def load_strategy(name: str, **kwargs: Any):
    """Removed: use direct strategy injection instead of entry-point discovery."""
    del name, kwargs
    raise NotImplementedError(
        "trading_engine.plugins.load_strategy was removed in lean Host Phase A. "
        "Inject the strategy directly: TradingEngine(strategy=YourStrategy(...), ...)."
    )


__all__ = ["ENTRY_POINT_GROUP", "load_strategy"]
