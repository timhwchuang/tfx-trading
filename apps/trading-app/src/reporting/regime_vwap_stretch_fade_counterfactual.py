"""FT-012 Phase 0: Regime-conditioned VWAP stretch fade counterfactual."""

from __future__ import annotations

import bisect
import datetime as dt
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from reporting.armed_forward_counterfactual import (
    FRICTION_POINTS,
    _summarize_gross_net,
    simulate_atr_barrier_exit,
)
from reporting.forward_pnl import ForwardPnlPolicy, make_replay_forward_pnl
from reporting.short_breakout_counterfactual import _session_bars
from reporting.volatility_baseline import atr_series_from_bars
from reporting.vwap_stretch_fade_counterfactual import (
    DEFAULT_COOLDOWN_SEC,
    DEFAULT_RESET_Z,
    DEFAULT_VWAP_WINDOW_MIN,
    PHASE0_GROSS_MIN,
    PHASE0_MIN_N,
    PHASE0_NET_MIN,
    SESSION_END,
    SESSION_START,
    _atr_at_ts,
    _bar_atr_lookup,
    _tick_rows_for_day,
    audit_direction,
    fade_direction,
)
from storage.kbar_loader import KBarRecord, load_kbars_csv, resolve_kbar_path
from storage.tick_loader import iter_replay_ticks, resolve_cli_tick_cache_dates
from trading_engine.indicators import IndicatorState

SCHEMA_VERSION = 1
EXIT_VARIANT = "atr_barrier_180s"

DEFAULT_STRETCH_KS = (2.0, 2.5, 3.0)
DEFAULT_VOL_PCT_MAXS = (25, 30, 35)
DEFAULT_RV_WINDOW_BARS = 30
DEFAULT_REGIME_LOOKBACK_DAYS = 20
DEFAULT_MIN_REGIME_SAMPLES = 5
DEFAULT_MIN_ATR_RAW = 0.01

MORNING_START = dt.time(9, 0)
MORNING_END = dt.time(10, 30)


@dataclass(frozen=True)
class RegimeTickSnapshot:
    ts: int
    price: float
    vwap: float
    atr: float
    z: float
    in_morning_window: bool
    regime_pct: float | None
    bar_time: dt.time | None


def morning_fade_window_for_ts(ts: int) -> bool:
    t = dt.datetime.fromtimestamp(ts).time()
    if t < SESSION_START or t > SESSION_END:
        return False
    return MORNING_START <= t < MORNING_END


def _param_key(stretch_k: float, vol_pct_max: int) -> str:
    sk = f"{stretch_k:g}".replace(".", "p")
    return f"k{sk}_p{vol_pct_max}"


def compute_rv_recent_at_bar(bars: list[KBarRecord], idx: int, *, window: int = DEFAULT_RV_WINDOW_BARS) -> float | None:
    """RV from the last `window` **completed** bars strictly before bar `idx`."""
    if idx < window:
        return None
    closes = [float(bars[i].Close) for i in range(idx - window, idx)]
    if any(c <= 0 for c in closes):
        return None
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    if len(rets) < 2:
        return None
    return float(statistics.pstdev(rets))


def build_day_rv_by_bar_time(
    bars: list[KBarRecord],
    *,
    window: int = DEFAULT_RV_WINDOW_BARS,
) -> dict[dt.time, float]:
    """Map bar clock time -> RV known at the **start** of that bar (no lookahead)."""
    out: dict[dt.time, float] = {}
    for idx in range(window, len(bars)):
        rv = compute_rv_recent_at_bar(bars, idx, window=window)
        if rv is not None:
            out[bars[idx].ts.time()] = rv
    return out


def build_rv_index_for_dates(
    code: str,
    dates: list[dt.date],
    *,
    cache_dir: Path,
    window: int = DEFAULT_RV_WINDOW_BARS,
) -> dict[dt.date, dict[dt.time, float]]:
    index: dict[dt.date, dict[dt.time, float]] = {}
    for day in dates:
        kpath = resolve_kbar_path(cache_dir, code, day)
        if kpath is None:
            continue
        bars = _session_bars(load_kbars_csv(kpath))
        if len(bars) < window + 2:
            continue
        index[day] = build_day_rv_by_bar_time(bars, window=window)
    return index


def regime_pct_at_bar_time(
    rv_today: float,
    bar_time: dt.time,
    prior_days: list[dt.date],
    rv_index: dict[dt.date, dict[dt.time, float]],
) -> float | None:
    historical: list[float] = []
    for day in prior_days:
        day_map = rv_index.get(day) or {}
        val = day_map.get(bar_time)
        if val is not None:
            historical.append(val)
    if len(historical) < DEFAULT_MIN_REGIME_SAMPLES:
        return None
    count_le = sum(1 for h in historical if h <= rv_today)
    return 100.0 * count_le / len(historical)


def _bar_time_for_ts(ts: int) -> dt.time:
    return dt.datetime.fromtimestamp(ts).replace(second=0, microsecond=0).time()


def build_regime_day_snapshots(
    code: str,
    day: dt.date,
    *,
    cache_dir: Path,
    prior_days: list[dt.date],
    rv_index: dict[dt.date, dict[dt.time, float]],
    vwap_window_min: int = DEFAULT_VWAP_WINDOW_MIN,
    min_atr: float = DEFAULT_MIN_ATR_RAW,
) -> list[RegimeTickSnapshot]:
    kpath = resolve_kbar_path(cache_dir, code, day)
    today_rv = rv_index.get(day) or {}
    atr_lookup = _bar_atr_lookup(kpath) if kpath is not None else []
    ind = IndicatorState(vwap_window_min=vwap_window_min)
    snaps: list[RegimeTickSnapshot] = []

    for tick in iter_replay_ticks(code, [day], cache_dir=cache_dir):
        ts = int(tick.datetime.timestamp())
        price = float(tick.close)
        volume = int(tick.volume)
        tick_type = int(tick.tick_type)
        ind.update_vwap(ts, price, volume)
        ind.update_momentum(ts, volume, tick_type)
        vwap = ind.current_vwap
        raw_atr = _atr_at_ts(atr_lookup, ts, 0.0)
        atr = raw_atr if raw_atr > min_atr else min_atr
        z = (price - vwap) / atr if atr > 0 else 0.0
        in_morning = morning_fade_window_for_ts(ts)
        bar_time = _bar_time_for_ts(ts)
        rv_val = today_rv.get(bar_time)
        regime_pct = None
        if rv_val is not None and prior_days:
            regime_pct = regime_pct_at_bar_time(rv_val, bar_time, prior_days, rv_index)
        snaps.append(
            RegimeTickSnapshot(
                ts=ts,
                price=price,
                vwap=vwap,
                atr=atr,
                z=z,
                in_morning_window=in_morning,
                regime_pct=regime_pct,
                bar_time=bar_time,
            )
        )
    return snaps


def regime_ok(regime_pct: float | None, vol_pct_max: int) -> bool:
    return regime_pct is not None and regime_pct <= float(vol_pct_max)


def simulate_regime_stretch_fade_entries(
    snapshots: list[RegimeTickSnapshot],
    ticks: list[tuple[int, float, int, int]],
    *,
    stretch_k: float,
    vol_pct_max: int,
    reset_z: float = DEFAULT_RESET_Z,
    cooldown_sec: int = DEFAULT_COOLDOWN_SEC,
    hard_stop_atr_k: float = 0.75,
    tp_atr_k: float = 2.0,
    friction_points: float = FRICTION_POINTS,
    forward_fn: Any | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    can_arm = True
    last_entry_ts: int | None = None

    for snap in snapshots:
        if not snap.in_morning_window:
            continue
        if not can_arm and abs(snap.z) <= reset_z:
            can_arm = True
        if last_entry_ts is not None and snap.ts - last_entry_ts < cooldown_sec:
            continue
        if not can_arm or abs(snap.z) < stretch_k:
            continue
        if not regime_ok(snap.regime_pct, vol_pct_max):
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
                "vol_pct_max": vol_pct_max,
                "direction": direction,
                "entry_price": snap.price,
                "vwap": round(snap.vwap, 2),
                "atr": round(snap.atr, 2),
                "z": round(snap.z, 4),
                "regime_pct": snap.regime_pct,
                "bar_time": snap.bar_time.isoformat() if snap.bar_time else None,
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


def simulate_morning_vsf_entries(
    snapshots: list[RegimeTickSnapshot],
    ticks: list[tuple[int, float, int, int]],
    *,
    stretch_k: float = 2.0,
    reset_z: float = DEFAULT_RESET_Z,
    cooldown_sec: int = DEFAULT_COOLDOWN_SEC,
    hard_stop_atr_k: float = 0.75,
    tp_atr_k: float = 2.0,
    friction_points: float = FRICTION_POINTS,
) -> list[dict[str, Any]]:
    """Morning window only, no regime filter — VSF delta baseline."""
    rows: list[dict[str, Any]] = []
    can_arm = True
    last_entry_ts: int | None = None

    for snap in snapshots:
        if not snap.in_morning_window:
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
        rows.append(
            {
                "direction": direction,
                "gross_atr_sim": gross_barrier,
                "net_atr_sim": gross_barrier - friction_points,
                "atr_barrier_sim": sim,
            }
        )
        can_arm = False
        last_entry_ts = snap.ts
    return rows


def _count_funnel_day(
    snapshots: list[RegimeTickSnapshot],
    *,
    stretch_k: float,
    vol_pct_max: int,
) -> dict[str, int]:
    counts = {
        "days": 1,
        "in_morning_window": 0,
        "regime_ok": 0,
        "stretch_ok": 0,
        "entry": 0,
    }
    had_window = False
    had_regime = False
    had_stretch = False
    had_entry = False

    can_arm = True
    last_entry_ts: int | None = None
    for snap in snapshots:
        if snap.in_morning_window:
            had_window = True
        if snap.in_morning_window and regime_ok(snap.regime_pct, vol_pct_max):
            had_regime = True
        if (
            snap.in_morning_window
            and regime_ok(snap.regime_pct, vol_pct_max)
            and abs(snap.z) >= stretch_k
        ):
            had_stretch = True

        if not snap.in_morning_window:
            continue
        if not can_arm and abs(snap.z) <= DEFAULT_RESET_Z:
            can_arm = True
        if last_entry_ts is not None and snap.ts - last_entry_ts < DEFAULT_COOLDOWN_SEC:
            continue
        if (
            can_arm
            and abs(snap.z) >= stretch_k
            and regime_ok(snap.regime_pct, vol_pct_max)
        ):
            had_entry = True
            can_arm = False
            last_entry_ts = snap.ts

    if had_window:
        counts["in_morning_window"] = 1
    if had_regime:
        counts["regime_ok"] = 1
    if had_stretch:
        counts["stretch_ok"] = 1
    if had_entry:
        counts["entry"] = 1
    return counts


def _summary_block(rows: list[dict[str, Any]], gross_key: str, net_key: str) -> dict[str, Any]:
    out = _summarize_gross_net(gross_key, net_key, rows)
    if rows:
        out["quick_stop_loss_rate"] = round(
            sum(1 for r in rows if (r.get("atr_barrier_sim") or {}).get("quick_stop")) / len(rows),
            4,
        )
    return out


def _group_summary(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row[key]), []).append(row)
    return {
        g: {EXIT_VARIANT: _summary_block(sub, "gross_atr_sim", "net_atr_sim")}
        for g, sub in sorted(groups.items())
    }


def _monthly_net_means(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    by_month: dict[str, list[float]] = {}
    for row in rows:
        ts = int(row["ts"])
        day = dt.datetime.fromtimestamp(ts).date()
        key = f"{day.year}-{day.month:02d}"
        by_month.setdefault(key, []).append(float(row["net_atr_sim"]))
    return {m: round(statistics.mean(v), 4) if v else None for m, v in sorted(by_month.items())}


def _champion_disqualify(rows: list[dict[str, Any]], summary: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    gross_median = summary.get("gross_median")
    if gross_median is not None and gross_median <= -5:
        flags.append("gross_median_le_neg5")
    if not rows:
        return flags
    gross_total = sum(float(r["gross_atr_sim"]) for r in rows)
    by_dir_gross: dict[str, float] = {}
    by_dir_net: dict[str, list[float]] = {}
    for row in rows:
        d = str(row.get("direction", "Long"))
        by_dir_gross[d] = by_dir_gross.get(d, 0.0) + float(row["gross_atr_sim"])
        by_dir_net.setdefault(d, []).append(float(row["net_atr_sim"]))
    if gross_total > 0:
        for d, g in by_dir_gross.items():
            if g / gross_total > 0.8:
                flags.append(f"{d}_gross_share_gt_80pct")
    for direction, nets in by_dir_net.items():
        if nets and statistics.mean(nets) < -3:
            flags.append(f"{direction}_net_mean_lt_neg3")
    return flags


def _evaluate_phase0_gate(
    summary_by_param: dict[str, dict[str, Any]],
    rows_by_param: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    best: dict[str, Any] | None = None
    passed = False
    candidates: list[dict[str, Any]] = []
    for param, metrics in summary_by_param.items():
        s = metrics.get(EXIT_VARIANT) or {}
        n = int(s.get("n") or 0)
        gross = s.get("gross_mean")
        net = s.get("net_mean")
        if gross is None or net is None:
            continue
        rows = rows_by_param.get(param) or []
        disqualify = _champion_disqualify(rows, s)
        monthly = _monthly_net_means(rows)
        unstable_months = [m for m, v in monthly.items() if v is not None and v < -2]
        candidate = {
            "param": param,
            "n": n,
            "gross_mean": gross,
            "net_mean": net,
            "gross_median": s.get("gross_median"),
            "disqualify": disqualify,
            "unstable_months": unstable_months,
        }
        candidates.append(candidate)
        gate_ok = (
            n >= PHASE0_MIN_N
            and gross > PHASE0_GROSS_MIN
            and net > PHASE0_NET_MIN
            and not disqualify
        )
        if gate_ok:
            passed = True
            if best is None or net > best.get("net_mean", -1e9) or (
                net == best.get("net_mean") and n > best.get("n", 0)
            ):
                best = candidate
    return {
        "pass": passed,
        "gross_mean_min": PHASE0_GROSS_MIN,
        "net_mean_min": PHASE0_NET_MIN,
        "min_n": PHASE0_MIN_N,
        "best_passing": best,
        "candidates": candidates,
    }


def _prior_trading_days(sorted_dates: list[dt.date], day: dt.date, lookback: int) -> list[dt.date]:
    idx = bisect.bisect_left(sorted_dates, day)
    return sorted_dates[max(0, idx - lookback) : idx]


def build_regime_vwap_stretch_fade_payload(
    *,
    code: str,
    cache_dir: Path,
    from_date: str,
    to_date: str,
    stretch_ks: tuple[float, ...] = DEFAULT_STRETCH_KS,
    vol_pct_maxs: tuple[int, ...] = DEFAULT_VOL_PCT_MAXS,
    reset_z: float = DEFAULT_RESET_Z,
    cooldown_sec: int = DEFAULT_COOLDOWN_SEC,
    hard_stop_atr_k: float = 0.75,
    tp_atr_k: float = 2.0,
    friction_points: float = FRICTION_POINTS,
    horizon_seconds: int = 1800,
    vwap_window_min: int = DEFAULT_VWAP_WINDOW_MIN,
    regime_lookback_days: int = DEFAULT_REGIME_LOOKBACK_DAYS,
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

    sorted_dates = sorted(dates)
    hist_start = (sorted_dates[0] - dt.timedelta(days=regime_lookback_days * 2)).isoformat()
    hist_dates = resolve_cli_tick_cache_dates(
        explicit=None,
        from_cache=True,
        code=code,
        cache_dir=cache_dir,
        from_date=hist_start,
        to_date=to_date,
    )
    hist_sorted = sorted(hist_dates) if hist_dates else sorted_dates
    rv_index = build_rv_index_for_dates(code, hist_sorted, cache_dir=cache_dir)

    from reporting.forward_pnl import load_tick_series

    series = load_tick_series(code, sorted_dates, cache_dir=cache_dir)
    forward_fn = make_replay_forward_pnl(
        series,
        ForwardPnlPolicy(mode="fixed_seconds", window_seconds=horizon_seconds),
    )

    params = [(k, p) for k in stretch_ks for p in vol_pct_maxs]
    all_by_param: dict[str, list[dict[str, Any]]] = {_param_key(k, p): [] for k, p in params}
    funnel_by_param: dict[str, dict[str, int]] = {
        _param_key(k, p): {
            "days": 0,
            "in_morning_window": 0,
            "regime_ok": 0,
            "stretch_ok": 0,
            "entry": 0,
        }
        for k, p in params
    }

    for day in sorted_dates:
        prior = _prior_trading_days(hist_sorted, day, regime_lookback_days)
        snaps = build_regime_day_snapshots(
            code,
            day,
            cache_dir=cache_dir,
            prior_days=prior,
            rv_index=rv_index,
            vwap_window_min=vwap_window_min,
        )
        if not snaps:
            continue
        day_ticks = _tick_rows_for_day(code, day, cache_dir=cache_dir)
        for stretch_k, vol_pct_max in params:
            pkey = _param_key(stretch_k, vol_pct_max)
            funnel = _count_funnel_day(snaps, stretch_k=stretch_k, vol_pct_max=vol_pct_max)
            for fk, fv in funnel.items():
                funnel_by_param[pkey][fk] += fv
            rows = simulate_regime_stretch_fade_entries(
                snaps,
                day_ticks,
                stretch_k=stretch_k,
                vol_pct_max=vol_pct_max,
                reset_z=reset_z,
                cooldown_sec=cooldown_sec,
                hard_stop_atr_k=hard_stop_atr_k,
                tp_atr_k=tp_atr_k,
                friction_points=friction_points,
                forward_fn=forward_fn,
            )
            for row in rows:
                row["day"] = day.isoformat()
            all_by_param[pkey].extend(rows)

    summary_by_param: dict[str, dict[str, Any]] = {}
    for pkey, rows in all_by_param.items():
        summary_by_param[pkey] = {
            EXIT_VARIANT: _summary_block(rows, "gross_atr_sim", "net_atr_sim"),
        }

    funnel_out: dict[str, Any] = {}
    for pkey, totals in funnel_by_param.items():
        days = totals.get("days") or 1
        rates = {
            f"{k}_rate": round(totals[k] / days, 4) if days else 0.0
            for k in ("in_morning_window", "regime_ok", "stretch_ok", "entry")
        }
        funnel_out[pkey] = {**totals, **rates}

    return {
        "schema_version": SCHEMA_VERSION,
        "thesis": "regime_vwap_stretch_fade",
        "from_date": from_date,
        "to_date": to_date,
        "code": code,
        "friction_points_per_round_trip": friction_points,
        "sim_params": {
            "stretch_ks": list(stretch_ks),
            "vol_pct_maxs": list(vol_pct_maxs),
            "morning_window": "09:00-10:30",
            "rv_window_bars": DEFAULT_RV_WINDOW_BARS,
            "regime_lookback_days": regime_lookback_days,
            "min_regime_samples": DEFAULT_MIN_REGIME_SAMPLES,
            "reset_z": reset_z,
            "cooldown_sec": cooldown_sec,
            "hard_stop_atr_k": hard_stop_atr_k,
            "tp_atr_k": tp_atr_k,
            "max_hold_sec": 180,
            "horizon_seconds": horizon_seconds,
            "vwap_window_min": vwap_window_min,
            "atr_method": "sma_tr_period_20_raw",
        },
        "variant": EXIT_VARIANT,
        "phase0_gate": _evaluate_phase0_gate(summary_by_param, all_by_param),
        "summary_by_param": summary_by_param,
        "summary_by_direction": {
            p: _group_summary(rows, "direction") for p, rows in all_by_param.items()
        },
        "entry_count_by_param": {p: len(rows) for p, rows in all_by_param.items()},
        "funnel_by_param": funnel_out,
        "rows_by_param": all_by_param,
    }


def build_vsf_delta(
    *,
    code: str,
    cache_dir: Path,
    from_date: str,
    to_date: str,
    stretch_k: float = 2.0,
    regime_lookback_days: int = DEFAULT_REGIME_LOOKBACK_DAYS,
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

    sorted_dates = sorted(dates)
    hist_start = (sorted_dates[0] - dt.timedelta(days=regime_lookback_days * 2)).isoformat()
    hist_dates = resolve_cli_tick_cache_dates(
        explicit=None,
        from_cache=True,
        code=code,
        cache_dir=cache_dir,
        from_date=hist_start,
        to_date=to_date,
    )
    hist_sorted = sorted(hist_dates) if hist_dates else sorted_dates
    rv_index = build_rv_index_for_dates(code, hist_sorted, cache_dir=cache_dir)

    vsf_morning_rows: list[dict[str, Any]] = []

    for day in sorted_dates:
        prior = _prior_trading_days(hist_sorted, day, regime_lookback_days)
        snaps = build_regime_day_snapshots(
            code,
            day,
            cache_dir=cache_dir,
            prior_days=prior,
            rv_index=rv_index,
        )
        if not snaps:
            continue
        day_ticks = _tick_rows_for_day(code, day, cache_dir=cache_dir)
        vsf_morning_rows.extend(
            simulate_morning_vsf_entries(snaps, day_ticks, stretch_k=stretch_k)
        )

    vsf_summary = _summary_block(vsf_morning_rows, "gross_atr_sim", "net_atr_sim")

    return {
        "from_date": from_date,
        "to_date": to_date,
        "vsf_morning": {
            "stretch_k": stretch_k,
            "window": "09:00-10:30",
            "regime_filter": False,
            "summary": vsf_summary,
            "n": len(vsf_morning_rows),
            "net_total": round(sum(r["net_atr_sim"] for r in vsf_morning_rows), 2),
        },
        "note": "Compare RVSF champion in gate_report vs vsf_morning (same window, no regime)",
    }


def build_vsf_delta_with_rvsf(
    train_payload: dict[str, Any],
    *,
    code: str,
    cache_dir: Path,
    from_date: str,
    to_date: str,
    stretch_k: float = 2.0,
) -> dict[str, Any]:
    base = build_vsf_delta(
        code=code,
        cache_dir=cache_dir,
        from_date=from_date,
        to_date=to_date,
        stretch_k=stretch_k,
    )
    best = (train_payload.get("phase0_gate") or {}).get("best_passing")
    rvsf_n = 0
    rvsf_net_total = 0.0
    if best:
        param = best["param"]
        rows = (train_payload.get("rows_by_param") or {}).get(param) or []
        rvsf_n = len(rows)
        rvsf_net_total = round(sum(float(r["net_atr_sim"]) for r in rows), 2)
    base["rvsf_best"] = {
        "param": best.get("param") if best else None,
        "n": rvsf_n,
        "net_total": rvsf_net_total,
        "net_mean": best.get("net_mean") if best else None,
    }
    vsf_net = base["vsf_morning"]["net_total"]
    base["delta"] = {
        "net_delta_rvsf_minus_vsf_morning": round(rvsf_net_total - vsf_net, 2),
        "rvsf_pass_rate_of_vsf": round(rvsf_n / base["vsf_morning"]["n"], 4)
        if base["vsf_morning"]["n"]
        else None,
    }
    return base
