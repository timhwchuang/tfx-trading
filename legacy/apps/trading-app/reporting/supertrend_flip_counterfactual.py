"""FT-013 Phase 0: SuperTrend flip continuation (long-only) counterfactual."""

from __future__ import annotations

import datetime as dt
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from reporting.armed_forward_counterfactual import (
    FRICTION_POINTS,
    _summarize_gross_net,
    simulate_atr_barrier_exit,
)
from reporting.forward_pnl import load_tick_series
from reporting.post_entry_diagnosis import (
    enrich_rows_with_forward_windows,
    summarize_post_entry_diagnosis,
)
from reporting.short_breakout_counterfactual import (
    PHASE0_GROSS_MIN,
    PHASE0_MIN_N,
    PHASE0_NET_MIN,
    _session_bars,
    _tick_rows_for_day,
)
from reporting.volatility_baseline import atr_series_from_bars
from storage.kbar_loader import KBarRecord, load_kbars_csv, resolve_kbar_path
from storage.tick_loader import resolve_cli_tick_cache_dates

SCHEMA_VERSION = 1
TIMEFRAME_MIN = 5

SESSION_START = dt.time(8, 45)
SESSION_END = dt.time(13, 45)
ENTRY_START = dt.time(9, 15)
LAST_ENTRY_BEFORE = dt.time(11, 45)
NO_NEW_ENTRY_AFTER = dt.time(12, 0)

DEFAULT_MIN_ATR = 25.0
DEFAULT_SLIPPAGE_PTS = 1.0
DEFAULT_MAX_HOLD_SEC = 180
EXIT_VARIANT = "atr_barrier_180s"

DEFAULT_ATR_PERIODS = (10, 14)
DEFAULT_ST_MULTS = (2.5, 3.0, 3.5)
DEFAULT_COOLDOWN_BARS = (3, 6)
DEFAULT_K_SL = (0.75, 1.0, 1.25)
DEFAULT_TP_ATR_K = (1.5, 2.0, 2.5)

# Frozen fingerprint (§5.0)
FINGERPRINT_ATR_PERIOD = 10
FINGERPRINT_ST_MULT = 3.0
FINGERPRINT_COOLDOWN_BARS = 6
FINGERPRINT_K_SL = 1.0
FINGERPRINT_TP_ATR_K = 2.0


@dataclass(frozen=True)
class Bar5m:
    ts: dt.datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def bucket_close(self) -> dt.datetime:
        return self.ts + dt.timedelta(minutes=TIMEFRAME_MIN)


@dataclass(frozen=True)
class StfParams:
    atr_period: int
    st_mult: float
    cooldown_bars: int
    k_sl: float
    tp_atr_k: float

    def key(self) -> str:
        sm = f"{self.st_mult:g}".replace(".", "p")
        ks = f"{self.k_sl:g}".replace(".", "p")
        tp = f"{self.tp_atr_k:g}".replace(".", "p")
        return f"ap{self.atr_period}_sm{sm}_cd{self.cooldown_bars}_ksl{ks}_tp{tp}"


@dataclass
class SuperTrendSeries:
    atr: list[float]
    final_ub: list[float]
    final_lb: list[float]
    trend: list[int]
    supertrend_line: list[float]
    flip_long: list[bool]
    flip_short: list[bool]


def _bucket_start(ts: dt.datetime, timeframe_min: int) -> dt.datetime:
    minute = (ts.minute // timeframe_min) * timeframe_min
    return ts.replace(minute=minute, second=0, microsecond=0)


def resample_1m_to_5m_closed(
    bars_1m: list[KBarRecord],
    exchange_dt: dt.datetime,
) -> list[Bar5m]:
    """Only **closed** 5m buckets (MUST-1 — no partial bar flips)."""
    if not bars_1m:
        return []

    buckets: dict[dt.datetime, list[KBarRecord]] = {}
    for bar in bars_1m:
        key = _bucket_start(bar.ts, TIMEFRAME_MIN)
        buckets.setdefault(key, []).append(bar)

    out: list[Bar5m] = []
    for key in sorted(buckets.keys()):
        bucket_close = key + dt.timedelta(minutes=TIMEFRAME_MIN)
        if bucket_close > exchange_dt:
            continue
        chunk = sorted(buckets[key], key=lambda b: b.ts)
        out.append(
            Bar5m(
                ts=key,
                open=float(chunk[0].Open),
                high=max(float(b.High) for b in chunk),
                low=min(float(b.Low) for b in chunk),
                close=float(chunk[-1].Close),
                volume=float(sum(int(b.Volume) for b in chunk)),
            )
        )
    return out


def _raw_atr_at_5m_index(
    bars: list[Bar5m],
    idx: int,
    *,
    period: int,
) -> float:
    """ORB-style slice indexing — do not hand-roll vs atr_series_from_bars length."""
    tuples = [
        (b.high, b.low, b.close, b.high - b.low, b.volume) for b in bars[: idx + 1]
    ]
    atrs = atr_series_from_bars(tuples, period=period)
    if not atrs:
        return 0.0
    return float(atrs[-1])


def compute_supertrend_v1(
    closed_bars: list[Bar5m],
    atr_period: int,
    st_mult: float,
    *,
    min_atr_pts: float = DEFAULT_MIN_ATR,
) -> SuperTrendSeries:
    """§5.1a — SMA(TR) ATR + Pine final-band ratchet; bar 0 warmup, no flips at i=0."""
    n = len(closed_bars)
    if n == 0:
        return SuperTrendSeries([], [], [], [], [], [], [])

    atr: list[float] = []
    for i in range(n):
        raw = _raw_atr_at_5m_index(closed_bars, i, period=atr_period)
        atr.append(max(raw, min_atr_pts))

    final_ub: list[float] = []
    final_lb: list[float] = []
    trend: list[int] = []
    line: list[float] = []
    flip_long: list[bool] = []
    flip_short: list[bool] = []

    for i in range(n):
        bar = closed_bars[i]
        hl2 = (bar.high + bar.low) / 2.0
        basic_ub = hl2 + st_mult * atr[i]
        basic_lb = hl2 - st_mult * atr[i]

        if i == 0:
            f_ub = basic_ub
            f_lb = basic_lb
            if bar.close > f_ub:
                tr = 1
            elif bar.close < f_lb:
                tr = -1
            else:
                tr = 1
            flip_long.append(False)
            flip_short.append(False)
        else:
            prev_close = closed_bars[i - 1].close
            if basic_ub < final_ub[i - 1] or prev_close > final_ub[i - 1]:
                f_ub = basic_ub
            else:
                f_ub = final_ub[i - 1]
            if basic_lb > final_lb[i - 1] or prev_close < final_lb[i - 1]:
                f_lb = basic_lb
            else:
                f_lb = final_lb[i - 1]

            if bar.close > final_ub[i - 1]:
                tr = 1
            elif bar.close < final_lb[i - 1]:
                tr = -1
            else:
                tr = trend[i - 1]

            flip_long.append(tr == 1 and trend[i - 1] == -1)
            flip_short.append(tr == -1 and trend[i - 1] == 1)

        final_ub.append(f_ub)
        final_lb.append(f_lb)
        trend.append(tr)
        line.append(f_lb if tr == 1 else f_ub)

    return SuperTrendSeries(
        atr=atr,
        final_ub=final_ub,
        final_lb=final_lb,
        trend=trend,
        supertrend_line=line,
        flip_long=flip_long,
        flip_short=flip_short,
    )


def _confirm_tick_allowed(ts: int) -> bool:
    """MUST-3 — boundary on **confirmation tick** exchange time (not flip bar close)."""
    t = dt.datetime.fromtimestamp(ts).time()
    if t < ENTRY_START:
        return False
    if t >= LAST_ENTRY_BEFORE:
        return False
    if t >= NO_NEW_ENTRY_AFTER:
        return False
    return True


def _flip_bar_eligible(bar: Bar5m) -> bool:
    """No flip signals before first bucket close at/after 09:15."""
    return bar.bucket_close.time() >= ENTRY_START


def find_confirm_tick_long(
    ticks: list[tuple[int, float, int, int]],
    arm_ts: int,
    st_line: float,
) -> tuple[int, float] | None:
    for ts, price, _vol, _tt in ticks:
        if ts < arm_ts:
            continue
        if price > st_line:
            return ts, price
    return None


def find_confirm_tick_short(
    ticks: list[tuple[int, float, int, int]],
    arm_ts: int,
    st_line: float,
) -> tuple[int, float] | None:
    """Short appendix — first tick with close < supertrend_line (bear → final_ub)."""
    for ts, price, _vol, _tt in ticks:
        if ts < arm_ts:
            continue
        if price < st_line:
            return ts, price
    return None


def simulate_stf_long_entry(
    *,
    day: dt.date,
    params: StfParams,
    bar_idx: int,
    flip_bar: Bar5m,
    entry_ts: int,
    entry_price: float,
    atr_effective: float,
    ticks: list[tuple[int, float, int, int]],
    slippage_pts: float = DEFAULT_SLIPPAGE_PTS,
    friction_points: float = FRICTION_POINTS,
    max_hold_sec: int = DEFAULT_MAX_HOLD_SEC,
) -> dict[str, Any]:
    entry_fill = entry_price + slippage_pts
    atr_sim = simulate_atr_barrier_exit(
        direction="Long",
        entry_price=entry_fill,
        armed_ts=entry_ts,
        atr=atr_effective,
        ticks=ticks,
        hard_stop_atr_k=params.k_sl,
        tp_atr_k=params.tp_atr_k,
        max_hold_sec=max_hold_sec,
    )
    gross = float(atr_sim["gross_pnl"])
    net = gross - friction_points
    stop_dist = params.k_sl * atr_effective
    return {
        "day": day.isoformat(),
        "param": params.key(),
        "direction": "Long",
        "bar_idx": bar_idx,
        "flip_bar_ts": int(flip_bar.ts.timestamp()),
        "entry_arm_ts": int(flip_bar.bucket_close.timestamp()),
        "ts": entry_ts,
        "entry_price": round(entry_price, 1),
        "entry_fill": round(entry_fill, 1),
        "slippage_pts": slippage_pts,
        "atr": round(atr_effective, 2),
        "atr_effective": round(atr_effective, 2),
        "k_sl": params.k_sl,
        "stop_dist_pts": round(stop_dist, 2),
        "slippage_ratio": round(slippage_pts / stop_dist, 4) if stop_dist > 0 else None,
        "gross_atr_sim": gross,
        "net_atr_sim": net,
        "atr_barrier_sim": atr_sim,
        "exit_variant": EXIT_VARIANT,
    }


def _build_short_appendix_row(
    *,
    day: dt.date,
    bar_idx: int,
    flip_bar: Bar5m,
    entry_ts: int,
    entry_price: float,
    atr_effective: float,
    st_line: float,
) -> dict[str, Any]:
    return {
        "day": day.isoformat(),
        "direction": "Short",
        "appendix_only": True,
        "bar_idx": bar_idx,
        "flip_bar_ts": int(flip_bar.ts.timestamp()),
        "entry_arm_ts": int(flip_bar.bucket_close.timestamp()),
        "ts": entry_ts,
        "entry_price": round(entry_price, 1),
        "atr": round(atr_effective, 2),
        "supertrend_line": round(st_line, 1),
        "note": "post_entry_only — no barrier PnL",
    }


def scan_stf_session(
    bars_1m: list[KBarRecord],
    ticks: list[tuple[int, float, int, int]],
    day: dt.date,
    params: StfParams,
    *,
    slippage_pts: float = DEFAULT_SLIPPAGE_PTS,
    friction_points: float = FRICTION_POINTS,
    st_override: SuperTrendSeries | None = None,
    bars_5m_override: list[Bar5m] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    """Core STF scan — testable without tick cache I/O."""
    funnel = {
        "flip_detected_long": 0,
        "cooldown_pass": 0,
        "window_pass": 0,
        "entry": 0,
        "flip_detected_short": 0,
    }
    if len(bars_1m) < 30 and bars_5m_override is None:
        return [], [], funnel

    if bars_5m_override is not None:
        bars_5m = bars_5m_override
    else:
        exchange_dt = bars_1m[-1].ts + dt.timedelta(minutes=1)
        bars_5m = resample_1m_to_5m_closed(bars_1m, exchange_dt)
    if len(bars_5m) < 3:
        return [], [], funnel

    if st_override is not None:
        st = st_override
    else:
        st = compute_supertrend_v1(
            bars_5m,
            params.atr_period,
            params.st_mult,
            min_atr_pts=DEFAULT_MIN_ATR,
        )

    long_rows: list[dict[str, Any]] = []
    short_rows: list[dict[str, Any]] = []
    last_long_entry_bar_idx = -10_000

    for i in range(1, len(bars_5m)):
        bar = bars_5m[i]
        if not _flip_bar_eligible(bar):
            continue

        arm_ts = int(bar.bucket_close.timestamp())
        st_line = st.supertrend_line[i]
        atr_eff = st.atr[i]

        if st.flip_short[i]:
            funnel["flip_detected_short"] += 1
            short_confirm = find_confirm_tick_short(ticks, arm_ts, st_line)
            if short_confirm is not None:
                s_ts, s_px = short_confirm
                short_rows.append(
                    _build_short_appendix_row(
                        day=day,
                        bar_idx=i,
                        flip_bar=bar,
                        entry_ts=s_ts,
                        entry_price=s_px,
                        atr_effective=atr_eff,
                        st_line=st_line,
                    )
                )

        if not st.flip_long[i]:
            continue

        funnel["flip_detected_long"] += 1
        if i - last_long_entry_bar_idx < params.cooldown_bars:
            continue
        funnel["cooldown_pass"] += 1

        confirm = find_confirm_tick_long(ticks, arm_ts, st_line)
        if confirm is None:
            continue
        entry_ts, entry_price = confirm
        if not _confirm_tick_allowed(entry_ts):
            continue
        funnel["window_pass"] += 1

        last_long_entry_bar_idx = i
        funnel["entry"] += 1
        row = simulate_stf_long_entry(
            day=day,
            params=params,
            bar_idx=i,
            flip_bar=bar,
            entry_ts=entry_ts,
            entry_price=entry_price,
            atr_effective=atr_eff,
            ticks=ticks,
            slippage_pts=slippage_pts,
            friction_points=friction_points,
        )
        row["supertrend_line"] = round(st_line, 1)
        long_rows.append(row)

    return long_rows, short_rows, funnel


def detect_stf_entries_for_day(
    code: str,
    day: dt.date,
    *,
    cache_dir: Path,
    params: StfParams,
    slippage_pts: float = DEFAULT_SLIPPAGE_PTS,
    friction_points: float = FRICTION_POINTS,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    kpath = resolve_kbar_path(cache_dir, code, day)
    funnel = {
        "flip_detected_long": 0,
        "cooldown_pass": 0,
        "window_pass": 0,
        "entry": 0,
        "flip_detected_short": 0,
    }
    if kpath is None:
        return [], [], funnel

    bars_1m = _session_bars(load_kbars_csv(kpath))
    ticks = _tick_rows_for_day(code, day, cache_dir=cache_dir)
    return scan_stf_session(
        bars_1m,
        ticks,
        day,
        params,
        slippage_pts=slippage_pts,
        friction_points=friction_points,
    )


def _iter_param_sets(mode: Literal["fingerprint", "grid"]) -> list[StfParams]:
    if mode == "fingerprint":
        return [
            StfParams(
                atr_period=FINGERPRINT_ATR_PERIOD,
                st_mult=FINGERPRINT_ST_MULT,
                cooldown_bars=FINGERPRINT_COOLDOWN_BARS,
                k_sl=FINGERPRINT_K_SL,
                tp_atr_k=FINGERPRINT_TP_ATR_K,
            )
        ]

    out: list[StfParams] = []
    for ap in DEFAULT_ATR_PERIODS:
        for sm in DEFAULT_ST_MULTS:
            for cd in DEFAULT_COOLDOWN_BARS:
                for ks in DEFAULT_K_SL:
                    for tp in DEFAULT_TP_ATR_K:
                        out.append(
                            StfParams(
                                atr_period=ap,
                                st_mult=sm,
                                cooldown_bars=cd,
                                k_sl=ks,
                                tp_atr_k=tp,
                            )
                        )
    return out


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 4)
    rank = (pct / 100.0) * (len(ordered) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    frac = rank - lo
    return round(ordered[lo] * (1.0 - frac) + ordered[hi] * frac, 4)


def _slippage_ratio_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ratios = [float(r["slippage_ratio"]) for r in rows if r.get("slippage_ratio") is not None]
    p50 = _percentile(ratios, 50)
    p90 = _percentile(ratios, 90)
    thin = p50 is not None and p50 > 0.15
    return {
        "slippage_pts": DEFAULT_SLIPPAGE_PTS,
        "slippage_ratio_p50": p50,
        "slippage_ratio_p90": p90,
        "execution_margin_thin": thin,
        "legacy_ref_ratio": "slippage_pts / (k_sl * atr_effective)",
        "note": "FT-013 uses entry_fill+1 before barrier; gross not directly comparable to ORB/VSF raw entry",
    }


def _aggregate_funnel(funnels: list[dict[str, int]]) -> dict[str, int]:
    keys = (
        "flip_detected_long",
        "cooldown_pass",
        "window_pass",
        "entry",
        "flip_detected_short",
    )
    return {k: sum(f.get(k, 0) for f in funnels) for k in keys}


def _flips_per_day_stats(entries_by_day: dict[str, int]) -> dict[str, Any]:
    if not entries_by_day:
        return {"p50": None, "p90": None, "days": 0}
    counts = list(entries_by_day.values())
    return {
        "p50": _percentile([float(c) for c in counts], 50),
        "p90": _percentile([float(c) for c in counts], 90),
        "days": len(counts),
    }


def _evaluate_phase0_gate_params(
    summary_by_param: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    best: dict[str, Any] | None = None
    passed = False
    for param, metrics in summary_by_param.items():
        s = metrics.get(EXIT_VARIANT) or {}
        n = int(s.get("n") or 0)
        gross = s.get("gross_mean")
        net = s.get("net_mean")
        if gross is None or net is None:
            continue
        candidate = {
            "param": param,
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


def _evaluate_fingerprint_gate(post_entry: dict[str, Any]) -> dict[str, Any]:
    w30 = (post_entry.get("forward") or {}).get("W1800") or {}
    n = int(post_entry.get("n") or 0)
    med = w30.get("close_delta_median")
    passed = n >= PHASE0_MIN_N and med is not None and float(med) > 0
    return {
        "pass": passed,
        "min_n": PHASE0_MIN_N,
        "w30_stop_less_gross_median_min": 0,
        "w30_stop_less_gross_median": med,
        "n": n,
    }


def build_stf_payload(
    *,
    code: str,
    cache_dir: Path,
    from_date: str,
    to_date: str,
    mode: Literal["fingerprint", "grid"] = "fingerprint",
    slippage_pts: float = DEFAULT_SLIPPAGE_PTS,
    friction_points: float = FRICTION_POINTS,
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

    series = load_tick_series(code, sorted(dates), cache_dir=cache_dir)
    param_sets = _iter_param_sets(mode)

    all_long: dict[str, list[dict[str, Any]]] = {p.key(): [] for p in param_sets}
    all_short: dict[str, list[dict[str, Any]]] = {p.key(): [] for p in param_sets}
    funnel_by_param: dict[str, list[dict[str, int]]] = {p.key(): [] for p in param_sets}
    entries_per_day: dict[str, dict[str, int]] = {p.key(): {} for p in param_sets}

    for day in dates:
        for params in param_sets:
            key = params.key()
            long_rows, short_rows, funnel = detect_stf_entries_for_day(
                code,
                day,
                cache_dir=cache_dir,
                params=params,
                slippage_pts=slippage_pts,
                friction_points=friction_points,
            )
            all_long[key].extend(long_rows)
            all_short[key].extend(short_rows)
            funnel_by_param[key].append(funnel)
            if long_rows:
                day_key = day.isoformat()
                entries_per_day[key][day_key] = entries_per_day[key].get(day_key, 0) + len(
                    long_rows
                )

    summary_by_param: dict[str, Any] = {}
    post_entry_by_param: dict[str, Any] = {}
    post_entry_short_by_param: dict[str, Any] = {}
    slippage_by_param: dict[str, Any] = {}
    funnel_agg: dict[str, Any] = {}

    for key, rows in all_long.items():
        if rows:
            enrich_rows_with_forward_windows(rows, series)
        short_appendix = all_short[key]
        if short_appendix:
            enrich_rows_with_forward_windows(short_appendix, series)

        summary_by_param[key] = {
            EXIT_VARIANT: _summarize_gross_net("gross_atr_sim", "net_atr_sim", rows),
        }
        post_entry_by_param[key] = summarize_post_entry_diagnosis(
            rows,
            friction_points=friction_points,
        )
        post_entry_short_by_param[key] = summarize_post_entry_diagnosis(
            short_appendix,
            friction_points=friction_points,
        )
        slippage_by_param[key] = _slippage_ratio_summary(rows)
        funnel_agg[key] = {
            "totals": _aggregate_funnel(funnel_by_param[key]),
            "entries_per_day": _flips_per_day_stats(entries_per_day[key]),
            "friction_upper_bound_pts_per_day_p50": _percentile(
                [float(c) * friction_points for c in entries_per_day[key].values()],
                50,
            )
            if entries_per_day[key]
            else None,
        }

    phase0_gate = _evaluate_phase0_gate_params(summary_by_param)
    fingerprint_gate: dict[str, Any] | None = None
    if mode == "fingerprint" and param_sets:
        only_key = param_sets[0].key()
        fingerprint_gate = _evaluate_fingerprint_gate(post_entry_by_param.get(only_key, {}))

    variant = "stf_fingerprint_v1" if mode == "fingerprint" else "stf_grid_v1"

    return {
        "schema_version": SCHEMA_VERSION,
        "thesis": "supertrend_flip_continuation",
        "variant": variant,
        "mode": mode,
        "from_date": from_date,
        "to_date": to_date,
        "code": code,
        "friction_points_per_round_trip": friction_points,
        "entry_slippage_pts_long": slippage_pts,
        "sim_params": {
            "timeframe_min": TIMEFRAME_MIN,
            "atr_method": "sma_tr_period_via_atr_series_from_bars",
            "atr_indexing": "orb_style_bars_slice_idx_plus_one",
            "min_atr_pts": DEFAULT_MIN_ATR,
            "session_entry": f"{ENTRY_START.isoformat()}–{NO_NEW_ENTRY_AFTER.isoformat()}",
            "last_entry_before": LAST_ENTRY_BEFORE.isoformat(),
            "no_new_entry_after": NO_NEW_ENTRY_AFTER.isoformat(),
            "boundary_rule": "confirmation_tick_exchange_time",
            "short_confirm_rule": "tick.close < supertrend_line(b); bear line = final_ub",
            "long_confirm_rule": "tick.close > supertrend_line(b); bull line = final_lb",
            "direction_phase0": "Long-only fill; flip_short post_entry appendix",
            "hard_stop_atr_k_grid": list(DEFAULT_K_SL),
            "tp_atr_k_grid": list(DEFAULT_TP_ATR_K),
            "max_hold_sec": DEFAULT_MAX_HOLD_SEC,
            "exit_variant": EXIT_VARIANT,
        },
        "fingerprint_params": {
            "atr_period": FINGERPRINT_ATR_PERIOD,
            "st_mult": FINGERPRINT_ST_MULT,
            "cooldown_bars": FINGERPRINT_COOLDOWN_BARS,
            "k_sl": FINGERPRINT_K_SL,
            "tp_atr_k": FINGERPRINT_TP_ATR_K,
        }
        if mode == "fingerprint"
        else None,
        "fingerprint_gate": fingerprint_gate,
        "phase0_gate": phase0_gate,
        "summary_by_param": summary_by_param,
        "post_entry_diagnosis_by_param": post_entry_by_param,
        "post_entry_short_appendix_by_param": post_entry_short_by_param,
        "slippage_ratio_by_param": slippage_by_param,
        "funnel_by_param": funnel_agg,
        "entry_count_by_param": {k: len(v) for k, v in all_long.items()},
        "short_appendix_count_by_param": {k: len(v) for k, v in all_short.items()},
        "rows_by_param": all_long,
        "short_appendix_rows_by_param": all_short,
    }
