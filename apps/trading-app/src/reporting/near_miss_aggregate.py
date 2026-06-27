"""Aggregate per-day near_miss counters into a multi-day funnel."""

from __future__ import annotations

from typing import Any

_SUM_KEYS = (
    "momentum_episodes",
    "momentum_timeout",
    "blocked_vwap_only",
    "blocked_vol_only",
    "blocked_both",
)


def aggregate_near_miss(daily_summaries: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Sum additive near_miss fields across days; closest_vwap_distance = min."""
    if not daily_summaries:
        return None

    out: dict[str, Any] = {k: 0 for k in _SUM_KEYS}
    closest: float | None = None
    days_with_nm = 0

    for day in daily_summaries:
        nm = day.get("near_miss")
        if not nm:
            continue
        days_with_nm += 1
        for key in _SUM_KEYS:
            out[key] += int(nm.get(key) or 0)
        c = nm.get("closest_vwap_distance")
        if c is not None:
            cv = float(c)
            closest = cv if closest is None else min(closest, cv)

    if days_with_nm == 0:
        return None

    out["closest_vwap_distance"] = closest
    out["_aggregated_from_days"] = days_with_nm
    return out
