"""Position + in-flight order book (max_qty=1 Host model).

Book is the single owner of held position and the single pending flight.
Flat ⇄ Flight(entry) ⇄ Long|Short ⇄ Flight(exit) ⇄ Flat.

TradingEngine keeps property-compatible access via ``_book`` forwarding so
existing call sites and tests continue to use ``host.position_qty`` etc.
Capital risk (progressive MDD) stays in ``CapitalRiskState`` — not here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Attribute names owned by Book (forwarded from TradingEngine).
BOOK_FIELD_NAMES: frozenset[str] = frozenset(
    {
        # Position
        "position_qty",
        "position_dir",
        "entry_price",
        "entry_exchange_ts",
        "ticks_since_entry",
        "trailing_peak",
        "last_exit_time",
        # Session display PnL / ops (day-resettable; not progressive capital)
        "daily_pnl",
        "consecutive_loss",
        "block_new_entry",  # ops latch; capital freeze is separate
        # Flight (single pending slot)
        "is_pending",
        "pending_intent",
        "exit_pending",
        "pending_trade",
        "pending_order_id",
        "pending_since",
        "pending_exchange_ts",
        "pending_qty",
        "pending_signal_price",
        "pending_limit_price",
        "pending_exit_reason",
        "pending_ioc_slippage",
        "pending_market",
        "pending_episode_id",
        "pending_signal_id",
        "filled_qty",
        "_pending_exit_pnl",
        "_pending_action",
    }
)


@dataclass
class Book:
    """max_qty=1 position + single-flight pending state."""

    # --- Position ---
    position_qty: int = 0
    position_dir: str = "Flat"  # Long | Short | Flat
    entry_price: float = 0.0
    entry_exchange_ts: int = 0
    ticks_since_entry: int = 0
    trailing_peak: float = 0.0
    last_exit_time: int = 0

    # --- Day-scoped session bookkeeping (not progressive capital) ---
    daily_pnl: float = 0.0
    consecutive_loss: int = 0  # metric only
    block_new_entry: bool = False  # ops_entry_blocked (day-resettable)

    # --- Flight ---
    is_pending: bool = False
    pending_intent: str | None = None
    exit_pending: bool = False
    pending_trade: Any = None
    pending_order_id: str | None = None
    pending_since: float = 0.0
    pending_exchange_ts: int = 0
    pending_qty: int = 0
    pending_signal_price: float = 0.0
    pending_limit_price: float = 0.0
    pending_exit_reason: str = ""
    pending_ioc_slippage: int = 0
    pending_market: bool = False
    pending_episode_id: str = ""
    pending_signal_id: str = ""
    filled_qty: int = 0
    _pending_exit_pnl: float = 0.0
    _pending_action: str | None = None

    @property
    def has_position(self) -> bool:
        return self.position_qty > 0

    @property
    def order_in_flight(self) -> bool:
        """Alias: single pending slot is armed."""
        return self.is_pending

    def clear_position(self) -> None:
        """Full flatten bookkeeping (after successful exit / resync flat)."""
        self.position_qty = 0
        self.position_dir = "Flat"
        self.entry_price = 0.0
        self.trailing_peak = 0.0
        self.entry_exchange_ts = 0
        self.ticks_since_entry = 0

    def clear_flight(self) -> dict[str, Any]:
        """Clear pending flight; return snapshot for late-deal registry if needed."""
        snap = {
            "order_id": self.pending_order_id,
            "intent": self.pending_intent,
            "signal_id": self.pending_signal_id,
        }
        self.is_pending = False
        self.pending_intent = None
        self.exit_pending = False
        self.pending_trade = None
        self.pending_order_id = None
        self.pending_since = 0.0
        self.pending_exchange_ts = 0
        self.pending_qty = 0
        self.pending_signal_price = 0.0
        self.pending_limit_price = 0.0
        self.pending_exit_reason = ""
        self.pending_market = False
        self.pending_episode_id = ""
        self.pending_signal_id = ""
        self.filled_qty = 0
        self._pending_exit_pnl = 0.0
        self._pending_action = None
        return snap

    def reset_day_ops(self) -> None:
        """Trading-day rollover: session display + ops latch only."""
        self.daily_pnl = 0.0
        self.block_new_entry = False
        self.consecutive_loss = 0


__all__ = ["BOOK_FIELD_NAMES", "Book"]
