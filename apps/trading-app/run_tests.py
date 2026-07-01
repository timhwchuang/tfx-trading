#!/usr/bin/env python3
"""Run unit tests with ``src/`` and ``tests/`` on sys.path.

Supports the mirrored layout under tests/ (backtest/, runtime/, storage/ etc.)
while preserving cross-test imports such as ``from tests.test_helpers import ...``.
"""

from __future__ import annotations

import os
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
    _MONOREPO / "packages/strategies/gudt-route-a",
    _MONOREPO / "packages/strategies/opening-range-breakout",
)


def _ensure_packages() -> None:
    """Prefer installed packages; else editable install sibling packages."""
    try:
        import trading_engine  # noqa: F401
        import strategy_vwap_momentum  # noqa: F401
        import strategy_momentum_continuation  # noqa: F401
        import strategy_vwap_stretch_fade  # noqa: F401
        import trading_backtest  # noqa: F401
        import strategy_gudt_route_a  # noqa: F401
        import strategy_opening_range_breakout  # noqa: F401
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


def _run_gudt_package_tests() -> bool:
    """Run gudt-route-a package tests in isolation (avoids ``tests`` name clash)."""
    gudt_root = _MONOREPO / "packages/strategies/gudt-route-a"
    if not (gudt_root / "tests").is_dir():
        return True
    engine_src = _MONOREPO / "packages/trading-engine/src"
    env = os.environ.copy()
    extra = [str(gudt_root / "src"), str(engine_src)]
    env["PYTHONPATH"] = os.pathsep.join(
        extra + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    )
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-p",
            "test_*.py",
            "-v",
        ],
        cwd=str(gudt_root),
        env=env,
    )
    return proc.returncode == 0


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.discover(str(_ROOT / "tests"), top_level_dir=str(_ROOT))
    ok = unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()
    if ok:
        ok = _run_gudt_package_tests()
    raise SystemExit(not ok)