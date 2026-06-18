"""VWAP momentum strategy plugin (reference implementation for trading-engine).

Version and public surface are re-exported here for convenience.
"""

from strategy_vwap_momentum._version import __version__
from strategy_vwap_momentum.params import (
    SWEEPABLE_PARAMS,
    StrategyParams,
    apply_strategy_params,
    patch_strategy_params,
    restore_strategy_params,
    sweepable_value,
)
from strategy_vwap_momentum.strategy import MomentumState, VWAPMomentumStrategy
from strategy_vwap_momentum.structure import (
    StructureParams,
    StructureState,
    compute_structure,
    regime_allows_entry,
    structure_allows_entry,
    validate_regime_config,
)
from strategy_vwap_momentum.trend import (
    compute_trend,
    dynamic_trail_points,
    dynamic_vwap_stop_distance,
    trend_allows_entry,
)

__all__ = [
    "MomentumState",
    "StructureParams",
    "StructureState",
    "SWEEPABLE_PARAMS",
    "StrategyParams",
    "VWAPMomentumStrategy",
    "apply_strategy_params",
    "compute_structure",
    "compute_trend",
    "dynamic_trail_points",
    "dynamic_vwap_stop_distance",
    "patch_strategy_params",
    "regime_allows_entry",
    "restore_strategy_params",
    "structure_allows_entry",
    "sweepable_value",
    "trend_allows_entry",
    "validate_regime_config",
    "__version__",
]

__version__ = __version__  # re-export at package level (consistent with trading-engine)
