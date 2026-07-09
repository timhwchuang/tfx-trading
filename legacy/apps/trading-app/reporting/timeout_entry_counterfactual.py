"""FT-005 Phase 0: counterfactual PnL for timeout-selective entry timings (Thesis B)."""

from __future__ import annotations

import bisect
import datetime as dt
import statistics
from pathlib import Path
from typing import Any

from reporting.armed_forward_counterfactual import (
    FRICTION_POINTS,
    _in_date_range,
    _summarize_gross_net,
    simulate_atr_barrier_exit,
)
from reporting.entry_funnel import (
    EntryFunnelConfig,
    _tick_rows_for_day,
    classify_episode_outcome,
    episode_end_ts,
    replay_episode_funnel,
)
from reporting.structure_calibration import ArmedCandidate, parse_momentum_armed
from reporting.uat_report import Episode, compute_episodes, parse_decision_audits
from storage.tick_loader import resolve_cli_tick_cache_dates

SCHEMA_VERSION = 1

ENTRY_TIMINGS = (
    "armed_tick",
    "timeout_tick",
    "armed_plus_60s",
    "armed_plus_120s",
)


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return round(statistics.median(values), 2)


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(statistics.mean(values), 2)


def _timeout_event(ep: Episode) -> dict[str, Any] | None:
    for ev in ep.events or []:
        if ev.get("event_type") == "momentum_timeout":
            return ev
    return None


def _price_at_or_after(
    ticks: list[tuple[int, float, int, int]],
    target_ts: int,
) -> tuple[int, float] | None:
    if not ticks:
        return None
    idx = bisect.bisect_left([t[0] for t in ticks], target_ts)
    if idx >= len(ticks):
        return None
    ts, price, _v, _tt = ticks[idx]
    return ts, price


def resolve_entry_point(
    timing: str,
    *,
    armed: ArmedCandidate,
    ep: Episode,
    ticks: list[tuple[int, float, int, int]],
    momentum_timeout_sec: int,
) -> tuple[int, float] | None:
    """Return (entry_ts, entry_price) for a named timing variant."""
    if timing == "armed_tick":
        return armed.ts, armed.price

    if timing == "timeout_tick":
        ev = _timeout_event(ep)
        if ev is None:
            armed_ts = armed.ts
            entry_ts = armed_ts + momentum_timeout_sec + 1
            pt = _price_at_or_after(ticks, entry_ts)
            if pt is None:
                return None
            return pt
        ts = int(ev.get("ts") or 0)
        price = float(ev.get("price") or armed.price)
        return ts, price

    if timing.startswith("armed_plus_"):
        try:
            offset = int(timing.removeprefix("armed_plus_").removesuffix("s"))
        except ValueError:
            return None
        return _price_at_or_after(ticks, armed.ts + offset)

    return None


def _episode_ever_near_vwap(
    ep: Episode,
    armed: ArmedCandidate,
    ticks: list[tuple[int, float, int, int]],
    cfg: EntryFunnelConfig,
) -> bool:
    armed_ts, end_ts, entry_ts = episode_end_ts(ep, cfg)
    stats = replay_episode_funnel(
        ticks,
        armed_ts=armed_ts,
        end_ts=end_ts,
        trigger_price=armed.price,
        direction=armed.direction,
        cfg=cfg,
        vol_at_arm_audit=armed.vol_1s,
        entry_ts=entry_ts,
    )
    return stats.ever_near_vwap


def prepare_timeout_counterfactual_rows(
    *,
    log_lines: list[str],
    code: str,
    cache_dir: Path,
    from_date: str,
    to_date: str,
    hard_stop_atr_k: float = 0.75,
    tp_atr_k: float = 2.0,
    friction_points: float = FRICTION_POINTS,
    entry_band_points: float = 2.0,
    momentum_timeout_sec: int = 180,
    exhaustion_vol: int = 15,
) -> tuple[list[dict[str, Any]], dict[str, str], int]:
    """Build per-episode rows for each entry timing (timeout v1 cohort focus)."""
    decisions = parse_decision_audits(log_lines)
    armed_list = [
        a for a in parse_momentum_armed(decisions) if _in_date_range(a.ts, from_date, to_date)
    ]
    armed_total = len(armed_list)
    episodes = {ep.episode_id: ep for ep in compute_episodes(log_lines)}
    outcome_by_episode = {
        ep_id: classify_episode_outcome(ep) for ep_id, ep in episodes.items()
    }

    funnel_cfg = EntryFunnelConfig(
        entry_band_points=entry_band_points,
        momentum_vol_1s=150.0,
        exhaustion_vol=exhaustion_vol,
        momentum_timeout_sec=momentum_timeout_sec,
        vwap_window_min=5,
    )

    dates = resolve_cli_tick_cache_dates(
        explicit=None,
        from_cache=True,
        code=code,
        cache_dir=cache_dir,
        from_date=from_date,
        to_date=to_date,
    )
    if not dates:
        raise ValueError(f"no tick cache dates for {from_date}..{to_date}")

    day_ticks: dict[dt.date, list[tuple[int, float, int, int]]] = {
        day: _tick_rows_for_day(code, day, cache_dir=cache_dir) for day in dates
    }

    rows: list[dict[str, Any]] = []
    for armed in armed_list:
        ep = episodes.get(armed.episode_id)
        if ep is None:
            continue
        outcome_v1 = outcome_by_episode.get(armed.episode_id, "unknown")
        day = dt.datetime.fromtimestamp(armed.ts).date()
        ticks = day_ticks.get(day, [])
        atr = armed.atr if armed.atr > 0 else 25.0
        ever_near = _episode_ever_near_vwap(ep, armed, ticks, funnel_cfg)

        for timing in ENTRY_TIMINGS:
            entry = resolve_entry_point(
                timing,
                armed=armed,
                ep=ep,
                ticks=ticks,
                momentum_timeout_sec=momentum_timeout_sec,
            )
            if entry is None:
                continue
            entry_ts, entry_price = entry
            sim = simulate_atr_barrier_exit(
                direction=armed.direction,
                entry_price=entry_price,
                armed_ts=entry_ts,
                atr=atr,
                ticks=ticks,
                hard_stop_atr_k=hard_stop_atr_k,
                tp_atr_k=tp_atr_k,
            )
            gross = float(sim["gross_pnl"])
            net = gross - friction_points
            rows.append(
                {
                    "episode_id": armed.episode_id,
                    "outcome_v1": outcome_v1,
                    "entry_timing": timing,
                    "direction": armed.direction,
                    "armed_ts": armed.ts,
                    "entry_ts": entry_ts,
                    "entry_price": entry_price,
                    "atr": atr,
                    "ever_near_vwap": ever_near,
                    "vol_1s": armed.vol_1s,
                    "buy_ratio": armed.buy_ratio,
                    "sell_ratio": armed.sell_ratio,
                    "gross_atr_sim": gross,
                    "net_atr_sim": net,
                    "atr_barrier_sim": sim,
                }
            )
    return rows, outcome_by_episode, armed_total


def build_timeout_counterfactual_payload(
    *,
    log_lines: list[str],
    code: str,
    cache_dir: Path,
    from_date: str,
    to_date: str,
    hard_stop_atr_k: float = 0.75,
    tp_atr_k: float = 2.0,
    friction_points: float = FRICTION_POINTS,
    entry_band_points: float = 2.0,
    momentum_timeout_sec: int = 180,
) -> dict[str, Any]:
    all_rows, _outcomes, armed_total = prepare_timeout_counterfactual_rows(
        log_lines=log_lines,
        code=code,
        cache_dir=cache_dir,
        from_date=from_date,
        to_date=to_date,
        hard_stop_atr_k=hard_stop_atr_k,
        tp_atr_k=tp_atr_k,
        friction_points=friction_points,
        entry_band_points=entry_band_points,
        momentum_timeout_sec=momentum_timeout_sec,
    )

    timeout_rows = [r for r in all_rows if r["outcome_v1"] == "timeout"]
    never_band_rows = [r for r in timeout_rows if not r["ever_near_vwap"]]

    def _by_timing(rows: list[dict[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for timing in ENTRY_TIMINGS:
            subset = [r for r in rows if r["entry_timing"] == timing]
            out[timing] = _summarize_gross_net("gross_atr_sim", "net_atr_sim", subset)
        return out

    timeout_tick_summary = _by_timing(timeout_rows).get("timeout_tick", {})
    phase0_pass = (
        (timeout_tick_summary.get("gross_mean") or 0) > 5
        and (timeout_tick_summary.get("net_mean") or 0) > 0
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "thesis": "timeout_selective_entry",
        "from_date": from_date,
        "to_date": to_date,
        "code": code,
        "friction_points_per_round_trip": friction_points,
        "sim_params": {
            "hard_stop_atr_k": hard_stop_atr_k,
            "tp_atr_k": tp_atr_k,
            "max_hold_sec": 180,
            "entry_band_points": entry_band_points,
            "momentum_timeout_sec": momentum_timeout_sec,
        },
        "phase0_gate": {
            "cohort": "outcome_v1=timeout",
            "timing": "timeout_tick",
            "gross_mean_min": 5.0,
            "net_mean_min": 0.0,
            "pass": phase0_pass,
            "timeout_tick_summary": timeout_tick_summary,
        },
        "summary_by_timing_all_outcomes": _by_timing(all_rows),
        "summary_by_timing_timeout_cohort": _by_timing(timeout_rows),
        "summary_by_timing_timeout_never_near_vwap": _by_timing(never_band_rows),
        "armed_episodes_in_range": armed_total,
        "timeout_cohort_episodes": len({r["episode_id"] for r in timeout_rows}),
        "rows": all_rows,
    }
