"""StructureRefreshPort adapter wrapping strategy_vwap_momentum.structure."""

from __future__ import annotations

import datetime
from typing import Any, Optional

from core.runtime_config import RuntimeConfig
from storage.kbar_loader import KBarRecord, _kbars_raw_to_records
from strategy_vwap_momentum.structure import StructureParams, StructureState, compute_structure


class TradingAppStructureRefresh:
    def refresh_structure(
        self,
        kbars: Any,
        *,
        exchange_dt: Optional[datetime.datetime],
        used_long_lookback: bool,
        atr: float,
        cfg: RuntimeConfig,
    ) -> StructureState:
        bars: list[KBarRecord]
        if isinstance(kbars, list) and kbars and isinstance(kbars[0], KBarRecord):
            bars = list(kbars)
        else:
            bars = _kbars_raw_to_records(kbars)

        params = StructureParams(
            structure_filter_enabled=True,
            trend_filter_enabled=False,
            structure_timeframe_min=int(
                cfg.live_get("STRUCTURE_TIMEFRAME_MIN", cfg.structure_timeframe_min)
            ),
            structure_swing_lookback=int(
                cfg.live_get("STRUCTURE_SWING_LOOKBACK", cfg.structure_swing_lookback)
            ),
            structure_min_strength=float(
                cfg.live_get("STRUCTURE_MIN_STRENGTH", cfg.structure_min_strength)
            ),
        )
        anchor = exchange_dt or datetime.datetime.now()
        return compute_structure(
            bars,
            atr=atr,
            params=params,
            exchange_dt=anchor,
            used_long_lookback=used_long_lookback,
        )


__all__ = ["TradingAppStructureRefresh"]