"""FT-018b Route A stack: B′+br5 long sim + 5m EMA extension + distribution confirm flip."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from strategy_gudt_route_a.route_a_exit import RouteAParams, simulate_route_a_exit
from strategy_gudt_route_a.wash_bridge import (
    BPrimeCompositeParams,
    DayWashContext,
    DistributionHedgeParams,
    ProbeEntry,
    _probe_entry_from_row,
    _row_for,
    _simulate_exit,
    apply_hedge_distribution_short,
    rule_pick_for_day,
)

FRICTION_POINTS = 5.0


@dataclass(frozen=True)
class RouteAStackParams:
    """B′+br5 router with Route A p0 exits and structural distribution flip."""

    route_a: RouteAParams = RouteAParams(extension_exit="ema5")
    br5: BPrimeCompositeParams = BPrimeCompositeParams(
        pre_break_br_min=0.35,
        pre_break_br_p0_only=True,
        flip_min_ext_open=5.0,
        distribution=DistributionHedgeParams(
            confirm_sec=120,
            confirm_min_dump_atr=0.65,
            confirm_slope2_min=-0.35,
            confirm_slope2_max=0.0,
        ),
    )


def _long_net_for_pick(
    pick: dict[str, Any],
    day_rows: list[dict[str, Any]],
    ctx: DayWashContext,
    *,
    params: RouteAStackParams,
    friction: float = FRICTION_POINTS,
) -> tuple[float, dict[str, Any]]:
    path = pick["path"]
    if path.startswith("p0"):
        row = _row_for(day_rows, "p0", "sealed")
        entry = _probe_entry_from_row(row)
        sim = simulate_route_a_exit(entry, ctx, params=params.route_a)
        net = round(float(sim["gross_pnl"]) - friction, 2)
        return net, sim
    em = path.split("+")[0]
    ex = "drive_low_struct" if "drive_low" in path else "flow_bailout"
    row = _row_for(day_rows, em if em in ("flow_turn", "reclaim_br", "p0") else "flow_turn", ex)
    if row is None:
        row = _row_for(day_rows, "flow_turn", ex)
    sim = _simulate_exit(_probe_entry_from_row(row), ctx, ex)
    net = round(float(sim["gross_pnl"]) - friction, 2)
    return net, sim


def apply_route_a_stack_day(
    day_rows: list[dict[str, Any]],
    ctx: DayWashContext,
    *,
    params: RouteAStackParams | None = None,
    friction: float = FRICTION_POINTS,
) -> dict[str, Any] | None:
    """Single day: B′ pick → Route A long economics → optional dist flip."""
    params = params or RouteAStackParams()
    br = params.br5
    day = day_rows[0]["day"]

    base = rule_pick_for_day(day_rows, rule="B_prime", ft_exit=br.ft_exit)
    if base is None:
        return None

    if br.pre_break_br_p0_only and br.pre_break_br_min is not None and base["path"].startswith("p0"):
        from strategy_gudt_route_a.wash_bridge import pre_break_br_at, _fallback_ft_from_p0_veto

        br5 = pre_break_br_at(ctx)
        if br5 is not None and br5 < br.pre_break_br_min:
            fb = _fallback_ft_from_p0_veto(day, day_rows, ft_exit=br.ft_exit, tag="br5_veto")
            if fb is None:
                return None
            base = fb

    long_net, long_sim = _long_net_for_pick(base, day_rows, ctx, params=params, friction=friction)
    pick = {
        **base,
        "net": long_net,
        "long_net": long_net,
        "short_net": 0.0,
        "hedge": "none",
        "long_exit": long_sim.get("exit_reason"),
        "route_a_extended": bool(long_sim.get("extended")),
        "stack": "route_a_uat",
    }

    if br.flip_min_ext_open is not None:
        from strategy_gudt_route_a.wash_bridge import ext_open_atr

        ext = ext_open_atr(ctx)
        if ext is None or ext <= br.flip_min_ext_open:
            return pick

    flipped = apply_hedge_distribution_short(
        pick, day_rows, ctx, params=br.distribution, friction=friction
    )
    flipped["stack"] = "route_a_uat"
    flipped["long_exit"] = pick.get("long_exit")
    flipped["route_a_extended"] = pick.get("route_a_extended")
    return flipped


def summarize_route_a_stack(
    rows: list[dict[str, Any]],
    *,
    ctx_by_day: dict[str, DayWashContext],
    params: RouteAStackParams | None = None,
) -> dict[str, Any]:
    params = params or RouteAStackParams()
    by_day: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_day.setdefault(r["day"], []).append(r)
    picks: list[dict[str, Any]] = []
    skipped = 0
    for day_rows in by_day.values():
        ctx = ctx_by_day.get(day_rows[0]["day"])
        if ctx is None:
            skipped += 1
            continue
        p = apply_route_a_stack_day(day_rows, ctx, params=params)
        if p is None:
            skipped += 1
            continue
        picks.append(p)
    nets = [float(p["net"]) for p in picks]
    return {
        "stack": "route_a_uat",
        "params": params,
        "n": len(picks),
        "skipped": skipped,
        "flip_days": sum(1 for p in picks if p.get("hedge") == "flip"),
        "confirm_veto": sum(1 for p in picks if p.get("dist_confirm") == "veto"),
        "extend_days": sum(1 for p in picks if p.get("route_a_extended")),
        "net_total": round(sum(nets), 2),
        "net_mean": round(sum(nets) / len(nets), 2) if nets else 0.0,
        "picks": picks,
    }
