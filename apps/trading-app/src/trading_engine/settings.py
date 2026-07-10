"""Settings dataclass — host app loads YAML/env and passes to RuntimeConfig."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    simulation: bool
    product_code: str

    cooldown_sec: int
    max_daily_loss_points: int
    # DEPRECATED as capital gate (Host ignores); YAML/compat only.
    max_consecutive_loss: int
    pending_timeout_sec: int
    ioc_slippage_points: int
    no_tick_timeout_sec: int
    no_tick_resubscribe_escalate_after: int
    clock_skew_warn_sec: float

    session_start: datetime.time
    session_end: datetime.time
    session_flatten_time: datetime.time
    session_force_flatten_time: datetime.time
    flatten_slippage_points: int

    log_level: str
    log_file: str

    exit_order_max_retries: int
    exit_order_retry_delay_sec: float
    session_watchdog_sec: float
    session_relogin_max_attempts: int
    session_relogin_backoff_base_sec: float
    # Progressive realized MDD freeze. <=0 disables (UAT). Not day-scoped.
    max_mdd_points: float = 0.0
    # JSON path for durable capital book across restarts. Empty = disabled (tests).
    capital_state_path: str = ""
    # Optional overnight session (15:00–05:00). Disabled when night_enabled=False.
    night_enabled: bool = False
    night_session_start: datetime.time = datetime.time(15, 0)
    night_session_end: datetime.time = datetime.time(5, 0)
    night_session_flatten_time: datetime.time = datetime.time(4, 50)
    night_session_force_flatten_time: datetime.time = datetime.time(4, 55)
    simple_entry_delay_sec: int = 60
    simple_flip_interval_sec: int = 300
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
    # Exit IOC: stable unchanged broker position duration before declaring MISSED
    # (never infer-clear on a single L3 read — prevents double-exit over-flatten).
    exit_miss_confirm_sec: int = 5
    # After a full exit fill, poll broker at reconcile_fast_sec for this many seconds.
    post_exit_reconcile_sec: int = 15
    # TTL for recently cleared pending order_ids (late deal attribution / HALT).
    cleared_order_registry_sec: int = 120
    # Consecutive entry misses before HALT+CRITICAL (structural failure, e.g.
    # orders not reaching the exchange). 0 = disable circuit breaker.
    max_consecutive_missed_entries: int = 3

    # Strategy plugin name (refresh default: simple)
    strategy_name: str = "simple"

    config_path: Path = Path("")


__all__ = ["Settings"]
