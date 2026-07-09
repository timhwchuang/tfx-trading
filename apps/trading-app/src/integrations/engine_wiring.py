"""TradingEngine port wiring for trading-app (live / tests).

Host receives a Strategy instance from the caller; this module only wires
side-effect ports (alerts, archive, telemetry, adapters).
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from storage.cache_paths import DEFAULT_TICK_CACHE_DIR
from storage.live_session_bars import LiveSessionBars

from config import LOG_FILE, LOG_LEVEL
from core.runtime_config import RuntimeConfig, default_runtime_config
from integrations.alerts_port import TradingAppAlertPort
from integrations.archive_port import TradingAppArchivePort
from integrations.telemetry_port import TradingAppTelemetryPort
from observability import DailyObservability
from strategy_simple import SimpleParams, SimpleStrategy
from trading_engine.adapters.mock import MockOrderAdapter
from trading_engine.adapters.shioaji import ShioajiOrderAdapter
from trading_engine.logging_setup import setup_async_logging

_logging_configured = False

logger = logging.getLogger(__name__)


def _ensure_logging() -> None:
    global _logging_configured
    if not _logging_configured:
        setup_async_logging(level=LOG_LEVEL, log_file=LOG_FILE)
        _logging_configured = True


def order_adapter_for(api: Any, *, use_mock: bool) -> Any:
    """Explicit adapter selection at the wiring layer (no api heuristics)."""
    if use_mock:
        return MockOrderAdapter(api)
    return ShioajiOrderAdapter(api)


def default_strategy(
    cfg: RuntimeConfig,
    obs: DailyObservability,
) -> SimpleStrategy:
    """Test / helper constructor for the in-tree simple strategy."""
    return SimpleStrategy(
        params=SimpleParams.from_runtime_config(cfg),
        obs=obs,
    )


def trading_app_engine_ports(
    *,
    api: Any,
    use_mock_adapter: bool,
    runtime_config: RuntimeConfig | None = None,
    with_alerts: bool = False,
    with_archive: bool = False,
    obs: DailyObservability | None = None,
) -> dict:
    """Return kwargs for ``TradingEngine(api=api, **trading_app_engine_ports(...))``."""
    _ensure_logging()
    cfg = runtime_config or default_runtime_config()
    shared_obs = obs if obs is not None else DailyObservability()
    ports: dict = {
        "runtime_config": cfg,
        "order_adapter": order_adapter_for(api, use_mock=use_mock_adapter),
        "telemetry": TradingAppTelemetryPort(obs=shared_obs, runtime_config=cfg),
        "obs": shared_obs,
    }
    if with_alerts:
        ports["alerts"] = TradingAppAlertPort()
    if with_archive:
        live_bars: LiveSessionBars | None = None
        if cfg.live_bars:
            code = cfg.product_code
            try:
                live_bars = LiveSessionBars.start(
                    code,
                    datetime.datetime.now(),
                    cache_dir=DEFAULT_TICK_CACHE_DIR,
                    persist_kbars=cfg.live_kbar_persist,
                )
            except Exception as exc:
                logger.warning("LiveSessionBars disabled: %s", exc)
        archive = TradingAppArchivePort(live_bars=live_bars)
        ports["archive"] = archive
        if live_bars is not None:
            ports["live_bars"] = live_bars
    return ports


__all__ = [
    "default_strategy",
    "order_adapter_for",
    "trading_app_engine_ports",
]
