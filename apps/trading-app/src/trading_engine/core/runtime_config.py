"""Runtime configuration injected into TradingEngine."""

from __future__ import annotations

import os
from typing import Any

from trading_engine.settings import Settings

RuntimeConfigBase = Settings
_MISSING = object()

# Host-owned risk/ops fields that may be overlaid in tests.
SWEEP_FIELD_TO_CONST: dict[str, str] = {
    "max_consecutive_loss": "MAX_CONSECUTIVE_LOSS",
    "max_mdd_points": "MAX_MDD_POINTS",
    "ioc_slippage_points": "IOC_SLIPPAGE_POINTS",
    "pending_timeout_sec": "PENDING_TIMEOUT_SEC",
    "flatten_slippage_points": "FLATTEN_SLIPPAGE_POINTS",
    "cooldown_sec": "COOLDOWN_SEC",
    "max_daily_loss_points": "MAX_DAILY_LOSS_POINTS",
}

_CONST_TO_SNAKE = {
    "MAX_CONSECUTIVE_LOSS": "max_consecutive_loss",
    "MAX_MDD_POINTS": "max_mdd_points",
    "IOC_SLIPPAGE_POINTS": "ioc_slippage_points",
    "PENDING_TIMEOUT_SEC": "pending_timeout_sec",
    "FLATTEN_SLIPPAGE_POINTS": "flatten_slippage_points",
    "COOLDOWN_SEC": "cooldown_sec",
    "MAX_DAILY_LOSS_POINTS": "max_daily_loss_points",
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
        return saved

    def restore_overlay(self, saved: dict[str, Any]) -> None:
        for key, old in saved.items():
            if old is _MISSING:
                self._overlay.pop(key, None)
            else:
                self._overlay[key] = old

    def config_snapshot_fields(self) -> dict[str, Any]:
        """Host risk/ops fields for DAILY_SUMMARY embedding."""
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
