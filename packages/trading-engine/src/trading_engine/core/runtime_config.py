"""Runtime configuration injected into TradingEngine."""

from __future__ import annotations

import os
from typing import Any

from trading_engine.settings import Settings

RuntimeConfigBase = Settings
_MISSING = object()

SWEEP_FIELD_TO_CONST: dict[str, str] = {
    "entry_band_points": "ENTRY_BAND_POINTS",
    "vwap_stop_points": "VWAP_STOP_POINTS",
    "exhaustion_vol": "EXHAUSTION_VOL",
    "exit_grace_ticks": "EXIT_GRACE_TICKS",
    "exit_grace_sec": "EXIT_GRACE_SEC",
    "fixed_tp_points": "FIXED_TP_POINTS",
    "trail_points": "TRAIL_POINTS",
    "hard_stop_points": "HARD_STOP_POINTS",
    "momentum_timeout_sec": "MOMENTUM_TIMEOUT_SEC",
    "momentum_buy_ratio": "MOMENTUM_BUY_RATIO",
    "momentum_sell_ratio": "MOMENTUM_SELL_RATIO",
    "momentum_vol_1s": "MOMENTUM_VOL_1S",
    "min_atr_threshold": "MIN_ATR_THRESHOLD",
    "max_consecutive_loss": "MAX_CONSECUTIVE_LOSS",
    "ioc_slippage_points": "IOC_SLIPPAGE_POINTS",
    "pending_timeout_sec": "PENDING_TIMEOUT_SEC",
    "flatten_slippage_points": "FLATTEN_SLIPPAGE_POINTS",
    "atr_trailing_enabled": "ATR_TRAILING_ENABLED",
    "atr_vwap_stop_enabled": "ATR_VWAP_STOP_ENABLED",
    "trail_points_floor": "TRAIL_POINTS_FLOOR",
    "trail_atr_k": "TRAIL_ATR_K",
    "vwap_stop_points_floor": "VWAP_STOP_POINTS_FLOOR",
    "vwap_stop_atr_k": "VWAP_STOP_ATR_K",
    "trend_filter_enabled": "TREND_FILTER_ENABLED",
    "trend_min_strength": "TREND_MIN_STRENGTH",
    "trend_timeframe_min": "TREND_TIMEFRAME_MIN",
    "trend_mode": "TREND_MODE",
    "trend_ema_period": "TREND_EMA_PERIOD",
    "trend_slope_min": "TREND_SLOPE_MIN",
    "structure_filter_enabled": "STRUCTURE_FILTER_ENABLED",
    "structure_timeframe_min": "STRUCTURE_TIMEFRAME_MIN",
    "structure_swing_lookback": "STRUCTURE_SWING_LOOKBACK",
    "structure_min_strength": "STRUCTURE_MIN_STRENGTH",
    "hard_stop_atr_k": "HARD_STOP_ATR_K",
    "tp_atr_k": "TP_ATR_K",
    "max_adverse_atr_k": "MAX_ADVERSE_ATR_K",
    "stretch_k": "STRETCH_K",
    "reset_z": "RESET_Z",
    "range_minutes": "RANGE_MINUTES",
    "buffer_atr_k": "BUFFER_ATR_K",
    "orb_min_range_atr_k": "ORB_MIN_RANGE_ATR_K",
    "orb_max_hold_sec": "ORB_MAX_HOLD_SEC",
}

_CONST_TO_SNAKE = {
    "ENTRY_BAND_POINTS": "entry_band_points",
    "VWAP_STOP_POINTS": "vwap_stop_points",
    "EXHAUSTION_VOL": "exhaustion_vol",
    "EXIT_GRACE_TICKS": "exit_grace_ticks",
    "FIXED_TP_POINTS": "fixed_tp_points",
    "TRAIL_POINTS": "trail_points",
    "HARD_STOP_POINTS": "hard_stop_points",
    "TREND_FILTER_ENABLED": "trend_filter_enabled",
    "TREND_MIN_STRENGTH": "trend_min_strength",
    "TREND_TIMEFRAME_MIN": "trend_timeframe_min",
    "TREND_MODE": "trend_mode",
    "TREND_EMA_PERIOD": "trend_ema_period",
    "TREND_SLOPE_MIN": "trend_slope_min",
    "STRUCTURE_FILTER_ENABLED": "structure_filter_enabled",
    "STRUCTURE_TIMEFRAME_MIN": "structure_timeframe_min",
    "STRUCTURE_SWING_LOOKBACK": "structure_swing_lookback",
    "STRUCTURE_MIN_STRENGTH": "structure_min_strength",
    "MOMENTUM_BUY_RATIO": "momentum_buy_ratio",
    "MOMENTUM_SELL_RATIO": "momentum_sell_ratio",
    "MOMENTUM_TIMEOUT_SEC": "momentum_timeout_sec",
    "MIN_ATR_THRESHOLD": "min_atr_threshold",
    "MAX_CONSECUTIVE_LOSS": "max_consecutive_loss",
    "ATR_TRAILING_ENABLED": "atr_trailing_enabled",
    "ATR_VWAP_STOP_ENABLED": "atr_vwap_stop_enabled",
    "TRAIL_POINTS_FLOOR": "trail_points_floor",
    "TRAIL_ATR_K": "trail_atr_k",
    "VWAP_STOP_POINTS_FLOOR": "vwap_stop_points_floor",
    "VWAP_STOP_ATR_K": "vwap_stop_atr_k",
    "FLATTEN_SLIPPAGE_POINTS": "flatten_slippage_points",
    "EXIT_GRACE_SEC": "exit_grace_sec",
    "IOC_SLIPPAGE_POINTS": "ioc_slippage_points",
    "PENDING_TIMEOUT_SEC": "pending_timeout_sec",
    "MOMENTUM_VOL_1S": "momentum_vol_1s",
    "HARD_STOP_ATR_K": "hard_stop_atr_k",
    "TP_ATR_K": "tp_atr_k",
    "MAX_ADVERSE_ATR_K": "max_adverse_atr_k",
    "STRETCH_K": "stretch_k",
    "RESET_Z": "reset_z",
    "RANGE_MINUTES": "range_minutes",
    "BUFFER_ATR_K": "buffer_atr_k",
    "ORB_MIN_RANGE_ATR_K": "orb_min_range_atr_k",
    "ORB_MAX_HOLD_SEC": "orb_max_hold_sec",
}


def normalize_overlay_key(key: str) -> str:
    return SWEEP_FIELD_TO_CONST.get(key, key)


def _snake_for_const(name: str) -> str:
    return _CONST_TO_SNAKE.get(name, name.lower())


def _overlay_key_valid(cfg: "RuntimeConfig", real_key: str) -> bool:
    if real_key in _CONST_TO_SNAKE:
        return True
    if real_key in SWEEP_FIELD_TO_CONST:
        return True
    snake = _snake_for_const(real_key)
    if hasattr(cfg._base, snake):
        return True
    if hasattr(cfg._base, real_key):
        return True
    return False


class RuntimeConfig:
    """Frozen Settings + per-instance sweep overlay (no module-level patch)."""

    def __init__(
        self,
        base: Settings,
        overlay: dict[str, Any] | None = None,
    ) -> None:
        self._base = base
        self._overlay: dict[str, Any] = dict(overlay or {})

    def live_get(self, name: str, default: Any = None) -> Any:
        if name in self._overlay:
            return self._overlay[name]
        snake = _snake_for_const(name)
        if hasattr(self._base, snake):
            return getattr(self._base, snake)
        return default

    def apply_overlay(self, params: dict[str, Any]) -> dict[str, Any]:
        saved: dict[str, Any] = {}
        for key, value in params.items():
            real_key = normalize_overlay_key(key)
            if not _overlay_key_valid(self, real_key):
                raise ValueError(
                    f"unknown overlay key {key!r} (normalized {real_key!r}); "
                    "not in SWEEP_FIELD_TO_CONST and not a Settings field"
                )
            saved[real_key] = self._overlay.get(real_key, _MISSING)
            self._overlay[real_key] = value
        self._validate_regime_mutual_exclusion()
        return saved

    def _validate_regime_mutual_exclusion(self) -> None:
        structure_on = bool(
            self.live_get("STRUCTURE_FILTER_ENABLED", self.structure_filter_enabled)
        )
        trend_on = bool(self.live_get("TREND_FILTER_ENABLED", self.trend_filter_enabled))
        if structure_on and trend_on:
            raise ValueError(
                "structure_filter_enabled and trend_filter_enabled are mutually exclusive"
            )

    def restore_overlay(self, saved: dict[str, Any]) -> None:
        for key, old in saved.items():
            if old is _MISSING:
                self._overlay.pop(key, None)
            else:
                self._overlay[key] = old

    def config_snapshot_fields(self) -> dict[str, Any]:
        """Sweepable strategy fields for DAILY_SUMMARY embedding."""
        out: dict[str, Any] = {}
        for field, const in SWEEP_FIELD_TO_CONST.items():
            out[field] = self.live_get(const, getattr(self._base, field, None))
        return out

    @property
    def api_key(self) -> str:
        return os.environ.get("SJ_API_KEY", "YOUR_API_KEY")

    @property
    def secret_key(self) -> str:
        return os.environ.get("SJ_SEC_KEY", "YOUR_SECRET_KEY")

    @property
    def ca_path(self) -> str:
        return os.environ.get("SJ_CA_PATH", "")

    @property
    def ca_passwd(self) -> str:
        return os.environ.get("SJ_CA_PASSWD", "")

    def warn_if_placeholder_credentials(self, *, simulation: bool) -> None:
        """Warn when live credentials were not configured via environment."""
        if simulation:
            return
        import logging

        log = logging.getLogger("trading_engine")
        if self.api_key == "YOUR_API_KEY" or self.secret_key == "YOUR_SECRET_KEY":
            log.warning("SJ_API_KEY / SJ_SEC_KEY 仍為預設值；請設定 .env 或環境變數後再登入")

    @property
    def dump_order_events(self) -> bool:
        return False

    @property
    def tick_archive(self) -> bool:
        return False

    @property
    def kbars_archive(self) -> bool:
        return False

    def __getattr__(self, name: str) -> Any:
        if name in ("_base", "_overlay"):
            raise AttributeError(name)
        overlay_key = normalize_overlay_key(name)
        if overlay_key in self._overlay:
            return self._overlay[overlay_key]
        if name in self._overlay:
            return self._overlay[name]
        return getattr(self._base, name)


__all__ = [
    "RuntimeConfig",
    "RuntimeConfigBase",
    "SWEEP_FIELD_TO_CONST",
    "normalize_overlay_key",
]
