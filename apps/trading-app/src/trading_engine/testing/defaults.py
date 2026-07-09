"""Default Settings matching reference config.yaml (for unit tests)."""

from __future__ import annotations

import datetime
from pathlib import Path

from trading_engine.core.runtime_config import RuntimeConfig
from trading_engine.settings import Settings


def default_test_settings() -> Settings:
    return Settings(
        simulation=True,
        product_code="TMFR1",
        cooldown_sec=10,
        max_daily_loss_points=120,
        max_consecutive_loss=4,
        pending_timeout_sec=1,
        ioc_slippage_points=3,
        no_tick_timeout_sec=45,
        no_tick_resubscribe_escalate_after=3,
        clock_skew_warn_sec=1.0,
        session_start=datetime.time(8, 45),
        session_end=datetime.time(13, 45),
        session_flatten_time=datetime.time(13, 40),
        session_force_flatten_time=datetime.time(13, 44),
        flatten_slippage_points=8,
        log_level="INFO",
        log_file="",
        exit_order_max_retries=3,
        exit_order_retry_delay_sec=1.0,
        session_watchdog_sec=30.0,
        session_relogin_max_attempts=5,
        session_relogin_backoff_base_sec=5.0,
        reconnect_warmup_sec=300,
        max_disconnects_per_day=3,
        alert_on_disconnect_with_position=True,
        position_reconcile_sec=60,
        max_position_qty=1,
        settle_timeout_sec=45,
        reconcile_fast_sec=1,
        reconcile_confirm_reads=3,
        emergency_market_orders=True,
        entry_miss_confirm_sec=5,
        exit_miss_confirm_sec=5,
        post_exit_reconcile_sec=15,
        cleared_order_registry_sec=120,
        max_consecutive_missed_entries=3,
        config_path=Path("config/config.yaml"),
    )


def default_runtime_config() -> RuntimeConfig:
    return RuntimeConfig(default_test_settings())


__all__ = ["default_runtime_config", "default_test_settings"]
