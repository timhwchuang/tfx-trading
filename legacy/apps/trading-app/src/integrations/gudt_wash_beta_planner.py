"""Build wash-beta replay plans from wash probe contexts."""

from __future__ import annotations

from typing import Any

from reporting.gudt_wash_probe import DayWashContext
from strategy_gudt_route_a.types import DayReplayPlan
from strategy_gudt_route_a.wash_beta import (
    WashBetaParams,
    build_wash_beta_replay_plan,
    simulate_wash_beta_day,
)


def build_wash_beta_plans_for_range(
    rows: list[dict[str, Any]],
    ctx_by_day: dict[str, DayWashContext],
    *,
    params: WashBetaParams | None = None,
) -> dict[str, DayReplayPlan]:
    """One plan per wash-ctx day; skip when sim unavailable."""
    del rows
    params = params or WashBetaParams()
    plans: dict[str, DayReplayPlan] = {}
    for day in sorted(ctx_by_day):
        ctx = ctx_by_day[day]
        sim = simulate_wash_beta_day(ctx, params=params)
        if sim is None:
            plans[day] = DayReplayPlan(day=day, path="skip", skipped=True)
            continue
        plans[day] = build_wash_beta_replay_plan(day, sim)
    return plans


__all__ = ["build_wash_beta_plans_for_range"]
