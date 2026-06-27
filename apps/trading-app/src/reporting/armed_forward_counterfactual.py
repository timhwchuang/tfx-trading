"""FT-004 Phase 0: counterfactual PnL if entry on momentum_armed tick (Thesis A)."""

from __future__ import annotations

import datetime as dt
import statistics
from pathlib import Path
from typing import Any

from reporting.entry_funnel import (
    FORWARD_WINDOWS_SEC,
    _tick_rows_for_day,
    armed_forward_window_stats,
    classify_episode_outcome,
)
from reporting.forward_pnl import _direction_sign, load_tick_series
from reporting.structure_calibration import ArmedCandidate, parse_momentum_armed
from reporting.uat_report import compute_episodes, parse_decision_audits
from storage.tick_loader import resolve_cli_tick_cache_dates

FRICTION_POINTS = 5.0
SCHEMA_VERSION = 1


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return round(statistics.median(values), 2)


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(statistics.mean(values), 2)


def _in_date_range(ts: int, from_date: str, to_date: str) -> bool:
    d = dt.datetime.fromtimestamp(ts).date()
    lo = dt.date.fromisoformat(from_date)
    hi = dt.date.fromisoformat(to_date)
    return lo <= d <= hi


def passes_arm_threshold(
    armed: ArmedCandidate,
    *,
    min_vol_1s: float | None = None,
    min_buy_ratio: float | None = None,
    min_sell_ratio: float | None = None,
) -> bool:
    """Post-filter armed episodes by vol / directional ratio at trigger tick."""
    if min_vol_1s is not None and armed.vol_1s < min_vol_1s:
        return False
    if armed.direction == "Long":
        if min_buy_ratio is not None and armed.buy_ratio < min_buy_ratio:
            return False
    elif armed.direction == "Short":
        if min_sell_ratio is not None and armed.sell_ratio < min_sell_ratio:
            return False
    return True


def passes_adverse_guard(
    armed: ArmedCandidate,
    *,
    max_adverse_atr_k: float | None = None,
) -> bool:
    if max_adverse_atr_k is None or max_adverse_atr_k <= 0:
        return True
    atr = armed.atr if armed.atr > 0 else 25.0
    dist = armed.price - armed.vwap
    limit = max_adverse_atr_k * atr
    if armed.direction == "Long":
        return dist >= -limit
    if armed.direction == "Short":
        return dist <= limit
    return True


def filter_armed_list(
    armed_list: list[ArmedCandidate],
    *,
    min_vol_1s: float | None = None,
    min_buy_ratio: float | None = None,
    min_sell_ratio: float | None = None,
) -> list[ArmedCandidate]:
    return [
        a
        for a in armed_list
        if passes_arm_threshold(
            a,
            min_vol_1s=min_vol_1s,
            min_buy_ratio=min_buy_ratio,
            min_sell_ratio=min_sell_ratio,
        )
    ]


def simulate_atr_barrier_exit(
    *,
    direction: str,
    entry_price: float,
    armed_ts: int,
    atr: float,
    ticks: list[tuple[int, float, int, int]],
    hard_stop_atr_k: float,
    tp_atr_k: float,
    max_hold_sec: int = 180,
) -> dict[str, Any]:
    """Walk tick path from armed_ts; first touch of hard stop or TP wins."""
    if atr <= 0:
        atr = 25.0
    sign = _direction_sign(direction)
    hard_dist = hard_stop_atr_k * atr
    tp_dist = tp_atr_k * atr
    end_ts = armed_ts + max_hold_sec
    mfe = 0.0
    mae = 0.0

    for ts, price, _vol, _tt in ticks:
        if ts < armed_ts:
            continue
        if ts > end_ts:
            break
        delta = sign * (price - entry_price)
        mfe = max(mfe, delta)
        mae = max(mae, -delta)
        if delta <= -hard_dist:
            return {
                "gross_pnl": round(-hard_dist, 2),
                "exit_reason": "stop_loss",
                "hold_sec": ts - armed_ts,
                "mfe": round(mfe, 2),
                "mae": round(mae, 2),
            }
        if delta >= tp_dist:
            return {
                "gross_pnl": round(tp_dist, 2),
                "exit_reason": "take_profit",
                "hold_sec": ts - armed_ts,
                "mfe": round(mfe, 2),
                "mae": round(mae, 2),
            }

    last_price = entry_price
    last_ts = armed_ts
    for ts, price, _v, _t in ticks:
        if armed_ts <= ts <= end_ts:
            last_price = price
            last_ts = ts
    gross = sign * (last_price - entry_price)
    return {
        "gross_pnl": round(gross, 2),
        "exit_reason": "horizon",
        "hold_sec": last_ts - armed_ts,
        "mfe": round(mfe, 2),
        "mae": round(mae, 2),
    }


def _summarize_gross_net(
    key_gross: str, key_net: str, rows: list[dict[str, Any]]
) -> dict[str, Any]:
    gross = [float(r[key_gross]) for r in rows]
    net = [float(r[key_net]) for r in rows]
    return {
        "n": len(rows),
        "gross_mean": _mean(gross),
        "gross_median": _median(gross),
        "net_mean": _mean(net),
        "net_median": _median(net),
        "gross_total": round(sum(gross), 1),
        "net_total": round(sum(net), 1),
    }


def _episode_passes_row_filter(
    row: dict[str, Any],
    *,
    min_vol_1s: float | None,
    min_buy_ratio: float | None,
    min_sell_ratio: float | None,
    max_adverse_atr_k: float | None = None,
) -> bool:
    armed = ArmedCandidate(
        episode_id=str(row["episode_id"]),
        ts=int(row["ts"]),
        direction=str(row["direction"]),
        price=float(row["trigger_price"]),
        atr=float(row["atr"]),
        vwap=float(row.get("vwap") or 0.0),
        vol_1s=int(row.get("vol_1s") or 0),
        buy_ratio=float(row.get("buy_ratio") or 0.0),
        sell_ratio=float(row.get("sell_ratio") or 0.0),
    )
    if not passes_arm_threshold(
        armed,
        min_vol_1s=min_vol_1s,
        min_buy_ratio=min_buy_ratio,
        min_sell_ratio=min_sell_ratio,
    ):
        return False
    return passes_adverse_guard(armed, max_adverse_atr_k=max_adverse_atr_k)


def prepare_counterfactual_episodes(
    *,
    log_lines: list[str],
    code: str,
    cache_dir: Path,
    from_date: str,
    to_date: str,
    hard_stop_atr_k: float = 0.75,
    tp_atr_k: float = 2.0,
    friction_points: float = FRICTION_POINTS,
) -> tuple[list[dict[str, Any]], dict[str, str], int]:
    """Precompute per-armed episode rows (all triggers in range)."""
    decisions = parse_decision_audits(log_lines)
    armed_list = [
        a for a in parse_momentum_armed(decisions) if _in_date_range(a.ts, from_date, to_date)
    ]
    armed_total = len(armed_list)
    episodes = {ep.episode_id: ep for ep in compute_episodes(log_lines)}
    outcome_by_episode = {
        ep_id: classify_episode_outcome(ep) for ep_id, ep in episodes.items()
    }

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

    tick_series = load_tick_series(code, dates, cache_dir=cache_dir)
    day_ticks: dict[dt.date, list[tuple[int, float, int, int]]] = {
        day: _tick_rows_for_day(code, day, cache_dir=cache_dir) for day in dates
    }

    per_episode: list[dict[str, Any]] = []
    for armed in armed_list:
        day = dt.datetime.fromtimestamp(armed.ts).date()
        ticks = day_ticks.get(day, [])
        atr = armed.atr if armed.atr > 0 else 25.0
        forward: dict[str, Any] = {}
        for w in FORWARD_WINDOWS_SEC:
            forward[f"W{w}"] = armed_forward_window_stats(armed, tick_series, w, atr=atr)

        sim = simulate_atr_barrier_exit(
            direction=armed.direction,
            entry_price=armed.price,
            armed_ts=armed.ts,
            atr=atr,
            ticks=ticks,
            hard_stop_atr_k=hard_stop_atr_k,
            tp_atr_k=tp_atr_k,
        )
        gross_w180 = float(forward.get("W180", {}).get("close_delta", 0.0))
        net_w180 = gross_w180 - friction_points
        gross_sim = float(sim["gross_pnl"])
        net_sim = gross_sim - friction_points

        per_episode.append(
            {
                "episode_id": armed.episode_id,
                "ts": armed.ts,
                "outcome_v1": outcome_by_episode.get(armed.episode_id, "unknown"),
                "direction": armed.direction,
                "trigger_price": armed.price,
                "atr": atr,
                "vol_1s": armed.vol_1s,
                "buy_ratio": armed.buy_ratio,
                "sell_ratio": armed.sell_ratio,
                "vwap": armed.vwap,
                "forward": forward,
                "atr_barrier_sim": sim,
                "gross_w180": gross_w180,
                "net_w180": net_w180,
                "gross_atr_sim": gross_sim,
                "net_atr_sim": net_sim,
            }
        )
    return per_episode, outcome_by_episode, armed_total


def build_counterfactual_payload_from_rows(
    *,
    per_episode_all: list[dict[str, Any]],
    armed_total: int,
    from_date: str,
    to_date: str,
    code: str,
    hard_stop_atr_k: float = 0.75,
    tp_atr_k: float = 2.0,
    friction_points: float = FRICTION_POINTS,
    min_vol_1s: float | None = None,
    min_buy_ratio: float | None = None,
    min_sell_ratio: float | None = None,
    max_adverse_atr_k: float | None = None,
) -> dict[str, Any]:
    per_episode = [
        row
        for row in per_episode_all
        if _episode_passes_row_filter(
            row,
            min_vol_1s=min_vol_1s,
            min_buy_ratio=min_buy_ratio,
            min_sell_ratio=min_sell_ratio,
            max_adverse_atr_k=max_adverse_atr_k,
        )
    ]

    by_outcome: dict[str, list[dict[str, Any]]] = {}
    for row in per_episode:
        by_outcome.setdefault(row["outcome_v1"], []).append(row)

    return {
        "schema_version": SCHEMA_VERSION,
        "thesis": "armed_forward_immediate_entry",
        "from_date": from_date,
        "to_date": to_date,
        "code": code,
        "friction_points_per_round_trip": friction_points,
        "sim_params": {
            "hard_stop_atr_k": hard_stop_atr_k,
            "tp_atr_k": tp_atr_k,
            "max_hold_sec": 180,
        },
        "arm_filter": {
            "min_vol_1s": min_vol_1s,
            "min_buy_ratio": min_buy_ratio,
            "min_sell_ratio": min_sell_ratio,
            "max_adverse_atr_k": max_adverse_atr_k,
            "armed_before_filter": armed_total,
            "armed_after_filter": len(per_episode),
        },
        "summary_all": {
            "w180_horizon": _summarize_gross_net("gross_w180", "net_w180", per_episode),
            "atr_barrier_180s": _summarize_gross_net(
                "gross_atr_sim", "net_atr_sim", per_episode
            ),
        },
        "summary_by_outcome_v1": {
            outcome: {
                "w180_horizon": _summarize_gross_net("gross_w180", "net_w180", rows),
                "atr_barrier_180s": _summarize_gross_net(
                    "gross_atr_sim", "net_atr_sim", rows
                ),
            }
            for outcome, rows in sorted(by_outcome.items())
        },
        "episode_count": len(per_episode),
        "episodes": per_episode,
    }


def build_counterfactual_payload(
    *,
    log_lines: list[str],
    code: str,
    cache_dir: Path,
    from_date: str,
    to_date: str,
    hard_stop_atr_k: float = 0.75,
    tp_atr_k: float = 2.0,
    friction_points: float = FRICTION_POINTS,
    min_vol_1s: float | None = None,
    min_buy_ratio: float | None = None,
    min_sell_ratio: float | None = None,
    max_adverse_atr_k: float | None = None,
) -> dict[str, Any]:
    per_episode_all, _outcomes, armed_total = prepare_counterfactual_episodes(
        log_lines=log_lines,
        code=code,
        cache_dir=cache_dir,
        from_date=from_date,
        to_date=to_date,
        hard_stop_atr_k=hard_stop_atr_k,
        tp_atr_k=tp_atr_k,
        friction_points=friction_points,
    )
    return build_counterfactual_payload_from_rows(
        per_episode_all=per_episode_all,
        armed_total=armed_total,
        from_date=from_date,
        to_date=to_date,
        code=code,
        hard_stop_atr_k=hard_stop_atr_k,
        tp_atr_k=tp_atr_k,
        friction_points=friction_points,
        min_vol_1s=min_vol_1s,
        min_buy_ratio=min_buy_ratio,
        min_sell_ratio=min_sell_ratio,
        max_adverse_atr_k=max_adverse_atr_k,
    )
