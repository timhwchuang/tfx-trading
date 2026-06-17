#!/usr/bin/env python3
"""Run trading-backtest unit tests."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_SRC = _ROOT / "src"
_SIBLING = _ROOT.parent / "trading-engine"


def _ensure_packages() -> None:
    for candidate in (_SIBLING, _ROOT):
        if (candidate / "pyproject.toml").is_file():
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "-e", str(candidate), "-q"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except subprocess.CalledProcessError:
                src = candidate / "src"
                if src.is_dir() and str(src) not in sys.path:
                    sys.path.insert(0, str(src))
    try:
        import trading_backtest  # noqa: F401
        import trading_engine  # noqa: F401
    except ImportError:
        for src in (_SIBLING / "src", _SRC):
            if src.is_dir() and str(src) not in sys.path:
                sys.path.insert(0, str(src))


_ensure_packages()

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

if __name__ == "__main__":
    raise SystemExit(
        unittest.main(
            module=None,
            argv=["", "discover", "-s", str(_ROOT / "tests"), "-t", str(_ROOT), "-v"],
            exit=True,
        )
    )
