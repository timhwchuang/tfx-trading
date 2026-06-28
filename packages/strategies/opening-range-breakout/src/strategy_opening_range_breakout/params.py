"""Strategy parameters for opening-range-breakout plugin."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from trading_engine.core.runtime_config import RuntimeConfig


@dataclass
class OrbParams:
    """Runtime strategy constants bound to a RuntimeConfig instance."""

    _cfg: RuntimeConfig

    def _live(self, const: str, snake: str, default: Any = None) -> Any:
        val = self._cfg.live_get(const, default)
        if val is not None:
            return val
        return getattr(self._cfg, snake, default)

    @property
    def range_minutes(self) -> int:
        return int(self._live("RANGE_MINUTES", "range_minutes", 30))

    @property
    def buffer_atr_k(self) -> float:
        return float(self._live("BUFFER_ATR_K", "buffer_atr_k", 0.15))

    @property
    def orb_min_range_atr_k(self) -> float:
        return float(self._live("ORB_MIN_RANGE_ATR_K", "orb_min_range_atr_k", 0.5))

    @property
    def orb_max_hold_sec(self) -> int:
        return int(self._live("ORB_MAX_HOLD_SEC", "orb_max_hold_sec", 180))

    @property
    def min_atr_threshold(self) -> float:
        return float(self._live("MIN_ATR_THRESHOLD", "min_atr_threshold", 25.0))

    @property
    def atr_period(self) -> int:
        return int(self._live("ATR_PERIOD", "atr_period", 20))

    @property
    def max_consecutive_loss(self) -> int:
        return int(self._live("MAX_CONSECUTIVE_LOSS", "max_consecutive_loss", 4))

    @property
    def exit_grace_ticks(self) -> int:
        return int(self._live("EXIT_GRACE_TICKS", "exit_grace_ticks", 10))

    @property
    def exit_grace_sec(self) -> int:
        return int(self._live("EXIT_GRACE_SEC", "exit_grace_sec", 10))

    @property
    def hard_stop_atr_k(self) -> float:
        return float(self._live("HARD_STOP_ATR_K", "hard_stop_atr_k", 0.75))

    @property
    def tp_atr_k(self) -> float:
        return float(self._live("TP_ATR_K", "tp_atr_k", 2.0))

    @property
    def trail_atr_k(self) -> float:
        return float(self._live("TRAIL_ATR_K", "trail_atr_k", 0.6))

    @property
    def trail_points_floor(self) -> float:
        return float(self._live("TRAIL_POINTS_FLOOR", "trail_points_floor", 6.0))

    @property
    def atr_trailing_enabled(self) -> bool:
        return bool(self._live("ATR_TRAILING_ENABLED", "atr_trailing_enabled", False))

    @property
    def flatten_slippage_points(self) -> int:
        return int(self._live("FLATTEN_SLIPPAGE_POINTS", "flatten_slippage_points", 8))

    @property
    def session_start(self):
        return self._cfg.session_start

    @property
    def session_end(self):
        return self._cfg.session_end

    @classmethod
    def from_runtime_config(cls, cfg: RuntimeConfig) -> OrbParams:
        return cls(_cfg=cfg)
