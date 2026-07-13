from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    simulation: bool
    api_key: str
    secret_key: str
    kbars_path: Path


__all__ = [
    "Config",
]
