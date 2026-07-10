"""Shared runtime types used across strategy, runtime, and backtest."""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from trading_engine.core.audit.signal_audit import SignalAudit


@dataclass
class OrderSignal:
    action: str  # "Buy" | "Sell"
    qty: int
    ref_price: float
    intent: str  # "entry" | "exit"
    exchange_ts: int = 0
    audit: SignalAudit | None = None
    slippage_points: int | None = None
    signal_id: str = ""  # assigned by kernel (FT-001 Phase 2)
    # P0-5: emergency market order (guaranteed fill, no limit). Used by kernel for
    # stop-loss IOC-miss escalation and HALT convergence flatten. Never set by the
    # strategy for normal entries/profit exits.
    market: bool = False


@dataclass
class MarketSnapshot:
    """Market state at a single tick (Host owns no strategy indicators)."""

    ts: int
    price: float
    dt: datetime.datetime


@dataclass
class PositionSnapshot:
    has_position: bool
    position_dir: str
    entry_price: float
    trailing_peak: float
    entry_exchange_ts: int
    ticks_since_entry: int
    qty: int = 0


@dataclass
class RiskGate:
    """Pre-computed runtime guards passed into strategy evaluation."""

    api_connected: bool
    is_pending: bool
    exit_pending: bool
    cooldown_active: bool
    in_trading_session: bool
    # Composed entry block (ops latch OR active capital freeze). Not the raw
    # Book.block_new_entry alone — see capital_frozen / entry_blocked on host.
    block_new_entry: bool
    consecutive_loss: int  # metric only; not a capital gate
    daily_pnl: float
    after_flatten_time: bool
    force_flatten: bool
    reconnect_warmup_active: bool = False
    # P0-5 (truth-driven execution): order outcome unknown after timeout
    # (awaiting broker reconcile) / position not yet confirmed against broker
    # (HALT). Strategy MUST return None for both entry and exit when set; the
    # kernel owns convergence in these states.
    settling: bool = False
    position_unconfirmed: bool = False
    # Progressive capital book (not day-scoped)
    capital_frozen: bool = False
    realized_pnl: float = 0.0
    equity_peak: float = 0.0
    current_drawdown: float = 0.0


@dataclass(frozen=True)
class EngineStateSnapshot:
    """Read-only view of TradingEngine runtime state.

    Obtain via ``TradingEngine.get_state_snapshot()``.
    Do **not** mutate ``TradingEngine`` attributes directly.
    """

    position_qty: int
    position_dir: str
    entry_price: float
    is_pending: bool
    pending_intent: str | None
    exit_pending: bool
    pending_qty: int
    filled_qty: int
    daily_pnl: float
    consecutive_loss: int
    # Composed entry block (ops | active capital freeze), same as RiskGate.
    block_new_entry: bool
    api_connected: bool
    has_position: bool
    trailing_peak: float
    ticks_since_entry: int
    settling: bool = False
    position_unconfirmed: bool = False
    capital_frozen: bool = False  # sticky book flag; gate may ignore if mdd off
    realized_pnl: float = 0.0
    equity_peak: float = 0.0
    current_drawdown: float = 0.0


@dataclass
class StrategySideEffects:
    """Side effects returned by a Strategy's evaluate() method.

    Currently only used for the daily loss block, but kept extensible.
    """

    block_new_entry: bool = False


@dataclass
class TickSnapshot:
    """Broker-agnostic normalized tick used internally by the engine.

    Live adapters (e.g. Shioaji) are responsible for converting their native
    tick objects into this before calling into engine hot paths.
    """

    ts: int
    price: float
    volume: int
    tick_type: int
    exchange_dt: datetime.datetime
