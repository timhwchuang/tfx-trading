"""VWAP strategy test host factory."""

from __future__ import annotations

from typing import Any

from trading_engine.testing.defaults import default_runtime_config
from trading_engine.testing.helpers import make_host

from strategy_vwap_momentum import StrategyParams, VWAPMomentumStrategy


def make_vwap_host(*, api: Any | None = None, obs: Any | None = None):
    cfg = default_runtime_config()
    strategy = VWAPMomentumStrategy(
        params=StrategyParams.from_runtime_config(cfg),
        obs=obs,
    )
    return make_host(strategy, api=api)


__all__ = ["make_vwap_host"]
