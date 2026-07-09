"""Generic live session bootstrap (no strategy-specific coordinators)."""

from __future__ import annotations

from typing import Any


def start_live_session(engine: Any) -> None:
    """Run Shioaji live bootstrap for the given TradingEngine."""
    from trading_engine.adapters.shioaji_live import ShioajiLiveBootstrap

    ShioajiLiveBootstrap(engine).start_live()


__all__ = ["start_live_session"]
