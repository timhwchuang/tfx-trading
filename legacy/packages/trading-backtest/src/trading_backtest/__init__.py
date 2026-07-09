"""Deterministic tick replay for trading-engine (reuses exact TradingEngine from trading-engine)."""

from trading_backtest._version import __version__
from trading_backtest.engine import BacktestEngine, VirtualClock
from trading_backtest.loader import DEFAULT_CACHE_DIR, ReplayTick, iter_replay_ticks
from trading_backtest.mock_broker import MockBroker
from trading_backtest.validation import (
    AuditCaptureHandler,
    FillComparisonReport,
    capture_backtest_audits,
    compare_fill_audits,
    format_fill_comparison,
    hash_audit_records,
    parse_fill_audits,
    parse_fill_audits_from_file,
)

__all__ = [
    "AuditCaptureHandler",
    "BacktestEngine",
    "DEFAULT_CACHE_DIR",
    "FillComparisonReport",
    "MockBroker",
    "ReplayTick",
    "VirtualClock",
    "__version__",
    "capture_backtest_audits",
    "compare_fill_audits",
    "format_fill_comparison",
    "hash_audit_records",
    "iter_replay_ticks",
    "parse_fill_audits",
    "parse_fill_audits_from_file",
]

__version__ = __version__  # re-export at package level (consistent with trading-engine)
