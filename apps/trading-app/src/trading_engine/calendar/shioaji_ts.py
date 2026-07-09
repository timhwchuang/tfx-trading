"""Shioaji historical tick/kbar timestamp decode (single source of truth).

Official docs cast ``ts`` with ``pl.col("ts").cast(pl.Datetime("ns"))``, yielding
exchange wall-clock naive datetimes. See ``trading-engine/SPEC.md`` § Shioaji Time Contract.
"""

from __future__ import annotations

import datetime

UTC = datetime.timezone.utc


def shioaji_historical_ts_from_ns(ts_ns: int) -> datetime.datetime:
    """Convert Shioaji historical ``api.ticks`` / ``api.kbars`` ``ts`` to exchange wall clock.

    Matches Shioaji official polars cast: ns integer → naive exchange session time.
    Simulation and production use the same encoding (verified 2026-06-25 TXFR1).
    """
    return datetime.datetime.fromtimestamp(ts_ns / 1_000_000_000, UTC).replace(
        tzinfo=None
    )


__all__ = ["shioaji_historical_ts_from_ns"]
