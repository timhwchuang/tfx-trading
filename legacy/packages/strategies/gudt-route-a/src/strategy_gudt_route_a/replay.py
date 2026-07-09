"""Build replay event lists from counterfactual pick + exit sim details."""

from __future__ import annotations

from typing import Any

from strategy_gudt_route_a.types import DayReplayPlan, TradeEvent

# CF replay must not schedule entry/exit on the same second (kernel cannot fill both).
MIN_REPLAY_HOLD_SEC = 1


def _exit_ts_from_sim(sim: dict[str, Any], entry_ts: int) -> int:
    hold = int(sim.get("hold_sec") or 0)
    if hold <= 0:
        hold = MIN_REPLAY_HOLD_SEC
    return entry_ts + hold


def build_replay_plan(
    pick: dict[str, Any] | None,
    *,
    long_row: dict[str, Any] | None,
    long_sim: dict[str, Any] | None,
    flip_signal: dict[str, Any] | None = None,
    short_sim: dict[str, Any] | None = None,
) -> DayReplayPlan:
    """Convert stack pick + simulators into timed TradeEvents."""
    if pick is None or long_row is None or long_sim is None:
        day = (pick or long_row or {}).get("day", "")
        return DayReplayPlan(day=str(day), path="skip", skipped=True)

    day = str(pick["day"])
    path = str(pick.get("path", ""))
    entry_ts = int(long_row["entry_ts"])
    entry_px = float(long_row["entry_px"])
    events: list[TradeEvent] = [
        TradeEvent(ts=entry_ts, action="Buy", price=entry_px, leg="long_entry", reason=path),
    ]

    hedge = str(pick.get("hedge", "none"))
    if hedge == "flip" and flip_signal is not None:
        flip_ts = int(flip_signal["flip_ts"])
        flip_px = float(flip_signal["flip_px"])
        events.append(
            TradeEvent(
                ts=flip_ts,
                action="Sell",
                price=flip_px,
                leg="long_exit",
                reason="dist_signal",
            )
        )
        if short_sim is not None and pick.get("dist_confirm") == "pass":
            short_ts = int(pick.get("dist_short_ts") or flip_ts)
            short_px = float(short_sim.get("entry_price") or flip_signal.get("confirm_px") or flip_px)
            events.append(
                TradeEvent(
                    ts=short_ts,
                    action="Sell",
                    price=short_px,
                    leg="short_entry",
                    reason="dist_confirm",
                )
            )
            short_exit_ts = _exit_ts_from_sim(short_sim, short_ts)
            short_exit_px = float(short_sim["exit_price"])
            events.append(
                TradeEvent(
                    ts=short_exit_ts,
                    action="Buy",
                    price=short_exit_px,
                    leg="short_exit",
                    reason=str(short_sim.get("exit_reason", "short_exit")),
                )
            )
    else:
        exit_ts = _exit_ts_from_sim(long_sim, entry_ts)
        exit_px = float(long_sim["exit_price"])
        events.append(
            TradeEvent(
                ts=exit_ts,
                action="Sell",
                price=exit_px,
                leg="long_exit",
                reason=str(long_sim.get("exit_reason", "exit")),
            )
        )

    events.sort(key=lambda e: (e.ts, e.leg))
    meta = {
        "net": pick.get("net"),
        "hedge": pick.get("hedge"),
        "dist_confirm": pick.get("dist_confirm"),
        "route_a_extended": pick.get("route_a_extended"),
        "long_exit": pick.get("long_exit"),
    }
    return DayReplayPlan(day=day, path=path, events=events, meta=meta)
