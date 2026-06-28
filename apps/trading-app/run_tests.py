#!/usr/bin/env python3
"""Run unit tests with ``src/`` and ``tests/`` on sys.path.

Supports the mirrored layout under tests/ (backtest/, runtime/, storage/ etc.)
while preserving cross-test imports such as ``from tests.test_helpers import ...``.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_SRC = _ROOT / "src"
_MONOREPO = _ROOT.parent.parent
_SIBLING_PACKAGES = (
    _MONOREPO / "packages/trading-engine",
    _MONOREPO / "packages/trading-backtest",
    _MONOREPO / "packages/strategies/vwap-momentum",
    _MONOREPO / "packages/strategies/momentum-continuation",
    _MONOREPO / "packages/strategies/vwap-stretch-fade",
)


def _ensure_packages() -> None:
    """Prefer installed packages; else editable install sibling packages."""
    try:
        import trading_engine  # noqa: F401
        import strategy_vwap_momentum  # noqa: F401
        import strategy_momentum_continuation  # noqa: F401
        import strategy_vwap_stretch_fade  # noqa: F401
        import trading_backtest  # noqa: F401
        return
    except ImportError:
        pass

    for candidate in _SIBLING_PACKAGES:
        if (candidate / "pyproject.toml").is_file():
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "-e", str(candidate), "-q"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except subprocess.CalledProcessError:
                src = candidate / "src"
                if src.is_dir():
                    sys.path.insert(0, str(src))

    for candidate in _SIBLING_PACKAGES:
        src = candidate / "src"
        if src.is_dir() and str(src) not in sys.path:
            sys.path.insert(0, str(src))


_ensure_packages()

if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

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