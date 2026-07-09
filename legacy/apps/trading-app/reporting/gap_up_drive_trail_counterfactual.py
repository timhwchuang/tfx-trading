"""FT-018 Phase 0: Gap up drive trail (skew · exit-led) counterfactual."""

from __future__ import annotations

import datetime as dt
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from reporting.armed_forward_counterfactual import FRICTION_POINTS, _summarize_gross_net
from reporting.forward_pnl import load_tick_series
from reporting.gap_drive_continuation_counterfactual import (
    GDC_ATR_PERIOD,
    MIN_GAP_PTS,
    _atr_at_index,
    _index_at_close_time,
    _load_gdc_day_context,
    _open_0845,
    detect_gdc_signal,
)
from reporting.gate_summary import build_gate_summary
from reporting.gap_drive_continuation_counterfactual import GdcParams as GdcEntryParams
from reporting.post_entry_diagnosis import (
    enrich_rows_with_forward_windows,
    summarize_post_entry_diagnosis,
)
from reporting.simulate_atr_trail_skew_exit import simulate_atr_trail_skew_exit
from storage.tick_loader import resolve_cli_tick_cache_dates

SCHEMA_VERSION = 1
THESIS_CLASS = "skew"
EXIT_VARIANT = "atr_trail_skew_900s"
DEFAULT_MIN_ATR = 25.0
DEFAULT_MAX_HOLD_SEC = 900
FINGERPRINT_WINDOW_SEC = 900

PHASE0_GROSS_MIN = 5.0
PHASE0_NET_MIN = 0.0
PHASE0_MIN_N = 15

FINGERPRINT_GAP_K_ATR = 1.0
FINGERPRINT_RETRACE_MAX_FRAC = 0.40
FINGERPRINT_K_SL = 1.0
FINGERPRINT_BE_TRIGGER = 1.0
FINGERPRINT_TRAIL_ARM = 2.0
FINGERPRINT_TRAIL_DIST = 0.5
FINGERPRINT_HARD_TP = 4.0

DEFAULT_GAP_K_ATR = (1.0, 1.5)
DEFAULT_RETRACE_MAX_FRAC = (0.30, 0.40)
DEFAULT_K_SL = (0.75, 1.0, 1.25)
DEFAULT_BE_TRIGGER = (0.75, 1.0)
DEFAULT_TRAIL_ARM = (1.5, 2.0)
DEFAULT_TRAIL_DIST = (0.4, 0.5, 0.6)
DEFAULT_HARD_TP: tuple[float | None, ...] = (3.0, 4.0, None)

PAYOFF_RATIO_MIN = 2.5
TAIL_GROSS_MIN_PTS = 15.0
MAX_CONSECUTIVE_LOSSES = 10
MAX_CONSECUTIVE_LOSS_PTS = 150.0
WORST_MONTH_NET_PTS = -120.0
TOP3_WIN_GROSS_SHARE_MAX = 0.65


@dataclass(frozen=True)
class GudtParams:
    gap_k_atr: float
    retrace_max_frac: float
    k_sl: float
    be_trigger_atr_k: float
    trail_arm_atr_k: float
    trail_dist_atr_k: float
    hard_tp_atr_k: float | None

    def key(self) -> str:
        gk = f"{self.gap_k_atr:g}".replace(".", "p")
        rt = f"{self.retrace_max_frac:g}".replace(".", "p")
        ks = f"{self.k_sl:g}".replace(".", "p")
        be = f"{self.be_trigger_atr_k:g}".replace(".", "p")
        ta = f"{self.trail_arm_atr_k:g}".replace(".", "p")
        td = f"{self.trail_dist_atr_k:g}".replace(".", "p")
        if self.hard_tp_atr_k is None:
            tp = "none"
        else:
            tp = f"{self.hard_tp_atr_k:g}".replace(".", "p")
        return f"gk{gk}_rt{rt}_ksl{ks}_be{be}_ta{ta}_td{td}_tp{tp}"

    def entry_params(self) -> GdcEntryParams:
        return GdcEntryParams(
            gap_k_atr=self.gap_k_atr,
            retrace_max_frac=self.retrace_max_frac,
            k_sl=self.k_sl,
            tp_atr_k=2.0,
        )


def _empty_gudt_funnel() -> dict[str, int]:
    return {
        "days_with_session": 0,
        "gap_qualify_up": 0,
        "retrace_ok": 0,
        "break_signal": 0,
        "entry": 0,
    }


def simulate_gudt_entry(
    signal: Any,
    ticks: list[tuple[int, float, int, int]],
    *,
    params: GudtParams,
    friction_points: float = FRICTION_POINTS,
    max_hold_sec: int = DEFAULT_MAX_HOLD_SEC,
) -> dict[str, Any]:
    sim = simulate_atr_trail_skew_exit(
        direction=signal.direction,
        entry_price=signal.entry_price,
        entry_ts=signal.entry_ts,
        atr=signal.atr,
        ticks=ticks,
        hard_stop_atr_k=params.k_sl,
        be_trigger_atr_k=params.be_trigger_atr_k,
        trail_arm_atr_k=params.trail_arm_atr_k,
        trail_dist_atr_k=params.trail_dist_atr_k,
        hard_tp_atr_k=params.hard_tp_atr_k,
        max_hold_sec=max_hold_sec,
        min_atr_pts=DEFAULT_MIN_ATR,
    )
    gross = float(sim["gross_pnl"])
    net = gross - friction_points
    slip: dict[str, float] = {}
    for extra in (0, 1, 2):
        slip[str(extra)] = round(gross - friction_points - extra, 2)
    return {
        "day": signal.day.isoformat(),
        "param": params.key(),
        "direction": signal.direction,
        "ts": signal.entry_ts,
        "entry_price": round(signal.entry_price, 1),
        "atr": round(signal.atr, 2),
        "gap_pts": signal.gap_pts,
        "open_0845": round(signal.open_0845, 1),
        "prior_close": round(signal.prior_close, 1),
        "drive_high": round(signal.drive_high, 1),
        "drive_low": round(signal.drive_low, 1),
        "gross_atr_sim": gross,
        "net_atr_sim": net,
        "entry_slippage_sensitivity_pts": slip,
        "atr_trail_sim": sim,
        "exit_variant": EXIT_VARIANT,
    }


def scan_gudt_session(
    bars: list,
    *,
    params: GudtParams,
    day: dt.date,
    prior_close: float | None,
    ticks: list[tuple[int, float, int, int]] | None = None,
    friction_points: float = FRICTION_POINTS,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    funnel = _empty_gudt_funnel()
    if not bars or prior_close is None:
        return [], funnel

    funnel["days_with_session"] = 1
    if ticks is None:
        return [], funnel

    open_0845 = _open_0845(bars)
    if open_0845 is None:
        return [], funnel

    gap_pts = open_0845 - prior_close
    if gap_pts <= MIN_GAP_PTS:
        return [], funnel

    atr_idx = _index_at_close_time(bars, dt.time(9, 14))
    if atr_idx is None:
        return [], funnel
    atr = _atr_at_index(bars, atr_idx)

    if gap_pts >= params.gap_k_atr * atr:
        funnel["gap_qualify_up"] = 1

    entry_params = params.entry_params()
    signal, flags = detect_gdc_signal(
        bars, ticks, params=entry_params, day=day, prior_close=prior_close
    )
    if flags["retrace_ok"]:
        funnel["retrace_ok"] = 1
    if flags["break_signal"]:
        funnel["break_signal"] = 1

    if signal is None or signal.direction != "Long" or gap_pts <= 0:
        return [], funnel

    row = simulate_gudt_entry(signal, ticks, params=params, friction_points=friction_points)
    funnel["entry"] = 1
    return [row], funnel


def detect_gudt_entries_for_day(
    code: str,
    day: dt.date,
    *,
    cache_dir: Path,
    params: GudtParams,
    sorted_dates: list[dt.date],
    friction_points: float = FRICTION_POINTS,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    ctx = _load_gdc_day_context(code, day, cache_dir=cache_dir, sorted_dates=sorted_dates)
    if ctx is None:
        return [], _empty_gudt_funnel()
    bars, ticks, prior_close = ctx
    return scan_gudt_session(
        bars,
        params=params,
        day=day,
        prior_close=prior_close,
        ticks=ticks,
        friction_points=friction_points,
    )


def collect_gdc_long_entry_keys(
    code: str,
    day: dt.date,
    *,
    cache_dir: Path,
    entry_params: GdcEntryParams,
    sorted_dates: list[dt.date],
) -> set[tuple[str, int]]:
    """Long-only entry keys from GDC P0 for bit-identical reuse check."""
    ctx = _load_gdc_day_context(code, day, cache_dir=cache_dir, sorted_dates=sorted_dates)
    if ctx is None:
        return set()
    bars, ticks, prior_close = ctx
    open_0845 = _open_0845(bars)
    if open_0845 is None:
        return set()
    gap_pts = open_0845 - prior_close
    if gap_pts <= MIN_GAP_PTS:
        return set()
    signal, _ = detect_gdc_signal(
        bars, ticks, params=entry_params, day=day, prior_close=prior_close
    )
    if signal is None or signal.direction != "Long":
        return set()
    return {(day.isoformat(), signal.entry_ts)}


def _aggregate_funnel(funnels: list[dict[str, int]]) -> dict[str, Any]:
    keys = ("days_with_session", "gap_qualify_up", "retrace_ok", "break_signal", "entry")
    totals = {k: sum(f.get(k, 0) for f in funnels) for k in keys}
    gq = totals["gap_qualify_up"]
    totals["gap_up_to_entry_rate"] = round(totals["entry"] / gq, 4) if gq else None
    return totals


def _evaluate_fingerprint_gate(post_entry: dict[str, Any]) -> dict[str, Any]:
    w_key = f"W{FINGERPRINT_WINDOW_SEC}"
    w_block = (post_entry.get("forward") or {}).get(w_key) or {}
    n = int(post_entry.get("n") or 0)
    med = w_block.get("close_delta_median")
    direction_ok = med is not None and float(med) > 0
    n_ok = n >= PHASE0_MIN_N
    passed = direction_ok and n_ok
    return {
        "pass": passed,
        "min_n": PHASE0_MIN_N,
        "fingerprint_window_sec": FINGERPRINT_WINDOW_SEC,
        "w900_stop_less_gross_median_min": 0,
        "w900_stop_less_gross_median": med,
        "n": n,
        "direction_ok": direction_ok,
        "n_ok": n_ok,
    }


def _fingerprint_outcome(fp_gate: dict[str, Any]) -> str:
    if fp_gate.get("pass"):
        return "fingerprint_pass"
    n = int(fp_gate.get("n") or 0)
    med = fp_gate.get("w900_stop_less_gross_median")
    if n >= PHASE0_MIN_N and med is not None and float(med) <= 0:
        return "gudt_fingerprint_fail_direction"
    if n < PHASE0_MIN_N and med is not None and float(med) > 0:
        return "gudt_fingerprint_fail_n"
    if n < PHASE0_MIN_N:
        return "gudt_fingerprint_fail_n"
    return "gudt_fingerprint_fail_direction"


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
        "thesis_class": THESIS_CLASS,
        "best_passing": best,
    }


def _max_consecutive_losses(nets: list[float]) -> tuple[int, float]:
    max_streak = 0
    streak = 0
    max_pts = 0.0
    streak_pts = 0.0
    for net in nets:
        if net <= 0:
            streak += 1
            streak_pts += net
            max_streak = max(max_streak, streak)
            max_pts = min(max_pts, streak_pts)
        else:
            streak = 0
            streak_pts = 0.0
    return max_streak, abs(max_pts)


def _worst_month_net(rows: list[dict[str, Any]]) -> float:
    by_month: dict[str, float] = {}
    for row in rows:
        day = dt.date.fromisoformat(str(row["day"]))
        key = f"{day.year}-{day.month:02d}"
        by_month[key] = by_month.get(key, 0.0) + float(row["net_atr_sim"])
    return min(by_month.values()) if by_month else 0.0


def _top3_win_gross_share(gross: list[float]) -> float | None:
    wins = sorted([g for g in gross if g > 0], reverse=True)
    total = sum(g for g in gross if g > 0)
    if total <= 0 or not wins:
        return None
    return sum(wins[:3]) / total


def _evaluate_skew_gate(rows: list[dict[str, Any]], *, friction_points: float) -> dict[str, Any]:
    if not rows:
        return {"disqualified": True, "reasons": ["no_rows"]}

    gross = [float(r["gross_atr_sim"]) for r in rows]
    net = [float(r["net_atr_sim"]) for r in rows]
    wins = [g for g in gross if g > 0]
    losses = [g for g in gross if g <= 0]
    payoff = None
    if wins and losses:
        payoff = (sum(wins) / len(wins)) / abs(sum(losses) / len(losses))

    tail_count = sum(1 for g in gross if g >= TAIL_GROSS_MIN_PTS)
    max_losses, max_loss_pts = _max_consecutive_losses(net)
    worst_month = _worst_month_net(rows)
    top3_share = _top3_win_gross_share(gross)
    net_at_7 = [g - 7.0 for g in gross]
    net_mean_at_7 = statistics.mean(net_at_7) if net_at_7 else None

    reasons: list[str] = []
    if payoff is None or payoff < PAYOFF_RATIO_MIN:
        reasons.append("payoff_ratio")
    if tail_count < 5:
        reasons.append("tail_count")
    if max_losses > MAX_CONSECUTIVE_LOSSES:
        reasons.append("max_consecutive_losses")
    if max_loss_pts > MAX_CONSECUTIVE_LOSS_PTS:
        reasons.append("max_consecutive_loss_pts")
    if worst_month <= WORST_MONTH_NET_PTS:
        reasons.append("worst_month_net")
    if top3_share is not None and top3_share > TOP3_WIN_GROSS_SHARE_MAX:
        reasons.append("top3_win_gross_share")
    if net_mean_at_7 is not None and net_mean_at_7 <= 0:
        reasons.append("net_mean_at_friction_7")

    return {
        "disqualified": bool(reasons),
        "reasons": reasons,
        "payoff_ratio": round(payoff, 3) if payoff is not None else None,
        "tail_count": tail_count,
        "max_consecutive_losses": max_losses,
        "max_consecutive_loss_pts": round(max_loss_pts, 1),
        "worst_month_net": round(worst_month, 1),
        "top3_win_gross_share": round(top3_share, 3) if top3_share is not None else None,
        "net_mean_at_friction_7": round(net_mean_at_7, 2) if net_mean_at_7 is not None else None,
        "win_rate": round(len(wins) / len(gross), 3) if gross else None,
        "n": len(rows),
    }


def _slippage_sensitivity_summary(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    if not rows:
        return {"extra_0": None, "extra_1": None, "extra_2": None}
    out: dict[str, float | None] = {}
    for extra in ("0", "1", "2"):
        vals = [
            float((r.get("entry_slippage_sensitivity_pts") or {}).get(extra))
            for r in rows
            if (r.get("entry_slippage_sensitivity_pts") or {}).get(extra) is not None
        ]
        out[f"extra_{extra}"] = round(statistics.mean(vals), 2) if vals else None
    return out


def _exit_diagnostics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"exit_gap": None, "pct_mfe_ge_1atr": None}
    mfes: list[float] = []
    grosses: list[float] = []
    mfe_ge_1atr = 0
    for row in rows:
        sim = row.get("atr_trail_sim") or {}
        mfe = sim.get("mfe")
        atr = float(row.get("atr") or 0)
        grosses.append(float(row["gross_atr_sim"]))
        if mfe is not None:
            mfes.append(float(mfe))
            if atr > 0 and float(mfe) >= atr:
                mfe_ge_1atr += 1
    mfe_med = statistics.median(mfes) if mfes else None
    gross_med = statistics.median(grosses) if grosses else None
    exit_gap = (
        round(mfe_med - gross_med, 2)
        if mfe_med is not None and gross_med is not None
        else None
    )
    return {
        "exit_gap": exit_gap,
        "pct_mfe_ge_1atr": round(mfe_ge_1atr / len(rows), 4) if rows else None,
        "mfe_median": round(mfe_med, 2) if mfe_med is not None else None,
        "barrier_gross_median": round(gross_med, 2) if gross_med is not None else None,
    }


def _iter_param_sets(mode: Literal["fingerprint", "grid"]) -> list[GudtParams]:
    if mode == "fingerprint":
        return [
            GudtParams(
                gap_k_atr=FINGERPRINT_GAP_K_ATR,
                retrace_max_frac=FINGERPRINT_RETRACE_MAX_FRAC,
                k_sl=FINGERPRINT_K_SL,
                be_trigger_atr_k=FINGERPRINT_BE_TRIGGER,
                trail_arm_atr_k=FINGERPRINT_TRAIL_ARM,
                trail_dist_atr_k=FINGERPRINT_TRAIL_DIST,
                hard_tp_atr_k=FINGERPRINT_HARD_TP,
            )
        ]
    out: list[GudtParams] = []
    for gk in DEFAULT_GAP_K_ATR:
        for rt in DEFAULT_RETRACE_MAX_FRAC:
            for ks in DEFAULT_K_SL:
                for be in DEFAULT_BE_TRIGGER:
                    for ta in DEFAULT_TRAIL_ARM:
                        for td in DEFAULT_TRAIL_DIST:
                            for hp in DEFAULT_HARD_TP:
                                out.append(
                                    GudtParams(
                                        gap_k_atr=gk,
                                        retrace_max_frac=rt,
                                        k_sl=ks,
                                        be_trigger_atr_k=be,
                                        trail_arm_atr_k=ta,
                                        trail_dist_atr_k=td,
                                        hard_tp_atr_k=hp,
                                    )
                                )
    return out


def build_gudt_payload(
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

    sorted_dates = sorted(dates)
    series = load_tick_series(code, sorted_dates, cache_dir=cache_dir)
    param_sets = _iter_param_sets(mode)

    all_rows: dict[str, list[dict[str, Any]]] = {p.key(): [] for p in param_sets}
    funnel_by_param: dict[str, list[dict[str, int]]] = {p.key(): [] for p in param_sets}

    for day in dates:
        ctx = _load_gdc_day_context(code, day, cache_dir=cache_dir, sorted_dates=sorted_dates)
        if ctx is None:
            empty = _empty_gudt_funnel()
            for params in param_sets:
                funnel_by_param[params.key()].append(empty)
            continue
        bars, ticks, prior_close = ctx
        for params in param_sets:
            rows, funnel = scan_gudt_session(
                bars,
                params=params,
                day=day,
                prior_close=prior_close,
                ticks=ticks,
                friction_points=friction_points,
            )
            key = params.key()
            all_rows[key].extend(rows)
            funnel_by_param[key].append(funnel)

    summary_by_param: dict[str, Any] = {}
    post_entry_by_param: dict[str, Any] = {}
    skew_gate_by_param: dict[str, Any] = {}
    slippage_by_param: dict[str, Any] = {}
    exit_diag_by_param: dict[str, Any] = {}
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
        skew_gate_by_param[key] = _evaluate_skew_gate(rows, friction_points=friction_points)
        slippage_by_param[key] = _slippage_sensitivity_summary(rows)
        exit_diag_by_param[key] = _exit_diagnostics(rows)
        funnel_agg[key] = {"totals": _aggregate_funnel(funnel_by_param[key])}

    phase0_gate = _evaluate_phase0_gate_params(summary_by_param)
    fingerprint_gate: dict[str, Any] | None = None
    if mode == "fingerprint" and param_sets:
        fingerprint_gate = _evaluate_fingerprint_gate(
            post_entry_by_param.get(param_sets[0].key(), {})
        )

    outcome: str | None = None
    if mode == "fingerprint" and fingerprint_gate:
        if not fingerprint_gate.get("pass"):
            outcome = _fingerprint_outcome(fingerprint_gate)
    elif mode == "grid" and not phase0_gate.get("pass"):
        outcome = "gudt_fingerprint_pass_g1_fail"
    elif mode == "grid" and phase0_gate.get("pass"):
        best = phase0_gate.get("best_passing") or {}
        best_key = best.get("param")
        if best_key and skew_gate_by_param.get(best_key, {}).get("disqualified"):
            outcome = "gudt_no_skew_champion"

    variant = "gudt_fingerprint_v1" if mode == "fingerprint" else "gudt_grid_v1"

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "thesis": "gap_up_drive_trail",
        "thesis_class": THESIS_CLASS,
        "variant": variant,
        "mode": mode,
        "from_date": from_date,
        "to_date": to_date,
        "code": code,
        "friction_points_per_round_trip": friction_points,
        "entry_model": "gdc_p0_long_only_post_filter",
        "sim_params": {
            "drive_window_close": "09:15–09:45",
            "break_entry": "09:45–10:30",
            "max_trades_per_day": 1,
            "atr_period": GDC_ATR_PERIOD,
            "min_atr_pts": DEFAULT_MIN_ATR,
            "min_gap_pts": MIN_GAP_PTS,
            "exit_variant": EXIT_VARIANT,
            "max_hold_sec": DEFAULT_MAX_HOLD_SEC,
            "fingerprint_window_sec": FINGERPRINT_WINDOW_SEC,
        },
        "fingerprint_params": {
            "gap_k_atr": FINGERPRINT_GAP_K_ATR,
            "retrace_max_frac": FINGERPRINT_RETRACE_MAX_FRAC,
            "k_sl": FINGERPRINT_K_SL,
            "be_trigger_atr_k": FINGERPRINT_BE_TRIGGER,
            "trail_arm_atr_k": FINGERPRINT_TRAIL_ARM,
            "trail_dist_atr_k": FINGERPRINT_TRAIL_DIST,
            "hard_tp_atr_k": FINGERPRINT_HARD_TP,
            "fingerprint_window_sec": FINGERPRINT_WINDOW_SEC,
        }
        if mode == "fingerprint"
        else None,
        "fingerprint_gate": fingerprint_gate,
        "phase0_gate": phase0_gate,
        "skew_gate_by_param": skew_gate_by_param,
        "entry_slippage_sensitivity_by_param": slippage_by_param,
        "exit_diagnostics_by_param": exit_diag_by_param,
        "outcome_hint": outcome,
        "summary_by_param": summary_by_param,
        "post_entry_diagnosis_by_param": post_entry_by_param,
        "funnel_by_param": funnel_agg,
        "entry_count_by_param": {k: len(v) for k, v in all_rows.items()},
        "rows_by_param": all_rows,
    }
    payload["gate_summary"] = build_gate_summary(payload)
    return payload
