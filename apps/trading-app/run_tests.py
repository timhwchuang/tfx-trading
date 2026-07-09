#!/usr/bin/env python3
"""Run unit tests with ``src/`` and ``tests/`` on sys.path."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_SRC = _ROOT / "src"

if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.discover(str(_ROOT / "tests"), top_level_dir=str(_ROOT))
    ok = unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()
    raise SystemExit(not ok)
