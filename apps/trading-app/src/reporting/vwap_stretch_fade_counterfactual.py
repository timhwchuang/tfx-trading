"""FT-006 Phase 0: counterfactual VWAP stretch fade (mean reversion, no spike)."""

from __future__ import annotations

import bisect
import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from reporting.armed_forward_counterfactual import (
    FRICTION_POINTS,
    _summarize_gross_net,
    simulate_atr_barrier_exit,
)
from reporting.forward_pnl import ForwardPnlPolicy, TickSeries, make_replay_forward_pnl
from reporting.volatility_baseline import (
    DEFAULT_ATR_PERIOD,
    atr_series_from_bars,
)
from storage.kbar_loader import load_kbars_csv, resolve_kbar_path
from storage.tick_loader import ReplayTick, iter_replay_ticks, resolve_cli_tick_cache_dates
from trading_engine.indicators import IndicatorState

SCHEMA_VERSION = 1
DEFAULT_STRETCH_KS = (1.5, 2.0, 2.5)
DEFAULT_RESET_Z = 0.5
DEFAULT_COOLDOWN_SEC = 60
DEFAULT_VWAP_WINDOW_MIN = 5
DEFAULT_MIN_ATR = 25.0
SESSION_START = dt.time(8, 45)
SESSION_END = dt.time(13, 45)
OPEN_30M_END = dt.time(9, 15)
CLOSE_1H_START = dt.time(12, 45)

PHASE0_GROSS_MIN = 5.0
PHASE0_NET_MIN = 0.0
PHASE0_MIN_N = 30


@dataclass(frozen=True)
class TickSnapshot:
    ts: int
    price: float
    vwap: float
    atr: float
    z: float
    session_bucket: str


def session_bucket_for_ts(ts: int) -> str:
    """Bucket per ENTRY_FUNNEL_METRICS §7.1 (exchange local time)."""
    t = dt.datetime.fromtimestamp(ts).time()
    if t < SESSION_START or t > SESSION_END:
        return "out_of_session"
    if SESSION_START <= t < OPEN_30M_END:
        return "open_30m"
    if t >= CLOSE_1H_START:
        return "close_1h"
    return "mid"


def _bar_atr_lookup(
    kbar_path: Path,
    *,
    period: int = DEFAULT_ATR_PERIOD,
) -> list[tuple[int, float]]:
    """Map bar end epoch -> ATR (SMA TR, matches IndicatorState.compute_atr)."""
    bars_records = load_kbars_csv(kbar_path)
    bar_tuples = [
        (b.High, b.Low, b.Close, b.High - b.Low, float(b.Volume)) for b in bars_records
    ]
    atrs = atr_series_from_bars(bar_tuples, period=period)
    if not atrs:
        return []
    out: list[tuple[int, float]] = []
    for k, atr in enumerate(atrs):
        bar_idx = k + period
        if bar_idx >= len(bars_records):
            break
        bar_ts = int(bars_records[bar_idx].ts.timestamp())
        out.append((bar_ts, float(atr)))
    return out


def _atr_at_ts(lookup: list[tuple[int, float]], ts: int, fallback: float) -> float:
    if not lookup:
        return fallback
    stamps = [x[0] for x in lookup]
    idx = bisect.bisect_right(stamps, ts) - 1
    if idx < 0:
        return fallback
    atr = lookup[idx][1]
    return atr if atr > 0 else fallback


def build_day_snapshots(
    code: str,
    day: dt.date,
    *,
    cache_dir: Path,
    vwap_window_min: int = DEFAULT_VWAP_WINDOW_MIN,
    min_atr: float = DEFAULT_MIN_ATR,
) -> list[TickSnapshot]:
    kpath = resolve_kbar_path(cache_dir, code, day)
    atr_lookup = _bar_atr_lookup(kpath) if kpath is not None else []
    ind = IndicatorState(vwap_window_min=vwap_window_min)
    snaps: list[TickSnapshot] = []

    for tick in iter_replay_ticks(code, [day], cache_dir=cache_dir):
        ts = int(tick.datetime.timestamp())
        price = float(tick.close)
        volume = int(tick.volume)
        tick_type = int(tick.tick_type)
        ind.update_vwap(ts, price, volume)
        ind.update_momentum(ts, volume, tick_type)
        vwap = ind.current_vwap
        atr = max(_atr_at_ts(atr_lookup, ts, min_atr), min_atr)
        z = (price - vwap) / atr if atr > 0 else 0.0
        snaps.append(
            TickSnapshot(
                ts=ts,
                price=price,
                vwap=vwap,
                atr=atr,
                z=z,
                session_bucket=session_bucket_for_ts(ts),
            )
        )
    return snaps


def fade_direction(z: float) -> str:
    return "Short" if z > 0 else "Long"


def audit_direction(direction: str) -> str:
    return "Sell" if direction == "Short" else "Buy"


def simulate_stretch_fade_entries(
    snapshots: list[TickSnapshot],
    ticks: list[tuple[int, float, int, int]],
    *,
    stretch_k: float,
    reset_z: float = DEFAULT_RESET_Z,
    cooldown_sec: int = DEFAULT_COOLDOWN_SEC,
    hard_stop_atr_k: float = 0.75,
    tp_atr_k: float = 2.0,
    friction_points: float = FRICTION_POINTS,
    forward_fn: Any | None = None,
) -> list[dict[str, Any]]:
    """Walk snapshots; emit fade entries when |z| crosses stretch_k (debounced)."""
    rows: list[dict[str, Any]] = []
    can_arm = True
    last_entry_ts: int | None = None

    for snap in snapshots:
        if snap.session_bucket == "out_of_session":
            continue

        if not can_arm and abs(snap.z) <= reset_z:
            can_arm = True

        if last_entry_ts is not None and snap.ts - last_entry_ts < cooldown_sec:
            continue

        if not can_arm or abs(snap.z) < stretch_k:
            continue

        direction = fade_direction(snap.z)
        sim = simulate_atr_barrier_exit(
            direction=direction,
            entry_price=snap.price,
            armed_ts=snap.ts,
            atr=snap.atr,
            ticks=ticks,
            hard_stop_atr_k=hard_stop_atr_k,
            tp_atr_k=tp_atr_k,
        )
        gross_barrier = float(sim["gross_pnl"])
        net_barrier = gross_barrier - friction_points
        gross_horizon = 0.0
        net_horizon = 0.0
        if forward_fn is not None:
            gross_horizon = float(forward_fn(snap.price, snap.ts, audit_direction(direction)))
            net_horizon = gross_horizon - friction_points

        rows.append(
            {
                "ts": snap.ts,
                "stretch_k": stretch_k,
                "direction": direction,
                "entry_price": snap.price,
                "vwap": round(snap.vwap, 2),
                "atr": round(snap.atr, 2),
                "z": round(snap.z, 4),
                "session_bucket": snap.session_bucket,
                "gross_atr_sim": gross_barrier,
                "net_atr_sim": net_barrier,
                "gross_horizon": gross_horizon,
                "net_horizon": net_horizon,
                "atr_barrier_sim": sim,
            }
        )
        can_arm = False
        last_entry_ts = snap.ts

    return rows


def _tick_rows_for_day(code: str, day: dt.date, *, cache_dir: Path) -> list[tuple[int, float, int, int]]:
    rows: list[tuple[int, float, int, int]] = []
    for tick in iter_replay_ticks(code, [day], cache_dir=cache_dir):
        rows.append(
            (
                int(tick.datetime.timestamp()),
                float(tick.close),
                int(tick.volume),
                int(tick.tick_type),
            )
        )
    return rows


def _summary_block(rows: list[dict[str, Any]], gross_key: str, net_key: str) -> dict[str, Any]:
    return _summarize_gross_net(gross_key, net_key, rows)


def _group_summary(
    rows: list[dict[str, Any]],
    key: str,
) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row[key]), []).append(row)
    return {
        g: {
            "atr_barrier_180s": _summary_block(sub, "gross_atr_sim", "net_atr_sim"),
            "horizon_1800s": _summary_block(sub, "gross_horizon", "net_horizon"),
        }
        for g, sub in sorted(groups.items())
    }


def _evaluate_phase0_gate(
    summary_by_k_and_bucket: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    best: dict[str, Any] | None = None
    passed = False
    for k, buckets in summary_by_k_and_bucket.items():
        for bucket, metrics in buckets.items():
            if bucket == "out_of_session":
                continue
            s = metrics.get("atr_barrier_180s") or {}
            n = int(s.get("n") or 0)
            gross = s.get("gross_mean")
            net = s.get("net_mean")
            if gross is None or net is None:
                continue
            candidate = {
                "stretch_k": float(k),
                "session_bucket": bucket,
                "n": n,
                "gross_mean": gross,
                "net_mean": net,
            }
            if (
                n >= PHASE0_MIN_N
                and gross > PHASE0_GROSS_MIN
                and net > PHASE0_NET_MIN
            ):
                passed = True
                if best is None or gross > best.get("gross_mean", 0):
                    best = candidate
    return {
        "pass": passed,
        "gross_mean_min": PHASE0_GROSS_MIN,
        "net_mean_min": PHASE0_NET_MIN,
        "min_n": PHASE0_MIN_N,
        "best_passing": best,
    }


def build_vwap_stretch_fade_payload(
    *,
    code: str,
    cache_dir: Path,
    from_date: str,
    to_date: str,
    stretch_ks: tuple[float, ...] = DEFAULT_STRETCH_KS,
    reset_z: float = DEFAULT_RESET_Z,
    cooldown_sec: int = DEFAULT_COOLDOWN_SEC,
    hard_stop_atr_k: float = 0.75,
    tp_atr_k: float = 2.0,
    friction_points: float = FRICTION_POINTS,
    horizon_seconds: int = 1800,
    vwap_window_min: int = DEFAULT_VWAP_WINDOW_MIN,
) -> dict[str, Any]:
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

    # Forward PnL over merged range
    from reporting.forward_pnl import load_tick_series

    series = load_tick_series(code, dates, cache_dir=cache_dir)
    forward_fn = make_replay_forward_pnl(
        series,
        ForwardPnlPolicy(mode="fixed_seconds", window_seconds=horizon_seconds),
    )

    all_by_k: dict[float, list[dict[str, Any]]] = {k: [] for k in stretch_ks}

    for day in dates:
        snaps = build_day_snapshots(
            code, day, cache_dir=cache_dir, vwap_window_min=vwap_window_min
        )
        if not snaps:
            continue
        day_ticks = _tick_rows_for_day(code, day, cache_dir=cache_dir)
        for k in stretch_ks:
            all_by_k[k].extend(
                simulate_stretch_fade_entries(
                    snaps,
                    day_ticks,
                    stretch_k=k,
                    reset_z=reset_z,
                    cooldown_sec=cooldown_sec,
                    hard_stop_atr_k=hard_stop_atr_k,
                    tp_atr_k=tp_atr_k,
                    friction_points=friction_points,
                    forward_fn=forward_fn,
                )
            )

    summary_by_k: dict[str, Any] = {}
    summary_by_k_and_bucket: dict[str, dict[str, Any]] = {}
    for k in stretch_ks:
        rows = all_by_k[k]
        summary_by_k[str(k)] = {
            "atr_barrier_180s": _summary_block(rows, "gross_atr_sim", "net_atr_sim"),
            "horizon_1800s": _summary_block(rows, "gross_horizon", "net_horizon"),
        }
        by_bucket = _group_summary(rows, "session_bucket")
        summary_by_k_and_bucket[str(k)] = by_bucket

    phase0_gate = _evaluate_phase0_gate(summary_by_k_and_bucket)

    return {
        "schema_version": SCHEMA_VERSION,
        "thesis": "vwap_stretch_fade",
        "from_date": from_date,
        "to_date": to_date,
        "code": code,
        "friction_points_per_round_trip": friction_points,
        "sim_params": {
            "stretch_ks": list(stretch_ks),
            "reset_z": reset_z,
            "cooldown_sec": cooldown_sec,
            "hard_stop_atr_k": hard_stop_atr_k,
            "tp_atr_k": tp_atr_k,
            "max_hold_sec": 180,
            "horizon_seconds": horizon_seconds,
            "vwap_window_min": vwap_window_min,
            "atr_method": "sma_tr_period_20",
        },
        "phase0_gate": phase0_gate,
        "summary_by_k": summary_by_k,
        "summary_by_k_and_bucket": summary_by_k_and_bucket,
        "summary_by_direction": {
            str(k): _group_summary(all_by_k[k], "direction") for k in stretch_ks
        },
        "entry_count_by_k": {str(k): len(all_by_k[k]) for k in stretch_ks},
        "entries": {str(k): all_by_k[k] for k in stretch_ks},
    }
