"""Build GudtRouteAStrategy replay plans from counterfactual stack picks."""

from __future__ import annotations

from typing import Any

from reporting.gudt_wash_probe import (
    DayWashContext,
    _long_row_for_pick,
    _probe_entry_from_row,
    _row_for,
    _simulate_exit,
    distribution_confirm_pass,
    distribution_signal_at_p0,
    simulate_short_to_stop,
)
from strategy_gudt_route_a.replay import build_replay_plan
from strategy_gudt_route_a.route_a_exit import RouteAParams, simulate_route_a_exit
from strategy_gudt_route_a.stack import RouteAStackParams, apply_route_a_stack_day
from strategy_gudt_route_a.types import DayReplayPlan


def _long_row_for_pick_rows(day_rows: list[dict[str, Any]], pick: dict[str, Any]) -> dict[str, Any] | None:
    return _long_row_for_pick(day_rows, pick)


def _long_sim_for_pick(
    pick: dict[str, Any],
    day_rows: list[dict[str, Any]],
    ctx: DayWashContext,
    *,
    params: RouteAStackParams,
) -> dict[str, Any] | None:
    path = str(pick.get("path", ""))
    if path.startswith("p0"):
        row = _row_for(day_rows, "p0", "sealed")
        if row is None:
            return None
        entry = _probe_entry_from_row(row)
        return simulate_route_a_exit(entry, ctx, params=params.route_a)
    em = path.split("+")[0]
    ex = "drive_low_struct" if "drive_low" in path else "flow_bailout"
    row = _row_for(day_rows, em if em in ("flow_turn", "reclaim_br", "p0") else "flow_turn", ex)
    if row is None:
        row = _row_for(day_rows, "flow_turn", ex)
    if row is None:
        return None
    entry = _probe_entry_from_row(row)
    return _simulate_exit(entry, ctx, ex)


def build_replay_plans_for_range(
    rows: list[dict[str, Any]],
    ctx_by_day: dict[str, DayWashContext],
    *,
    params: RouteAStackParams | None = None,
) -> dict[str, DayReplayPlan]:
    """Build per-day replay plans aligned with ``summarize_route_a_stack`` picks."""
    params = params or RouteAStackParams()
    by_day: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_day.setdefault(r["day"], []).append(r)

    plans: dict[str, DayReplayPlan] = {}
    for day_rows in by_day.values():
        day = day_rows[0]["day"]
        ctx = ctx_by_day.get(day)
        if ctx is None:
            plans[day] = DayReplayPlan(day=day, path="skip", skipped=True)
            continue

        pick = apply_route_a_stack_day(day_rows, ctx, params=params)
        if pick is None:
            plans[day] = DayReplayPlan(day=day, path="skip", skipped=True)
            continue

        long_row = _long_row_for_pick_rows(day_rows, pick)
        long_sim = _long_sim_for_pick(pick, day_rows, ctx, params=params)
        flip_signal = None
        short_sim = None

        if pick.get("hedge") == "flip":
            p0 = _row_for(day_rows, "p0", "sealed")
            dist_params = params.br5.distribution
            if p0 is not None:
                flip_signal = distribution_signal_at_p0(p0, ctx, params=dist_params)
                if flip_signal is not None and pick.get("dist_confirm") == "pass":
                    confirm_ok, confirm_m = distribution_confirm_pass(
                        flip_signal, p0, ctx, params=dist_params
                    )
                    if confirm_ok and confirm_m:
                        short_ts = int(confirm_m["confirm_ts"])
                        short_px = float(confirm_m["confirm_px"])
                        stop_px = float(p0["drive_high"]) + dist_params.short_stop_pts
                        short_sim = simulate_short_to_stop(
                            ctx.ticks,
                            entry_ts=short_ts,
                            entry_px=short_px,
                            stop_px=stop_px,
                            max_hold_sec=dist_params.short_max_hold_sec,
                        )
                        short_sim["entry_price"] = short_px

        plan = build_replay_plan(
            pick,
            long_row=long_row,
            long_sim=long_sim,
            flip_signal=(
                {
                    "flip_ts": flip_signal.flip_ts,
                    "flip_px": flip_signal.flip_px,
                }
                if flip_signal is not None
                else None
            ),
            short_sim=short_sim,
        )
        plans[day] = plan

    return plans


__all__ = ["build_replay_plans_for_range"]
