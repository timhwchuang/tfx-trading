"""Default TradingEngine port wiring for trading-app (live / backtest / tests)."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, Literal

from config import LOG_FILE, LOG_LEVEL
from core.runtime_config import RuntimeConfig, default_runtime_config
from integrations.alerts_port import TradingAppAlertPort
from integrations.archive_port import TradingAppArchivePort
from integrations.strategy_bootstrap import resolve_strategy_bootstrap
from integrations.telemetry_port import TradingAppTelemetryPort
from integrations.structure_refresh import TradingAppStructureRefresh
from integrations.trend_refresh import TradingAppTrendRefresh
from observability import DailyObservability
from strategy_vwap_momentum import StrategyParams, VWAPMomentumStrategy
from strategy_momentum_continuation import ContinuationParams, MomentumContinuationStrategy
from strategy_vwap_stretch_fade import StretchFadeParams, VwapStretchFadeStrategy
from strategy_opening_range_breakout import OrbParams, OpeningRangeBreakoutStrategy
from strategy_gudt_route_a import GudtRouteAParams, GudtRouteAStrategy, GudtWashBetaStrategy
from trading_engine.adapters.mock import MockOrderAdapter
from trading_engine.adapters.shioaji import ShioajiOrderAdapter
from trading_engine.logging_setup import setup_async_logging
from trading_engine.plugins import load_strategy

_logging_configured = False

KNOWN_STRATEGY_NAMES = frozenset(
    {
        "vwap_momentum",
        "momentum_continuation",
        "vwap_stretch_fade",
        "opening_range_breakout",
        "gudt_route_a",
        "gudt_wash_beta",
    }
)

SessionMode = Literal["backtest", "live"]


def validate_strategy_name(name: str) -> None:
    if name not in KNOWN_STRATEGY_NAMES:
        available = ", ".join(sorted(KNOWN_STRATEGY_NAMES))
        raise LookupError(f"Unknown strategy plugin {name!r}. Available: {available}")


def build_strategy_session(
    cfg: RuntimeConfig,
    obs: DailyObservability,
    *,
    code: str,
    dates: list[datetime.date],
    cache_dir: Path,
    mode: SessionMode = "backtest",
    probe_csv_override: Path | None = None,
    **extra_kwargs: Any,
) -> Any:
    name = getattr(cfg, "strategy_name", "vwap_momentum")
    validate_strategy_name(name)
    kwargs = resolve_strategy_bootstrap(
        name,
        cfg,
        code=code,
        dates=dates,
        cache_dir=cache_dir,
        mode=mode,
        obs=obs,
        probe_csv_override=probe_csv_override,
    )
    kwargs.update(extra_kwargs)
    return load_named_strategy(name, cfg, obs, **kwargs)


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
) -> VWAPMomentumStrategy:
    return VWAPMomentumStrategy(
        params=StrategyParams.from_runtime_config(cfg),
        obs=obs,
    )


def load_named_strategy(
    name: str,
    cfg: RuntimeConfig,
    obs: DailyObservability,
    **kwargs: Any,
) -> Any:
    """Load strategy via entry point; falls back to explicit default for vwap_momentum."""
    if name == "vwap_momentum":
        return default_strategy(cfg, obs)
    if name == "momentum_continuation":
        return MomentumContinuationStrategy(
            params=ContinuationParams.from_runtime_config(cfg),
            obs=obs,
        )
    if name == "vwap_stretch_fade":
        return VwapStretchFadeStrategy(
            params=StretchFadeParams.from_runtime_config(cfg),
            obs=obs,
        )
    if name == "opening_range_breakout":
        return OpeningRangeBreakoutStrategy(
            params=OrbParams.from_runtime_config(cfg),
            obs=obs,
        )
    if name == "gudt_route_a":
        return GudtRouteAStrategy(
            params=GudtRouteAParams.from_runtime_config(cfg),
            obs=obs,
            day_plans=kwargs.get("day_plans"),
        )
    if name == "gudt_wash_beta":
        return GudtWashBetaStrategy(
            params=GudtRouteAParams.from_runtime_config(cfg),
            obs=obs,
            day_plans=kwargs.get("day_plans"),
        )
    return load_strategy(
        name,
        params=StrategyParams.from_runtime_config(cfg),
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
    """Return kwargs for ``TradingEngine(api=api, **trading_app_engine_ports(api=...))``."""
    _ensure_logging()
    cfg = runtime_config or default_runtime_config()
    shared_obs = obs if obs is not None else DailyObservability()
    ports: dict = {
        "runtime_config": cfg,
        "order_adapter": order_adapter_for(api, use_mock=use_mock_adapter),
        "telemetry": TradingAppTelemetryPort(obs=shared_obs, runtime_config=cfg),
        "trend_refresh": TradingAppTrendRefresh(),
        "structure_refresh": TradingAppStructureRefresh(),
        "obs": shared_obs,
    }
    if with_alerts:
        ports["alerts"] = TradingAppAlertPort()
    if with_archive:
        ports["archive"] = TradingAppArchivePort()
    return ports


__all__ = [
    "KNOWN_STRATEGY_NAMES",
    "build_strategy_session",
    "default_strategy",
    "load_named_strategy",
    "order_adapter_for",
    "trading_app_engine_ports",
    "validate_strategy_name",
]