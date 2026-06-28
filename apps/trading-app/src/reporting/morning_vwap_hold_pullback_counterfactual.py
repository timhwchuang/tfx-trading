"""FT-014 Phase 0: Morning VWAP hold pullback (long-only) counterfactual."""

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
from reporting.vwap_trend_pullback_counterfactual import BarCtx, _build_bar_contexts, _session_vwap_series
from storage.kbar_loader import KBarRecord, load_kbars_csv, resolve_kbar_path
from storage.tick_loader import resolve_cli_tick_cache_dates

SCHEMA_VERSION = 1
MVHP_ATR_PERIOD = 14

ENTRY_START = dt.time(9, 15)
NO_NEW_ENTRY_AFTER = dt.time(10, 30)
DEFAULT_MIN_ATR = 25.0
DEFAULT_MAX_HOLD_SEC = 900
EXIT_VARIANT = "atr_barrier_900s"

DEFAULT_HOLD_MIN_BARS = (5, 10, 15)
DEFAULT_TOUCH_BUF_K = (0.05, 0.10, 0.15)
DEFAULT_PULLBACK_VOL_RATIO_MAX = (0.70, 0.85)
DEFAULT_VWAP_SLOPE_BARS = (2, 3)
DEFAULT_K_SL = (0.75, 1.0, 1.25)
DEFAULT_TP_ATR_K = (1.5, 2.0, 2.5)

FINGERPRINT_HOLD_MIN_BARS = 10
FINGERPRINT_TOUCH_BUF_K = 0.10
FINGERPRINT_PULLBACK_VOL_RATIO_MAX = 0.85
FINGERPRINT_VWAP_SLOPE_BARS = 3
FINGERPRINT_K_SL = 1.0
FINGERPRINT_TP_ATR_K = 2.0


@dataclass(frozen=True)
class MvhpParams:
    hold_min_bars: int
    touch_buf_k: float
    pullback_vol_ratio_max: float
    vwap_slope_bars: int
    k_sl: float
    tp_atr_k: float

    def key(self) -> str:
        tb = f"{self.touch_buf_k:g}".replace(".", "p")
        vr = f"{self.pullback_vol_ratio_max:g}".replace(".", "p")
        ks = f"{self.k_sl:g}".replace(".", "p")
        tp = f"{self.tp_atr_k:g}".replace(".", "p")
        return (
            f"hm{self.hold_min_bars}_tb{tb}_vr{vr}_vs{self.vwap_slope_bars}"
            f"_ksl{ks}_tp{tp}"
        )


@dataclass(frozen=True)
class MvhpSignal:
    day: dt.date
    params: MvhpParams
    entry_ts: int
    entry_price: float
    atr: float
    session_vwap: float
    hold_bars: int
    hold_start_idx: int


def _bar_close_time(bar: KBarRecord) -> dt.time:
    return (bar.ts + dt.timedelta(minutes=1)).time()


def _in_entry_window(bar: KBarRecord) -> bool:
    t = _bar_close_time(bar)
    return ENTRY_START <= t < NO_NEW_ENTRY_AFTER


def _vwap_slope_ok(vwaps: list[float], idx: int, slope_bars: int) -> bool:
    if idx < slope_bars - 1:
        return False
    for j in range(slope_bars - 1):
        if not vwaps[idx - j] > vwaps[idx - j - 1]:
            return False
    return True


def _hold_bar_ok(
    ctx: BarCtx,
    vwaps: list[float],
    *,
    vwap_slope_bars: int,
    min_atr: float,
) -> bool:
    if ctx.atr < min_atr:
        return False
    if ctx.close <= ctx.session_vwap:
        return False
    return _vwap_slope_ok(vwaps, ctx.idx, vwap_slope_bars)


def _touch_bar_ok(ctx: BarCtx, *, touch_buf_k: float) -> bool:
    buf = touch_buf_k * ctx.atr
    upper = ctx.session_vwap + buf
    lower = ctx.session_vwap - buf
    return ctx.low <= upper and ctx.close >= lower


def _vol_shrink_ok(
    contexts: list[BarCtx],
    touch_idx: int,
    hold_start: int,
    hold_end: int,
    *,
    pullback_vol_ratio_max: float,
) -> bool:
    hold_vols = [contexts[j].volume for j in range(hold_start, hold_end + 1)]
    if not hold_vols:
        return False
    med = statistics.median(hold_vols)
    if med <= 0:
        return False
    return contexts[touch_idx].volume <= med * pullback_vol_ratio_max


def detect_mvhp_signal(
    contexts: list[BarCtx],
    bars: list[KBarRecord],
    *,
    params: MvhpParams,
    min_atr: float = DEFAULT_MIN_ATR,
) -> tuple[MvhpSignal | None, dict[str, bool]]:
    """Return signal and per-day funnel flags."""
    funnel = {
        "hold_pass": False,
        "first_touch": False,
        "vol_shrink": False,
    }
    if len(contexts) < params.hold_min_bars + params.vwap_slope_bars:
        return None, funnel

    vwaps = _session_vwap_series(bars)
    hold_streak = 0
    touch_seen = False
    day = bars[0].ts.date()

    for idx, bar in enumerate(bars):
        if not _in_entry_window(bar):
            hold_streak = 0
            continue

        ctx = contexts[idx]
        if _hold_bar_ok(ctx, vwaps, vwap_slope_bars=params.vwap_slope_bars, min_atr=min_atr):
            hold_streak += 1
        else:
            hold_streak = 0
            continue

        if hold_streak < params.hold_min_bars:
            continue

        funnel["hold_pass"] = True
        hold_end = idx
        hold_start = idx - params.hold_min_bars + 1

        if touch_seen:
            continue

        if not _touch_bar_ok(ctx, touch_buf_k=params.touch_buf_k):
            continue

        touch_seen = True
        funnel["first_touch"] = True

        if not _vol_shrink_ok(
            contexts,
            idx,
            hold_start,
            hold_end,
            pullback_vol_ratio_max=params.pullback_vol_ratio_max,
        ):
            break

        funnel["vol_shrink"] = True
        return (
            MvhpSignal(
                day=day,
                params=params,
                entry_ts=ctx.ts,
                entry_price=ctx.close,
                atr=ctx.atr,
                session_vwap=round(ctx.session_vwap, 2),
                hold_bars=params.hold_min_bars,
                hold_start_idx=hold_start,
            ),
            funnel,
        )

    return None, funnel


def simulate_mvhp_entry(
    signal: MvhpSignal,
    ticks: list[tuple[int, float, int, int]],
    *,
    friction_points: float = FRICTION_POINTS,
    max_hold_sec: int = DEFAULT_MAX_HOLD_SEC,
) -> dict[str, Any]:
    sim = simulate_atr_barrier_exit(
        direction="Long",
        entry_price=signal.entry_price,
        armed_ts=signal.entry_ts,
        atr=signal.atr,
        ticks=ticks,
        hard_stop_atr_k=signal.params.k_sl,
        tp_atr_k=signal.params.tp_atr_k,
        max_hold_sec=max_hold_sec,
    )
    gross = float(sim["gross_pnl"])
    net = gross - friction_points
    return {
        "day": signal.day.isoformat(),
        "param": signal.params.key(),
        "direction": "Long",
        "ts": signal.entry_ts,
        "entry_price": round(signal.entry_price, 1),
        "atr": round(signal.atr, 2),
        "session_vwap": signal.session_vwap,
        "hold_bars": signal.hold_bars,
        "hold_start_idx": signal.hold_start_idx,
        "gross_atr_sim": gross,
        "net_atr_sim": net,
        "atr_barrier_sim": sim,
        "exit_variant": EXIT_VARIANT,
    }


def scan_mvhp_session(
    bars: list[KBarRecord],
    *,
    params: MvhpParams,
    ticks: list[tuple[int, float, int, int]] | None = None,
    friction_points: float = FRICTION_POINTS,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Core scan — testable without tick cache I/O."""
    funnel: dict[str, int] = {
        "days_with_session": 0,
        "hold_pass": 0,
        "first_touch": 0,
        "vol_shrink": 0,
        "entry": 0,
    }
    if len(bars) < MVHP_ATR_PERIOD + params.hold_min_bars + 2:
        return [], funnel

    if not any(_in_entry_window(b) for b in bars):
        return [], funnel

    funnel["days_with_session"] = 1
    contexts = _build_bar_contexts(bars)
    signal, day_flags = detect_mvhp_signal(contexts, bars, params=params)
    if day_flags["hold_pass"]:
        funnel["hold_pass"] = 1
    if day_flags["first_touch"]:
        funnel["first_touch"] = 1
    if day_flags["vol_shrink"]:
        funnel["vol_shrink"] = 1

    if signal is None or ticks is None:
        return [], funnel

    row = simulate_mvhp_entry(signal, ticks, friction_points=friction_points)
    funnel["entry"] = 1
    return [row], funnel


def detect_mvhp_entries_for_day(
    code: str,
    day: dt.date,
    *,
    cache_dir: Path,
    params: MvhpParams,
    friction_points: float = FRICTION_POINTS,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    kpath = resolve_kbar_path(cache_dir, code, day)
    empty_funnel = {
        "days_with_session": 0,
        "hold_pass": 0,
        "first_touch": 0,
        "vol_shrink": 0,
        "entry": 0,
    }
    if kpath is None:
        return [], empty_funnel

    bars = _session_bars(load_kbars_csv(kpath))
    ticks = _tick_rows_for_day(code, day, cache_dir=cache_dir)
    return scan_mvhp_session(bars, params=params, ticks=ticks, friction_points=friction_points)


def _aggregate_funnel(funnels: list[dict[str, int]]) -> dict[str, Any]:
    keys = ("days_with_session", "hold_pass", "first_touch", "vol_shrink", "entry")
    totals = {k: sum(f.get(k, 0) for f in funnels) for k in keys}
    hp = totals["hold_pass"]
    totals["hold_to_entry_rate"] = round(totals["entry"] / hp, 4) if hp else None
    totals["hold_to_touch_rate"] = round(totals["first_touch"] / hp, 4) if hp else None
    return totals


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
        candidate = {"param": param, "n": n, "gross_mean": gross, "net_mean": net}
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


def _evaluate_section31_long(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"disqualified": True, "reasons": ["no_rows"]}
    gross = [float(r["gross_atr_sim"]) for r in rows]
    net = [float(r["net_atr_sim"]) for r in rows]
    gross_med = statistics.median(gross)
    net_mean = statistics.mean(net)
    reasons: list[str] = []
    if gross_med <= -5:
        reasons.append("gross_median_le_-5")
    if net_mean < -3:
        reasons.append("long_net_mean_lt_-3")
    return {
        "disqualified": bool(reasons),
        "reasons": reasons,
        "gross_median": round(gross_med, 2),
        "net_mean": round(net_mean, 2),
        "n": len(rows),
    }


def _iter_param_sets(mode: Literal["fingerprint", "grid"]) -> list[MvhpParams]:
    if mode == "fingerprint":
        return [
            MvhpParams(
                hold_min_bars=FINGERPRINT_HOLD_MIN_BARS,
                touch_buf_k=FINGERPRINT_TOUCH_BUF_K,
                pullback_vol_ratio_max=FINGERPRINT_PULLBACK_VOL_RATIO_MAX,
                vwap_slope_bars=FINGERPRINT_VWAP_SLOPE_BARS,
                k_sl=FINGERPRINT_K_SL,
                tp_atr_k=FINGERPRINT_TP_ATR_K,
            )
        ]
    out: list[MvhpParams] = []
    for hm in DEFAULT_HOLD_MIN_BARS:
        for tb in DEFAULT_TOUCH_BUF_K:
            for vr in DEFAULT_PULLBACK_VOL_RATIO_MAX:
                for vs in DEFAULT_VWAP_SLOPE_BARS:
                    for ks in DEFAULT_K_SL:
                        for tp in DEFAULT_TP_ATR_K:
                            out.append(
                                MvhpParams(
                                    hold_min_bars=hm,
                                    touch_buf_k=tb,
                                    pullback_vol_ratio_max=vr,
                                    vwap_slope_bars=vs,
                                    k_sl=ks,
                                    tp_atr_k=tp,
                                )
                            )
    return out


def build_mvhp_payload(
    *,
    code: str,
    cache_dir: Path,
    from_date: str,
    to_date: str,
    mode: Literal["fingerprint", "grid"] = "fingerprint",
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

    all_rows: dict[str, list[dict[str, Any]]] = {p.key(): [] for p in param_sets}
    funnel_by_param: dict[str, list[dict[str, int]]] = {p.key(): [] for p in param_sets}

    for day in dates:
        for params in param_sets:
            rows, funnel = detect_mvhp_entries_for_day(
                code,
                day,
                cache_dir=cache_dir,
                params=params,
                friction_points=friction_points,
            )
            key = params.key()
            all_rows[key].extend(rows)
            funnel_by_param[key].append(funnel)

    summary_by_param: dict[str, Any] = {}
    post_entry_by_param: dict[str, Any] = {}
    section31_by_param: dict[str, Any] = {}
    funnel_agg: dict[str, Any] = {}

    for key, rows in all_rows.items():
        if rows:
            enrich_rows_with_forward_windows(rows, series)
        summary_by_param[key] = {
            EXIT_VARIANT: _summarize_gross_net("gross_atr_sim", "net_atr_sim", rows),
        }
        post_entry_by_param[key] = summarize_post_entry_diagnosis(
            rows,
            friction_points=friction_points,
        )
        section31_by_param[key] = _evaluate_section31_long(rows)
        funnel_agg[key] = {"totals": _aggregate_funnel(funnel_by_param[key])}

    phase0_gate = _evaluate_phase0_gate_params(summary_by_param)
    fingerprint_gate: dict[str, Any] | None = None
    if mode == "fingerprint" and param_sets:
        fingerprint_gate = _evaluate_fingerprint_gate(
            post_entry_by_param.get(param_sets[0].key(), {})
        )

    outcome: str | None = None
    if mode == "fingerprint" and fingerprint_gate and not fingerprint_gate.get("pass"):
        outcome = "mvhp_fingerprint_fail"
    elif mode == "grid" and not phase0_gate.get("pass"):
        outcome = "mvhp_fingerprint_pass_g1_fail"

    variant = "mvhp_fingerprint_v1" if mode == "fingerprint" else "mvhp_grid_v1"

    return {
        "schema_version": SCHEMA_VERSION,
        "thesis": "morning_vwap_hold_pullback",
        "variant": variant,
        "mode": mode,
        "from_date": from_date,
        "to_date": to_date,
        "code": code,
        "friction_points_per_round_trip": friction_points,
        "entry_model": "raw_1m_bar_close_orb_vsf_family",
        "sim_params": {
            "entry_window": f"{ENTRY_START.isoformat()}–{NO_NEW_ENTRY_AFTER.isoformat()}",
            "max_trades_per_day": 1,
            "atr_period": MVHP_ATR_PERIOD,
            "min_atr_pts": DEFAULT_MIN_ATR,
            "exit_variant": EXIT_VARIANT,
            "max_hold_sec": DEFAULT_MAX_HOLD_SEC,
        },
        "fingerprint_params": {
            "hold_min_bars": FINGERPRINT_HOLD_MIN_BARS,
            "touch_buf_k": FINGERPRINT_TOUCH_BUF_K,
            "pullback_vol_ratio_max": FINGERPRINT_PULLBACK_VOL_RATIO_MAX,
            "vwap_slope_bars": FINGERPRINT_VWAP_SLOPE_BARS,
            "k_sl": FINGERPRINT_K_SL,
            "tp_atr_k": FINGERPRINT_TP_ATR_K,
        }
        if mode == "fingerprint"
        else None,
        "fingerprint_gate": fingerprint_gate,
        "phase0_gate": phase0_gate,
        "section31_long_by_param": section31_by_param,
        "outcome_hint": outcome,
        "summary_by_param": summary_by_param,
        "post_entry_diagnosis_by_param": post_entry_by_param,
        "funnel_by_param": funnel_agg,
        "entry_count_by_param": {k: len(v) for k, v in all_rows.items()},
        "rows_by_param": all_rows,
    }
