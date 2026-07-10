"""Shared logger for order pipeline modules (single object for test patches)."""

from trading_engine.logging_setup import get_logger

logger = get_logger()

__all__ = ["logger"]
