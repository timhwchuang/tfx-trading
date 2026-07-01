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
    """Indicator + market state at a single tick."""

    ts: int
    price: float
    dt: datetime.datetime
    vwap: float
    vol_1s: int
    buy_vol_1s: int
    sell_vol_1s: int
    current_atr: float
    trend_dir: str
    trend_strength: float
    structure_bias: str = "Neutral"
    structure_strength: float = 0.0
    structure_in_discount: bool = False
    structure_in_premium: bool = False
    structure_fvg_low: float | None = None
    structure_fvg_high: float | None = None
    structure_sweep_reclaim: bool = False


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
class MomentumState:
    active: bool
    direction: str
    peak: float
    trigger_time: int


@dataclass
class RiskGate:
    """Pre-computed runtime guards passed into strategy evaluation."""

    api_connected: bool
    is_pending: bool
    exit_pending: bool
    cooldown_active: bool
    in_trading_session: bool
    block_new_entry: bool
    consecutive_loss: int
    daily_pnl: float
    after_flatten_time: bool
    force_flatten: bool
    atr_stale: bool = False
    structure_stale: bool = False
    reconnect_warmup_active: bool = False
    # P0-5 (truth-driven execution): order outcome unknown after timeout
    # (awaiting broker reconcile) / position not yet confirmed against broker
    # (HALT). Strategy MUST return None for both entry and exit when set; the
    # kernel owns convergence in these states.
    settling: bool = False
    position_unconfirmed: bool = False


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
    block_new_entry: bool
    api_connected: bool
    has_position: bool
    trailing_peak: float
    ticks_since_entry: int
    settling: bool = False
    position_unconfirmed: bool = False


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
