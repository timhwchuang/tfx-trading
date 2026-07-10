"""Position + in-flight order book (max_qty=1 Host model).

Book is the single owner of held position and the single pending flight.
Flat ⇄ Flight(entry) ⇄ Long|Short ⇄ Flight(exit) ⇄ Flat.

Call sites use explicit ``host._book.*`` (Phase G1 — no engine ``__getattr__``).
Capital risk (progressive MDD) stays in ``CapitalRiskState`` — not here.

**Mutation policy (Phase E):** prefer Book methods over scattering
``position_qty = …`` on the host. Strategy must never write these fields.

``trailing_peak`` is a **legacy bag field** for snapshot/audit compatibility;
kernel does not implement trailing-stop logic. Do not add new strategy peak
logic here — keep it in Strategy private state if needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from trading_engine.core.types import PositionSnapshot

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
    # Legacy bag: entry fill seeds peak=price; strategy owns true trailing if any.
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

    # --- Position mutations (canonical write path) ---

    def clear_position(self) -> None:
        """Full flatten bookkeeping (after successful exit / resync flat)."""
        self.position_qty = 0
        self.position_dir = "Flat"
        self.entry_price = 0.0
        self.trailing_peak = 0.0
        self.entry_exchange_ts = 0
        self.ticks_since_entry = 0

    def clear_entry_tracking(self) -> None:
        self.entry_exchange_ts = 0
        self.ticks_since_entry = 0

    def begin_entry_tracking(self, exchange_ts: int) -> None:
        self.entry_exchange_ts = exchange_ts
        self.ticks_since_entry = 0

    def apply_entry_fill(
        self, qty: int, price: float, direction: str, exchange_ts: int
    ) -> None:
        """Kernel entry fill: open position from completed entry flight."""
        self.position_qty = qty
        self.entry_price = price
        self.position_dir = direction
        self.trailing_peak = price  # legacy seed only
        self.begin_entry_tracking(exchange_ts)

    def apply_exit_leg(self, price: float, deal_qty: int) -> tuple[int, float]:
        """Reduce held qty on one exit deal leg.

        Returns ``(leg_qty, leg_pnl)``. Updates ``daily_pnl`` and
        ``_pending_exit_pnl``. Does not clear entry metadata until full flat
        via ``clear_position``.
        """
        leg_qty = min(deal_qty, self.position_qty)
        if leg_qty <= 0:
            return 0, 0.0
        if self.position_dir == "Long":
            leg_pnl = (price - self.entry_price) * leg_qty
        else:
            leg_pnl = (self.entry_price - price) * leg_qty
        self.position_qty -= leg_qty
        self.daily_pnl += leg_pnl
        self._pending_exit_pnl += leg_pnl
        return leg_qty, leg_pnl

    def adopt_broker_position(
        self,
        qty: int,
        direction: str,
        entry_price: float = 0.0,
        *,
        preserve_peak: bool = False,
        clear_entry_tracking: bool = True,
    ) -> tuple[int, int]:
        """Adopt broker truth into the kernel book.

        Returns ``(qty_before, qty_after)``.
        """
        qty_before = self.position_qty
        if qty <= 0:
            self.clear_position()
            return qty_before, 0
        self.position_qty = int(qty)
        self.position_dir = direction
        self.entry_price = float(entry_price)
        if not preserve_peak:
            self.trailing_peak = self.entry_price
        if clear_entry_tracking:
            self.clear_entry_tracking()
        return qty_before, self.position_qty

    def set_qty_dir(self, qty: int, direction: str) -> None:
        """Set held qty/dir (converge path).

        Flat (qty<=0) fully clears position metadata via ``clear_position``.
        Non-flat only updates qty/dir so entry_price can still seed flatten
        ``ref_price`` fallbacks.
        """
        if qty <= 0:
            self.clear_position()
        else:
            self.position_qty = int(qty)
            self.position_dir = direction

    def note_tick_while_held(self) -> None:
        """Hot path: count ticks while a position is open."""
        if self.position_qty > 0:
            self.ticks_since_entry += 1

    def mark_exit_time(self, exchange_ts: int) -> None:
        self.last_exit_time = int(exchange_ts)

    def to_position_snapshot(self) -> PositionSnapshot:
        """Read-only view for Strategy.evaluate (never mutate host from this)."""
        return PositionSnapshot(
            has_position=self.has_position,
            position_dir=self.position_dir,
            entry_price=self.entry_price,
            trailing_peak=self.trailing_peak,
            entry_exchange_ts=self.entry_exchange_ts,
            ticks_since_entry=self.ticks_since_entry,
            qty=self.position_qty,
        )

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
