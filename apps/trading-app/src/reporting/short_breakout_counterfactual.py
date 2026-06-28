"""FT-008 Phase 0: 1m short-term breakout continuation counterfactual."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from reporting.armed_forward_counterfactual import (
    FRICTION_POINTS,
    _summarize_gross_net,
    simulate_atr_barrier_exit,
)
from reporting.forward_pnl import ForwardPnlPolicy, make_replay_forward_pnl
from reporting.impulse_absorption_counterfactual import simulate_scalp_exit
from reporting.volatility_baseline import DEFAULT_ATR_PERIOD, atr_series_from_bars
from reporting.vwap_stretch_fade_counterfactual import session_bucket_for_ts
from storage.kbar_loader import KBarRecord, load_kbars_csv, resolve_kbar_path
from storage.tick_loader import iter_replay_ticks, resolve_cli_tick_cache_dates

SCHEMA_VERSION = 1
SESSION_START = dt.time(8, 45)
SESSION_END = dt.time(13, 45)

DEFAULT_LOOKBACK_BARS = (5, 10, 15)
DEFAULT_BREAKOUT_ATR_KS = (0.0, 0.1)
DEFAULT_VOL_PCT = 70.0
DEFAULT_MIN_RANGE_ATR_K = 0.5
DEFAULT_SKIP_OPEN_MIN = 10
DEFAULT_COOLDOWN_SEC = 120
DEFAULT_MIN_ATR = 25.0
DEFAULT_SL_POINTS = 8.0
DEFAULT_TP_POINTS = 12.0
DEFAULT_SCALP_MAX_HOLD_SEC = 120

PHASE0_GROSS_MIN = 5.0
PHASE0_NET_MIN = 0.0
PHASE0_MIN_N = 30

BreakoutDir = Literal["Long", "Short"]


@dataclass(frozen=True)
class BreakoutSignal:
    day: dt.date
    bar_idx: int
    direction: BreakoutDir
    entry_ts: int
    entry_price: float
    atr: float
    prior_high: float
    prior_low: float
    bar_volume: int
    bar_range: float
    session_bucket: str
    lookback_bars: int
    breakout_atr_k: float


def _session_bars(bars: list[KBarRecord]) -> list[KBarRecord]:
    return [b for b in bars if SESSION_START <= b.ts.time() <= SESSION_END]


def _skip_open_cutoff(skip_open_min: int) -> dt.time:
    base = dt.datetime.combine(dt.date(2000, 1, 1), SESSION_START)
    return (base + dt.timedelta(minutes=skip_open_min)).time()


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100.0) * (len(ordered) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    frac = rank - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def _atr_at_bar_index(bars: list[KBarRecord], idx: int, *, period: int = DEFAULT_ATR_PERIOD) -> float:
    tuples = [
        (b.High, b.Low, b.Close, b.High - b.Low, float(b.Volume)) for b in bars[: idx + 1]
    ]
    atrs = atr_series_from_bars(tuples, period=period)
    if not atrs:
        return DEFAULT_MIN_ATR
    return max(float(atrs[-1]), DEFAULT_MIN_ATR)


def _bar_range(bar: KBarRecord) -> float:
    return max(0.0, float(bar.High - bar.Low))


def _prior_extremes(bars: list[KBarRecord], idx: int, lookback: int) -> tuple[float, float] | None:
    start = idx - lookback
    if start < 0:
        return None
    window = bars[start:idx]
    if not window:
        return None
    return max(float(b.High) for b in window), min(float(b.Low) for b in window)


def detect_breakout_signal(
    bars: list[KBarRecord],
    idx: int,
    *,
    lookback_bars: int,
    breakout_atr_k: float,
    vol_p70: float,
    min_range_atr_k: float,
    skip_open_until: dt.time,
    close_1h_only: bool = False,
) -> BreakoutSignal | None:
    bar = bars[idx]
    if bar.ts.time() < skip_open_until:
        return None

    extremes = _prior_extremes(bars, idx, lookback_bars)
    if extremes is None:
        return None
    prior_high, prior_low = extremes
    atr = _atr_at_bar_index(bars, idx)
    bar_range = _bar_range(bar)
    close = float(bar.Close)

    if float(bar.Volume) < vol_p70:
        return None
    if bar_range < min_range_atr_k * atr:
        return None

    threshold = breakout_atr_k * atr
    direction: BreakoutDir | None = None
    if close > prior_high + threshold:
        direction = "Long"
    elif close < prior_low - threshold:
        direction = "Short"
    if direction is None:
        return None

    entry_ts = int(bar.ts.timestamp()) + 60
    bucket = session_bucket_for_ts(entry_ts)
    if close_1h_only and bucket != "close_1h":
        return None

    return BreakoutSignal(
        day=bar.ts.date(),
        bar_idx=idx,
        direction=direction,
        entry_ts=entry_ts,
        entry_price=close,
        atr=atr,
        prior_high=round(prior_high, 1),
        prior_low=round(prior_low, 1),
        bar_volume=int(bar.Volume),
        bar_range=round(bar_range, 2),
        session_bucket=bucket,
        lookback_bars=lookback_bars,
        breakout_atr_k=breakout_atr_k,
    )


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


def simulate_breakout_entry(
    signal: BreakoutSignal,
    ticks: list[tuple[int, float, int, int]],
    *,
    hard_stop_atr_k: float = 0.75,
    tp_atr_k: float = 2.0,
    sl_points: float = DEFAULT_SL_POINTS,
    tp_points: float = DEFAULT_TP_POINTS,
    scalp_max_hold_sec: int = DEFAULT_SCALP_MAX_HOLD_SEC,
    friction_points: float = FRICTION_POINTS,
    forward_fn: Any | None = None,
) -> dict[str, Any]:
    atr_sim = simulate_atr_barrier_exit(
        direction=signal.direction,
        entry_price=signal.entry_price,
        armed_ts=signal.entry_ts,
        atr=signal.atr,
        ticks=ticks,
        hard_stop_atr_k=hard_stop_atr_k,
        tp_atr_k=tp_atr_k,
    )
    scalp_sim = simulate_scalp_exit(
        direction=signal.direction,
        entry_price=signal.entry_price,
        entry_ts=signal.entry_ts,
        ticks=ticks,
        tp_points=tp_points,
        sl_points=sl_points,
        max_hold_sec=scalp_max_hold_sec,
    )
    gross_atr = float(atr_sim["gross_pnl"])
    net_atr = gross_atr - friction_points
    gross_scalp = float(scalp_sim["gross_pnl"])
    net_scalp = gross_scalp - friction_points
    gross_horizon = 0.0
    net_horizon = 0.0
    if forward_fn is not None:
        audit_dir = "Buy" if signal.direction == "Long" else "Sell"
        gross_horizon = float(forward_fn(signal.entry_price, signal.entry_ts, audit_dir))
        net_horizon = gross_horizon - friction_points

    return {
        "day": signal.day.isoformat(),
        "ts": signal.entry_ts,
        "lookback_bars": signal.lookback_bars,
        "breakout_atr_k": signal.breakout_atr_k,
        "direction": signal.direction,
        "entry_price": signal.entry_price,
        "atr": round(signal.atr, 2),
        "prior_high": signal.prior_high,
        "prior_low": signal.prior_low,
        "bar_volume": signal.bar_volume,
        "bar_range": signal.bar_range,
        "session_bucket": signal.session_bucket,
        "gross_atr_sim": gross_atr,
        "net_atr_sim": net_atr,
        "gross_scalp": gross_scalp,
        "net_scalp": net_scalp,
        "gross_horizon": gross_horizon,
        "net_horizon": net_horizon,
        "atr_barrier_sim": atr_sim,
        "scalp_sim": scalp_sim,
    }


def detect_breakout_entries_for_day(
    code: str,
    day: dt.date,
    *,
    cache_dir: Path,
    lookback_bars: int,
    breakout_atr_k: float,
    vol_pct: float = DEFAULT_VOL_PCT,
    min_range_atr_k: float = DEFAULT_MIN_RANGE_ATR_K,
    skip_open_min: int = DEFAULT_SKIP_OPEN_MIN,
    cooldown_sec: int = DEFAULT_COOLDOWN_SEC,
    hard_stop_atr_k: float = 0.75,
    tp_atr_k: float = 2.0,
    sl_points: float = DEFAULT_SL_POINTS,
    tp_points: float = DEFAULT_TP_POINTS,
    scalp_max_hold_sec: int = DEFAULT_SCALP_MAX_HOLD_SEC,
    friction_points: float = FRICTION_POINTS,
    forward_fn: Any | None = None,
    close_1h_only: bool = False,
) -> list[dict[str, Any]]:
    kpath = resolve_kbar_path(cache_dir, code, day)
    if kpath is None:
        return []
    bars = _session_bars(load_kbars_csv(kpath))
    if len(bars) < lookback_bars + 1:
        return []

    vols = [float(b.Volume) for b in bars]
    vol_p70 = _percentile(vols, vol_pct)
    skip_open_until = _skip_open_cutoff(skip_open_min)
    ticks = _tick_rows_for_day(code, day, cache_dir=cache_dir)

    rows: list[dict[str, Any]] = []
    last_entry_ts: int | None = None
    for idx in range(lookback_bars, len(bars)):
        signal = detect_breakout_signal(
            bars,
            idx,
            lookback_bars=lookback_bars,
            breakout_atr_k=breakout_atr_k,
            vol_p70=vol_p70,
            min_range_atr_k=min_range_atr_k,
            skip_open_until=skip_open_until,
            close_1h_only=close_1h_only,
        )
        if signal is None:
            continue
        if last_entry_ts is not None and signal.entry_ts - last_entry_ts < cooldown_sec:
            continue
        rows.append(
            simulate_breakout_entry(
                signal,
                ticks,
                hard_stop_atr_k=hard_stop_atr_k,
                tp_atr_k=tp_atr_k,
                sl_points=sl_points,
                tp_points=tp_points,
                scalp_max_hold_sec=scalp_max_hold_sec,
                friction_points=friction_points,
                forward_fn=forward_fn,
            )
        )
        last_entry_ts = signal.entry_ts

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
            "fixed_scalp_120s": _summary_block(sub, "gross_scalp", "net_scalp"),
            "horizon_1800s": _summary_block(sub, "gross_horizon", "net_horizon"),
        }
        for g, sub in sorted(groups.items())
    }


def _param_key(lookback: int, breakout_k: float) -> str:
    return f"lb{lookback}_bk{breakout_k:g}"


def _evaluate_phase0_gate(
    summary_by_param_and_bucket: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    best: dict[str, Any] | None = None
    passed = False
    for param, buckets in summary_by_param_and_bucket.items():
        for bucket, metrics in buckets.items():
            if bucket == "out_of_session":
                continue
            s = metrics.get("atr_barrier_180s") or {}
            n = int(s.get("n") or 0)
            gross = s.get("gross_mean")
            net = s.get("net_mean")
            if gross is None or net is None:
                continue
            parts = param.split("_")
            lb = int(parts[0].replace("lb", ""))
            bk = float(parts[1].replace("bk", ""))
            candidate = {
                "param": param,
                "lookback_bars": lb,
                "breakout_atr_k": bk,
                "session_bucket": bucket,
                "n": n,
                "gross_mean": gross,
                "net_mean": net,
            }
            if n >= PHASE0_MIN_N and gross > PHASE0_GROSS_MIN and net > PHASE0_NET_MIN:
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


def _evaluate_phase0_gate_params(
    summary_by_param: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Gate on overall param summary (for close_1h_only where bucket is redundant)."""
    best: dict[str, Any] | None = None
    passed = False
    for param, metrics in summary_by_param.items():
        s = metrics.get("atr_barrier_180s") or {}
        n = int(s.get("n") or 0)
        gross = s.get("gross_mean")
        net = s.get("net_mean")
        if gross is None or net is None:
            continue
        parts = param.split("_")
        lb = int(parts[0].replace("lb", ""))
        bk = float(parts[1].replace("bk", ""))
        candidate = {
            "param": param,
            "lookback_bars": lb,
            "breakout_atr_k": bk,
            "session_bucket": "close_1h",
            "n": n,
            "gross_mean": gross,
            "net_mean": net,
        }
        if n >= PHASE0_MIN_N and gross > PHASE0_GROSS_MIN and net > PHASE0_NET_MIN:
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


def build_short_breakout_payload(
    *,
    code: str,
    cache_dir: Path,
    from_date: str,
    to_date: str,
    lookback_bars: tuple[int, ...] = DEFAULT_LOOKBACK_BARS,
    breakout_atr_ks: tuple[float, ...] = DEFAULT_BREAKOUT_ATR_KS,
    vol_pct: float = DEFAULT_VOL_PCT,
    min_range_atr_k: float = DEFAULT_MIN_RANGE_ATR_K,
    skip_open_min: int = DEFAULT_SKIP_OPEN_MIN,
    cooldown_sec: int = DEFAULT_COOLDOWN_SEC,
    hard_stop_atr_k: float = 0.75,
    tp_atr_k: float = 2.0,
    sl_points: float = DEFAULT_SL_POINTS,
    tp_points: float = DEFAULT_TP_POINTS,
    scalp_max_hold_sec: int = DEFAULT_SCALP_MAX_HOLD_SEC,
    friction_points: float = FRICTION_POINTS,
    horizon_seconds: int = 1800,
    close_1h_only: bool = False,
    variant: str = "v1_baseline",
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

    from reporting.forward_pnl import load_tick_series

    series = load_tick_series(code, dates, cache_dir=cache_dir)
    forward_fn = make_replay_forward_pnl(
        series,
        ForwardPnlPolicy(mode="fixed_seconds", window_seconds=horizon_seconds),
    )

    all_by_param: dict[str, list[dict[str, Any]]] = {}
    for lb in lookback_bars:
        for bk in breakout_atr_ks:
            all_by_param[_param_key(lb, bk)] = []

    for day in dates:
        for lb in lookback_bars:
            for bk in breakout_atr_ks:
                key = _param_key(lb, bk)
                all_by_param[key].extend(
                    detect_breakout_entries_for_day(
                        code,
                        day,
                        cache_dir=cache_dir,
                        lookback_bars=lb,
                        breakout_atr_k=bk,
                        vol_pct=vol_pct,
                        min_range_atr_k=min_range_atr_k,
                        skip_open_min=skip_open_min,
                        cooldown_sec=cooldown_sec,
                        hard_stop_atr_k=hard_stop_atr_k,
                        tp_atr_k=tp_atr_k,
                        sl_points=sl_points,
                        tp_points=tp_points,
                        scalp_max_hold_sec=scalp_max_hold_sec,
                        friction_points=friction_points,
                        forward_fn=forward_fn,
                        close_1h_only=close_1h_only,
                    )
                )

    summary_by_param: dict[str, Any] = {}
    summary_by_param_and_bucket: dict[str, dict[str, Any]] = {}
    for key, rows in all_by_param.items():
        summary_by_param[key] = {
            "atr_barrier_180s": _summary_block(rows, "gross_atr_sim", "net_atr_sim"),
            "fixed_scalp_120s": _summary_block(rows, "gross_scalp", "net_scalp"),
            "horizon_1800s": _summary_block(rows, "gross_horizon", "net_horizon"),
        }
        summary_by_param_and_bucket[key] = _group_summary(rows, "session_bucket")

    if close_1h_only:
        phase0_gate = _evaluate_phase0_gate_params(summary_by_param)
    else:
        phase0_gate = _evaluate_phase0_gate(summary_by_param_and_bucket)

    return {
        "schema_version": SCHEMA_VERSION,
        "thesis": "short_breakout",
        "variant": variant,
        "from_date": from_date,
        "to_date": to_date,
        "code": code,
        "friction_points_per_round_trip": friction_points,
        "sim_params": {
            "lookback_bars": list(lookback_bars),
            "breakout_atr_ks": list(breakout_atr_ks),
            "vol_pct": vol_pct,
            "min_range_atr_k": min_range_atr_k,
            "skip_open_min": skip_open_min,
            "cooldown_sec": cooldown_sec,
            "hard_stop_atr_k": hard_stop_atr_k,
            "tp_atr_k": tp_atr_k,
            "max_hold_sec": 180,
            "sl_points": sl_points,
            "tp_points": tp_points,
            "scalp_max_hold_sec": scalp_max_hold_sec,
            "horizon_seconds": horizon_seconds,
            "close_1h_only": close_1h_only,
            "atr_method": "sma_tr_period_20",
        },
        "phase0_gate": phase0_gate,
        "summary_by_param": summary_by_param,
        "summary_by_param_and_bucket": summary_by_param_and_bucket,
        "summary_by_direction": {
            k: _group_summary(v, "direction") for k, v in all_by_param.items()
        },
        "entry_count_by_param": {k: len(v) for k, v in all_by_param.items()},
        "entries": all_by_param,
        "ft004_baseline_reference": {
            "note": "FT-004 armed-forward valid 2026-04 gross_mean ~1.89/趟 (No-Go G1)",
            "gross_mean_per_trade": 1.89,
        },
    }
