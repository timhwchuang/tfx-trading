"""Wash-day open-to-flatten CF simulator (FT-023)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from strategy_gudt_route_a.replay import MIN_REPLAY_HOLD_SEC
from strategy_gudt_route_a.types import DayReplayPlan, TradeEvent


@dataclass(frozen=True)
class WashBetaParams:
    friction_points: float = 5.0
    session_start: dt.time = dt.time(8, 45)
    force_flatten_time: dt.time = dt.time(13, 44)


def _combine_ts(day: dt.date, clock: dt.time) -> int:
    return int(dt.datetime.combine(day, clock).timestamp())


def _first_tick_at_or_after(
    ticks: list[tuple[int, float, int, int]],
    threshold_ts: int,
) -> tuple[int, float] | None:
    for ts, price, _vol, _tt in ticks:
        if ts >= threshold_ts:
            return ts, float(price)
    return None


def _last_tick_at_or_before(
    ticks: list[tuple[int, float, int, int]],
    threshold_ts: int,
) -> tuple[int, float] | None:
    last: tuple[int, float] | None = None
    for ts, price, _vol, _tt in ticks:
        if ts > threshold_ts:
            break
        last = (ts, float(price))
    return last


def simulate_wash_beta_day(
    ctx: Any,
    *,
    params: WashBetaParams | None = None,
) -> dict[str, Any] | None:
    """Long at session open tick; exit at market tick on force-flatten time.

    Uses market prices only (no structural stops). Returns None when ticks missing.
    """
    params = params or WashBetaParams()
    day = ctx.day if isinstance(ctx.day, dt.date) else dt.date.fromisoformat(str(ctx.day))
    ticks = ctx.ticks
    if not ticks:
        return None

    start_ts = _combine_ts(day, params.session_start)
    flatten_ts = _combine_ts(day, params.force_flatten_time)

    entry = _first_tick_at_or_after(ticks, start_ts)
    if entry is None:
        entry_px = float(ctx.open_0845)
        entry_ts = start_ts
    else:
        entry_ts, entry_px = entry

    exit_tick = _first_tick_at_or_after(ticks, flatten_ts)
    if exit_tick is None:
        exit_tick = _last_tick_at_or_before(ticks, flatten_ts)
    if exit_tick is None:
        return None
    exit_ts, exit_px = exit_tick

    if exit_ts < entry_ts:
        aligned = _first_tick_at_or_after(ticks, entry_ts)
        if aligned is None:
            exit_ts, exit_px = entry_ts, entry_px
        else:
            exit_ts, exit_px = aligned

    gross = round(exit_px - entry_px, 2)
    net = round(gross - params.friction_points, 2)
    hold_sec = max(0, exit_ts - entry_ts)
    return {
        "gross_pnl": gross,
        "net": net,
        "entry_ts": entry_ts,
        "entry_px": round(entry_px, 2),
        "exit_ts": exit_ts,
        "exit_px": round(exit_px, 2),
        "exit_reason": "session_force_flatten",
        "hold_sec": hold_sec,
    }


def build_wash_beta_replay_plan(day: str, sim: dict[str, Any]) -> DayReplayPlan:
    """Entry + flatten exit events for execution parity pairing."""
    path = "wash_beta"
    entry_ts = int(sim["entry_ts"])
    exit_ts = int(sim["exit_ts"])
    if exit_ts <= entry_ts:
        exit_ts = entry_ts + MIN_REPLAY_HOLD_SEC
    events = [
        TradeEvent(
            ts=entry_ts,
            action="Buy",
            price=float(sim["entry_px"]),
            leg="long_entry",
            reason=path,
        ),
        TradeEvent(
            ts=exit_ts,
            action="Sell",
            price=float(sim["exit_px"]),
            leg="long_exit",
            reason=str(sim["exit_reason"]),
        ),
    ]
    return DayReplayPlan(
        day=day,
        path=path,
        events=events,
        meta={
            "net": sim["net"],
            "gross_pnl": sim["gross_pnl"],
            "long_exit": sim["exit_reason"],
            "hedge": "none",
        },
    )


def build_wash_beta_live_intraday_plan(
    day: str,
    ctx: Any,
    *,
    params: WashBetaParams | None = None,
) -> DayReplayPlan | None:
    """Live plan: entry from ticks so far; exit scheduled at config flatten (not CF EOD price)."""
    params = params or WashBetaParams()
    day_date = ctx.day if isinstance(ctx.day, dt.date) else dt.date.fromisoformat(str(day))
    ticks = ctx.ticks
    if not ticks:
        return None

    start_ts = _combine_ts(day_date, params.session_start)
    flatten_ts = _combine_ts(day_date, params.force_flatten_time)

    entry = _first_tick_at_or_after(ticks, start_ts)
    if entry is None:
        entry_px = float(ctx.open_0845)
        entry_ts = start_ts
    else:
        entry_ts, entry_px = entry

    exit_ts = flatten_ts
    if exit_ts <= entry_ts:
        exit_ts = entry_ts + MIN_REPLAY_HOLD_SEC

    sim = {
        "entry_ts": entry_ts,
        "entry_px": round(entry_px, 2),
        "exit_ts": exit_ts,
        "exit_px": round(entry_px, 2),
        "exit_reason": "session_force_flatten",
        "gross_pnl": 0.0,
        "net": -params.friction_points,
        "hold_sec": exit_ts - entry_ts,
    }
    return build_wash_beta_replay_plan(day, sim)


def summarize_wash_beta(picks: list[dict[str, Any]]) -> dict[str, Any]:
    nets = [float(p["net"]) for p in picks]
    return {
        "stack": "wash_beta",
        "n": len(picks),
        "net_total": round(sum(nets), 2),
        "net_mean": round(sum(nets) / len(nets), 2) if nets else 0.0,
        "picks": picks,
    }
