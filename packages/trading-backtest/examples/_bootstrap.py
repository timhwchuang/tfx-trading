"""Allow running examples from a fresh clone before pip install -e."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
_SIBLING_ENGINE = _ROOT.parent / "trading-engine" / "src"

for path in (_SRC, _SIBLING_ENGINE):
    if path.is_dir() and str(path) not in sys.path:
        sys.path.insert(0, str(path))