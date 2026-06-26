"""Settings dataclass — host app loads YAML/env and passes to RuntimeConfig."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    simulation: bool
    product_code: str

    vwap_window_min: int
    entry_band_points: float
    momentum_vol_1s: int
    momentum_buy_ratio: float
    momentum_sell_ratio: float
    exhaustion_vol: int
    cooldown_sec: int
    momentum_timeout_sec: int
    max_daily_loss_points: int
    max_consecutive_loss: int
    fixed_tp_points: int
    trail_points: int
    atr_period: int
    min_atr_threshold: float
    atr_refresh_sec: int
    atr_kline_lookback_days: int
    pending_timeout_sec: int
    ioc_slippage_points: int
    exit_grace_ticks: int
    exit_grace_sec: int
    hard_stop_points: int
    vwap_stop_points: int
    no_tick_timeout_sec: int
    no_tick_resubscribe_escalate_after: int
    clock_skew_warn_sec: float

    trend_filter_enabled: bool
    trend_timeframe_min: int
    trend_mode: str
    trend_ema_period: int
    trend_slope_min: float
    trend_min_strength: float
    structure_filter_enabled: bool
    structure_timeframe_min: int
    structure_swing_lookback: int
    structure_min_strength: float
    trail_atr_k: float
    trail_points_floor: float
    vwap_stop_atr_k: float
    vwap_stop_points_floor: float
    atr_trailing_enabled: bool
    atr_vwap_stop_enabled: bool

    session_start: datetime.time
    session_end: datetime.time
    session_flatten_time: datetime.time
    session_force_flatten_time: datetime.time
    flatten_slippage_points: int

    base_vol: int
    atr_vol_mult: float
    open_mult_futures: float
    open_mult_spot: float
    open_mult_normal: float

    log_level: str
    log_file: str

    exit_order_max_retries: int
    exit_order_retry_delay_sec: float
    session_watchdog_sec: float
    session_relogin_max_attempts: int
    session_relogin_backoff_base_sec: float
    atr_stale_multiplier: float = 2.0
    reconnect_warmup_sec: int = 300
    max_disconnects_per_day: int = 3
    alert_on_disconnect_with_position: bool = True
    # P0-3: background broker/kernel position reconcile cadence (exchange-time
    # gated). <=0 disables. Drift -> block_new_entry + CRITICAL alert.
    position_reconcile_sec: int = 60
    # P0-4: hard position ceiling (Pilot = 1). Entry rejected when held/pending
    # qty would reach this. Guards against runaway accumulation on report loss.
    max_position_qty: int = 1
    # P0-5 (truth-driven execution): after pending_timeout_sec the kernel stops
    # trusting the (possibly delayed) callback and treats the order as UNKNOWN,
    # actively reconciling against the broker position. ``settle_timeout_sec``
    # bounds how long SETTLING waits before HALT for exit/unreadable-broker paths.
    # Entry miss uses entry_miss_confirm_sec (clean resume) instead of sticky HALT.
    # order is unresolved (pending/settling/unconfirmed); ``reconcile_confirm_reads``
    # debounces consecutive identical broker reads before adopting them as truth.
    settle_timeout_sec: int = 45
    reconcile_fast_sec: int = 1
    reconcile_confirm_reads: int = 3
    # P0-5: emergency market orders. When True (default), a missed STOP-LOSS IOC and
    # the HALT convergence flatten escalate to a guaranteed-fill market order instead
    # of chasing with limit IOCs. Bounds time-to-flat in fast/illiquid markets at the
    # cost of slippage. Set False to keep the legacy limit-IOC-only behavior.
    emergency_market_orders: bool = True
    # P0-5: stable readable-flat duration before an entry IOC is declared MISSED
    # (clean resume, no sticky HALT). Must exceed max live fill-report latency
    # (live IOC is ms-level; 5s is conservative). Sim may mis-infer and trigger
    # the ceiling/convergence backstop — that is intentional for UAT==live.
    entry_miss_confirm_sec: int = 5
    # Consecutive entry misses before HALT+CRITICAL (structural failure, e.g.
    # orders not reaching the exchange). 0 = disable circuit breaker.
    max_consecutive_missed_entries: int = 3
    # Layer 2: IOC terminal-state query via update_status(trade) on the order
    # worker (borrow-safe). Default OFF; inference path remains fallback.
    order_status_query_enabled: bool = False
    # Bounded timeout (ms) passed to update_status; Shioaji default is 30s which
    # would stall the shared order-worker thread.
    order_status_query_timeout_ms: int = 1000

    config_path: Path = Path("")


__all__ = ["Settings"]
