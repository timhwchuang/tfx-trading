from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

FillMode = Literal["optimistic", "conservative"]

_DEFAULT_FILL_MODE: FillMode = "conservative"
_ALLOWED_FILL_MODES: frozenset[str] = frozenset({"optimistic", "conservative"})
_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "config.yaml"


@dataclass(frozen=True)
class BacktestConfig:
    fill_mode: FillMode


def load_backtest_config(path: Path | None = None) -> BacktestConfig:
    config_path = path if path is not None else _DEFAULT_CONFIG_PATH
    if not config_path.is_file():
        raise FileNotFoundError(f"找不到設定檔: {config_path}")
    with config_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    section = raw.get("trading") or {}
    fill_mode = section.get("fill_mode", _DEFAULT_FILL_MODE)
    if fill_mode not in _ALLOWED_FILL_MODES:
        raise ValueError(f"invalid fill_mode: {fill_mode!r}")
    return BacktestConfig(fill_mode=fill_mode)


__all__ = [
    "BacktestConfig",
    "FillMode",
    "load_backtest_config",
]
