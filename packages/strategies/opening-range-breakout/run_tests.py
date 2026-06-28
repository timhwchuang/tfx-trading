#!/usr/bin/env python3
"""Run opening-range-breakout package tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root / "src"))
    suite = unittest.defaultTestLoader.discover(str(root / "tests"))
    raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
