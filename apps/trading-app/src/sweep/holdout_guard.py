"""FT-003: block holdout dates from sweep/backtest until human unseals."""

from __future__ import annotations

import datetime
import os
from collections.abc import Sequence

DEFAULT_SEALED_FROM = datetime.date(2026, 5, 1)
DEFAULT_SEALED_TO = datetime.date(2026, 5, 31)
_UNSEAL_ENV = "FT003_HOLDOUT_UNSEAL"


def holdout_unsealed() -> bool:
    return os.environ.get(_UNSEAL_ENV, "").strip() in ("1", "true", "yes")


def assert_dates_unsealed(
    dates: Sequence[datetime.date],
    *,
    sealed_from: datetime.date = DEFAULT_SEALED_FROM,
    sealed_to: datetime.date = DEFAULT_SEALED_TO,
) -> None:
    """Raise if any date falls in the sealed holdout window (unless unsealed)."""
    if holdout_unsealed():
        return
    blocked = [
        d for d in dates if sealed_from <= d <= sealed_to
    ]
    if blocked:
        sample = ", ".join(str(d) for d in blocked[:5])
        suffix = "..." if len(blocked) > 5 else ""
        raise RuntimeError(
            f"holdout dates sealed ({sealed_from}..{sealed_to}); "
            f"blocked {len(blocked)} date(s): {sample}{suffix}. "
            f"Set {_UNSEAL_ENV}=1 only for Phase 4 election."
        )


__all__ = [
    "DEFAULT_SEALED_FROM",
    "DEFAULT_SEALED_TO",
    "assert_dates_unsealed",
    "holdout_unsealed",
]
