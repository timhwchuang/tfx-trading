"""Strategy parameters for gudt-route-a plugin."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from trading_engine.core.runtime_config import RuntimeConfig


@dataclass
class GudtRouteAParams:
    """Runtime strategy constants bound to a RuntimeConfig instance."""

    _cfg: RuntimeConfig

    def _live(self, const: str, snake: str, default: Any = None) -> Any:
        val = self._cfg.live_get(const, default)
        if val is not None:
            return val
        return getattr(self._cfg, snake, default)

    @property
    def pre_break_br_min(self) -> float:
        return float(self._live("GUDT_PRE_BREAK_BR_MIN", "gudt_pre_break_br_min", 0.35))

    @property
    def flip_min_ext_open(self) -> float:
        return float(self._live("GUDT_FLIP_MIN_EXT_OPEN", "gudt_flip_min_ext_open", 5.0))

    @property
    def p0_ext_open_max(self) -> float | None:
        val = self._live("GUDT_P0_EXT_OPEN_MAX", "gudt_p0_ext_open_max", None)
        return None if val is None else float(val)

    @property
    def extension_exit(self) -> str:
        return str(self._live("GUDT_EXTENSION_EXIT", "gudt_extension_exit", "ema5"))

    @property
    def confirm_min_dump_atr(self) -> float:
        return float(self._live("GUDT_CONFIRM_MIN_DUMP_ATR", "gudt_confirm_min_dump_atr", 0.65))

    @property
    def confirm_slope2_min(self) -> float:
        return float(self._live("GUDT_CONFIRM_SLOPE2_MIN", "gudt_confirm_slope2_min", -0.35))

    @property
    def confirm_slope2_max(self) -> float:
        return float(self._live("GUDT_CONFIRM_SLOPE2_MAX", "gudt_confirm_slope2_max", 0.0))

    @property
    def friction_points(self) -> float:
        return float(self._live("GUDT_FRICTION_POINTS", "gudt_friction_points", 5.0))

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
    def from_runtime_config(cls, cfg: RuntimeConfig) -> GudtRouteAParams:
        return cls(_cfg=cfg)
