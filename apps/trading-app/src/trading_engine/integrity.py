"""Execution integrity: SETTLING / HALT / reconcile / miss circuit breaker.

Owned by TradingEngine as ``_integrity``. Capital freeze is separate
(``CapitalRiskState``); position/flight live on ``Book``.
"""

from __future__ import annotations

import datetime
from collections import deque
from dataclasses import dataclass, field

INTEGRITY_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "_settling",
        "_settle_since",
        "_position_unconfirmed",
        "_reconcile_last_read",
        "_reconcile_read_streak",
        "_severe_drift_broker_read",
        "_severe_drift_read_streak",
        "_converge_flatten_at",
        "_consecutive_missed_entries",
        "_kernel_converging",
        "_pending_generation",
        "_post_exit_reconcile_until",
        "_recent_cleared_orders",
        "_stop_market_flatten_request",
        "_position_drift_detected",
        "_last_reconcile_wall",
        "_exit_order_retry_count",
        "_exit_order_retry_at",
        "_pending_intent_cancel_exchange_dt",
    }
)


@dataclass
class IntegrityState:
    """Truth-driven execution safety (P0-5) + related recovery knobs."""

    # SETTLING: pending timed out → UNKNOWN → broker reconcile; new orders frozen
    _settling: bool = False
    _settle_since: float = 0.0
    # HALT: position unconfirmed vs broker; strategy frozen; kernel converges
    _position_unconfirmed: bool = False
    _reconcile_last_read: tuple[int, str] | None = None
    _reconcile_read_streak: int = 0
    _severe_drift_broker_read: tuple[int, str] | None = None
    _severe_drift_read_streak: int = 0
    _converge_flatten_at: float = 0.0
    _consecutive_missed_entries: int = 0
    _kernel_converging: bool = False
    _pending_generation: int = 0
    _post_exit_reconcile_until: float = 0.0
    _recent_cleared_orders: deque[tuple[str, str, float]] = field(
        default_factory=lambda: deque(maxlen=64)
    )
    # Stop-loss IOC miss → kernel market flatten request
    _stop_market_flatten_request: bool = False
    _position_drift_detected: bool = False
    _last_reconcile_wall: float = 0.0
    _exit_order_retry_count: int = 0
    _exit_order_retry_at: float = 0.0
    _pending_intent_cancel_exchange_dt: datetime.datetime | None = None

    def clear_settling_window(self) -> None:
        """Exit SETTLING (e.g. after pending cleared). HALT flag is sticky."""
        self._settling = False
        self._settle_since = 0.0
        self._reconcile_last_read = None
        self._reconcile_read_streak = 0

    def reset_day_ops(self) -> None:
        """Trading-day rollover: lift HALT + miss CB (operator-equivalent)."""
        self._position_unconfirmed = False
        self._converge_flatten_at = 0.0
        self._consecutive_missed_entries = 0


__all__ = ["IntegrityState", "INTEGRITY_FIELD_NAMES"]
