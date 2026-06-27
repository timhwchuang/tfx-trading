"""Momentum continuation strategy plugin (FT-004)."""

from strategy_momentum_continuation._version import __version__
from strategy_momentum_continuation.atr_utils import dynamic_atr_distance
from strategy_momentum_continuation.params import ContinuationParams
from strategy_momentum_continuation.strategy import MomentumContinuationStrategy

__all__ = [
    "ContinuationParams",
    "MomentumContinuationStrategy",
    "dynamic_atr_distance",
    "__version__",
]
