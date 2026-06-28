"""FT-016 Phase 0: Gap drive continuation (skew) counterfactual."""

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
from reporting.short_breakout_counterfactual import _session_bars
from reporting.volatility_baseline import atr_series_from_bars
from storage.kbar_loader import KBarRecord, load_kbars_csv, resolve_kbar_path
from storage.tick_loader import iter_replay_ticks, resolve_cli_tick_cache_dates

SCHEMA_VERSION = 1
THESIS_CLASS = "skew"
GDC_ATR_PERIOD = 14

SESSION_OPEN = dt.time(8, 45)
SESSION_OPEN_EDGE_TOLERANCE_MIN = 1
DRIVE_CLOSE_START = dt.time(9, 15)
DRIVE_CLOSE_END = dt.time(9, 45)
BREAK_START = dt.time(9, 45)
NO_NEW_ENTRY_AFTER = dt.time(10, 30)

MIN_GAP_PTS = 0.5
DEFAULT_MIN_ATR = 25.0
DEFAULT_MAX_HOLD_SEC = 900
EXIT_VARIANT = "atr_barrier_900s"

PHASE0_GROSS_MIN = 5.0
PHASE0_NET_MIN = 0.0
PHASE0_MIN_N = 15

DEFAULT_GAP_K_ATR = (1.0, 1.5)
DEFAULT_RETRACE_MAX_FRAC = (0.30, 0.40)
DEFAULT_K_SL = (0.75, 1.0, 1.25)
DEFAULT_TP_ATR_K = (1.5, 2.0, 2.5)

FINGERPRINT_GAP_K_ATR = 1.0
FINGERPRINT_RETRACE_MAX_FRAC = 0.40
FINGERPRINT_K_SL = 1.0
FINGERPRINT_TP_ATR_K = 2.0

PAYOFF_RATIO_MIN = 2.5
TAIL_GROSS_MIN_PTS = 15.0
MAX_CONSECUTIVE_LOSSES = 10
MAX_CONSECUTIVE_LOSS_PTS = 150.0
WORST_MONTH_NET_PTS = -120.0
TOP3_WIN_GROSS_SHARE_MAX = 0.65

TradeDir = Literal["Long", "Short"]


@dataclass(frozen=True)
class GdcParams:
    gap_k_atr: float
    retrace_max_frac: float
    k_sl: float
    tp_atr_k: float

    def key(self) -> str:
        gk = f"{self.gap_k_atr:g}".replace(".", "p")
        rt = f"{self.retrace_max_frac:g}".replace(".", "p")
        ks = f"{self.k_sl:g}".replace(".", "p")
        tp = f"{self.tp_atr_k:g}".replace(".", "p")
        return f"gk{gk}_rt{rt}_ksl{ks}_tp{tp}"


@dataclass(frozen=True)
class GdcSignal:
    day: dt.date
    params: GdcParams
    direction: TradeDir
    entry_ts: int
    entry_price: float
    atr: float
    gap_pts: float
    open_0845: float
    prior_close: float
    drive_high: float
    drive_low: float


def _bar_close_time(bar: KBarRecord) -> dt.time:
    return (bar.ts + dt.timedelta(minutes=1)).time()


def _atr_at_index(bars: list[KBarRecord], idx: int) -> float:
    tuples = [
        (b.High, b.Low, b.Close, b.High - b.Low, float(b.Volume)) for b in bars[: idx + 1]
    ]
    series = atr_series_from_bars(tuples, period=GDC_ATR_PERIOD)
    if not series:
        return DEFAULT_MIN_ATR
    return max(float(series[-1]), DEFAULT_MIN_ATR)


def _index_at_close_time(bars: list[KBarRecord], close_t: dt.time) -> int | None:
    for i, bar in enumerate(bars):
        if _bar_close_time(bar) == close_t:
            return i
    return None


def _open_0845(bars: list[KBarRecord]) -> float | None:
    if not bars:
        return None
    first = min(bars, key=lambda b: b.ts)
    t = first.ts.time()
    latest = (
        dt.datetime.combine(dt.date(2000, 1, 1), SESSION_OPEN)
        + dt.timedelta(minutes=SESSION_OPEN_EDGE_TOLERANCE_MIN)
    ).time()
    if SESSION_OPEN <= t <= latest:
        return float(first.Open)
    return None


def _prior_session_date(day: dt.date, sorted_dates: list[dt.date]) -> dt.date | None:
    try:
        idx = sorted_dates.index(day)
    except ValueError:
        return None
    if idx <= 0:
        return None
    return sorted_dates[idx - 1]


def _prior_close(code: str, prior_day: dt.date, *, cache_dir: Path) -> float | None:
    path = resolve_kbar_path(cache_dir, code, prior_day)
    if path is None:
        return None
    bars = _session_bars(load_kbars_csv(path))
    if not bars:
        return None
    return float(bars[-1].Close)


def _drive_window_bars(bars: list[KBarRecord]) -> list[KBarRecord]:
    out: list[KBarRecord] = []
    for bar in bars:
        ct = _bar_close_time(bar)
        if DRIVE_CLOSE_START <= ct <= DRIVE_CLOSE_END:
            out.append(bar)
    return out


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


def _retrace_ok(
    *,
    gap_pts: float,
    open_0845: float,
    drive_bars: list[KBarRecord],
    retrace_max_frac: float,
) -> bool:
    if not drive_bars:
        return False
    gap_abs = abs(gap_pts)
    if gap_pts > 0:
        min_low = min(float(b.Low) for b in drive_bars)
        floor = open_0845 - gap_abs * retrace_max_frac
        return min_low >= floor
    max_high = max(float(b.High) for b in drive_bars)
    ceiling = open_0845 + gap_abs * retrace_max_frac
    return max_high <= ceiling


def detect_gdc_signal(
    bars: list[KBarRecord],
    ticks: list[tuple[int, float, int, int]],
    *,
    params: GdcParams,
    day: dt.date,
    prior_close: float,
) -> tuple[GdcSignal | None, dict[str, bool]]:
    flags = {
        "gap_qualify": False,
        "retrace_ok": False,
        "break_signal": False,
    }

    open_0845 = _open_0845(bars)
    if open_0845 is None:
        return None, flags

    gap_pts = open_0845 - prior_close
    if abs(gap_pts) < MIN_GAP_PTS:
        return None, flags

    atr_idx = _index_at_close_time(bars, dt.time(9, 14))
    if atr_idx is None:
        return None, flags
    atr = _atr_at_index(bars, atr_idx)

    if abs(gap_pts) < params.gap_k_atr * atr:
        return None, flags
    flags["gap_qualify"] = True

    drive_bars = _drive_window_bars(bars)
    if not _retrace_ok(
        gap_pts=gap_pts,
        open_0845=open_0845,
        drive_bars=drive_bars,
        retrace_max_frac=params.retrace_max_frac,
    ):
        return None, flags
    flags["retrace_ok"] = True

    if not drive_bars:
        return None, flags
    drive_high = max(float(b.High) for b in drive_bars)
    drive_low = min(float(b.Low) for b in drive_bars)
    direction: TradeDir = "Long" if gap_pts > 0 else "Short"

    break_start_ts = int(dt.datetime.combine(day, BREAK_START).timestamp())
    entry_deadline = int(dt.datetime.combine(day, NO_NEW_ENTRY_AFTER).timestamp())

    for ts, price, _, _ in ticks:
        if ts < break_start_ts:
            continue
        if direction == "Long" and price > drive_high:
            flags["break_signal"] = True
            if ts < entry_deadline:
                return (
                    GdcSignal(
                        day=day,
                        params=params,
                        direction=direction,
                        entry_ts=ts,
                        entry_price=price,
                        atr=atr,
                        gap_pts=round(gap_pts, 1),
                        open_0845=open_0845,
                        prior_close=prior_close,
                        drive_high=drive_high,
                        drive_low=drive_low,
                    ),
                    flags,
                )
            return None, flags
        if direction == "Short" and price < drive_low:
            flags["break_signal"] = True
            if ts < entry_deadline:
                return (
                    GdcSignal(
                        day=day,
                        params=params,
                        direction=direction,
                        entry_ts=ts,
                        entry_price=price,
                        atr=atr,
                        gap_pts=round(gap_pts, 1),
                        open_0845=open_0845,
                        prior_close=prior_close,
                        drive_high=drive_high,
                        drive_low=drive_low,
                    ),
                    flags,
                )
            return None, flags

    return None, flags


def simulate_gdc_entry(
    signal: GdcSignal,
    ticks: list[tuple[int, float, int, int]],
    *,
    friction_points: float = FRICTION_POINTS,
    max_hold_sec: int = DEFAULT_MAX_HOLD_SEC,
) -> dict[str, Any]:
    sim = simulate_atr_barrier_exit(
        direction=signal.direction,
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
    slip: dict[str, float] = {}
    for extra in (0, 1, 2):
        slip[str(extra)] = round(gross - friction_points - extra, 2)
    return {
        "day": signal.day.isoformat(),
        "param": signal.params.key(),
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
        "atr_barrier_sim": sim,
        "exit_variant": EXIT_VARIANT,
    }


def scan_gdc_session(
    bars: list[KBarRecord],
    *,
    params: GdcParams,
    day: dt.date,
    prior_close: float | None,
    ticks: list[tuple[int, float, int, int]] | None = None,
    friction_points: float = FRICTION_POINTS,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    funnel: dict[str, int] = {
        "days_with_session": 0,
        "gap_qualify": 0,
        "retrace_ok": 0,
        "break_signal": 0,
        "entry": 0,
    }
    if not bars or prior_close is None:
        return [], funnel

    funnel["days_with_session"] = 1
    if ticks is None:
        return [], funnel

    signal, flags = detect_gdc_signal(
        bars, ticks, params=params, day=day, prior_close=prior_close
    )
    if flags["gap_qualify"]:
        funnel["gap_qualify"] = 1
    if flags["retrace_ok"]:
        funnel["retrace_ok"] = 1
    if flags["break_signal"]:
        funnel["break_signal"] = 1
    if signal is None:
        return [], funnel

    row = simulate_gdc_entry(signal, ticks, friction_points=friction_points)
    funnel["entry"] = 1
    return [row], funnel


def detect_gdc_entries_for_day(
    code: str,
    day: dt.date,
    *,
    cache_dir: Path,
    params: GdcParams,
    sorted_dates: list[dt.date],
    friction_points: float = FRICTION_POINTS,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    empty = _empty_gdc_funnel()
    kpath = resolve_kbar_path(cache_dir, code, day)
    if kpath is None:
        return [], empty

    prior_day = _prior_session_date(day, sorted_dates)
    if prior_day is None:
        return [], empty
    pclose = _prior_close(code, prior_day, cache_dir=cache_dir)
    if pclose is None:
        return [], empty

    bars = _session_bars(load_kbars_csv(kpath))
    ticks = _tick_rows_for_day(code, day, cache_dir=cache_dir)
    return scan_gdc_session(
        bars,
        params=params,
        day=day,
        prior_close=pclose,
        ticks=ticks,
        friction_points=friction_points,
    )


def _empty_gdc_funnel() -> dict[str, int]:
    return {
        "days_with_session": 0,
        "gap_qualify": 0,
        "retrace_ok": 0,
        "break_signal": 0,
        "entry": 0,
    }


def _load_gdc_day_context(
    code: str,
    day: dt.date,
    *,
    cache_dir: Path,
    sorted_dates: list[dt.date],
) -> tuple[list[KBarRecord], list[tuple[int, float, int, int]], float] | None:
    kpath = resolve_kbar_path(cache_dir, code, day)
    if kpath is None:
        return None

    prior_day = _prior_session_date(day, sorted_dates)
    if prior_day is None:
        return None
    pclose = _prior_close(code, prior_day, cache_dir=cache_dir)
    if pclose is None:
        return None

    bars = _session_bars(load_kbars_csv(kpath))
    ticks = _tick_rows_for_day(code, day, cache_dir=cache_dir)
    return bars, ticks, pclose


def _aggregate_funnel(funnels: list[dict[str, int]]) -> dict[str, Any]:
    keys = ("days_with_session", "gap_qualify", "retrace_ok", "break_signal", "entry")
    totals = {k: sum(f.get(k, 0) for f in funnels) for k in keys}
    gq = totals["gap_qualify"]
    totals["gap_to_entry_rate"] = round(totals["entry"] / gq, 4) if gq else None
    return totals


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

    long_rows = [r for r in rows if r["direction"] == "Long"]
    short_rows = [r for r in rows if r["direction"] == "Short"]
    for label, subset in (("long", long_rows), ("short", short_rows)):
        if not subset:
            continue
        sub_net = [float(r["net_atr_sim"]) for r in subset]
        if statistics.mean(sub_net) < -3:
            reasons.append(f"{label}_net_mean_lt_-3")

    total_gross = sum(gross)
    if total_gross > 0:
        for label, subset in (("long", long_rows), ("short", short_rows)):
            side_gross = sum(float(r["gross_atr_sim"]) for r in subset)
            if side_gross / total_gross > 0.80:
                reasons.append(f"{label}_gross_share_gt_80pct")

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


def _iter_param_sets(mode: Literal["fingerprint", "grid"]) -> list[GdcParams]:
    if mode == "fingerprint":
        return [
            GdcParams(
                gap_k_atr=FINGERPRINT_GAP_K_ATR,
                retrace_max_frac=FINGERPRINT_RETRACE_MAX_FRAC,
                k_sl=FINGERPRINT_K_SL,
                tp_atr_k=FINGERPRINT_TP_ATR_K,
            )
        ]
    out: list[GdcParams] = []
    for gk in DEFAULT_GAP_K_ATR:
        for rt in DEFAULT_RETRACE_MAX_FRAC:
            for ks in DEFAULT_K_SL:
                for tp in DEFAULT_TP_ATR_K:
                    out.append(
                        GdcParams(
                            gap_k_atr=gk,
                            retrace_max_frac=rt,
                            k_sl=ks,
                            tp_atr_k=tp,
                        )
                    )
    return out


def build_gdc_payload(
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
            empty = _empty_gdc_funnel()
            for params in param_sets:
                funnel_by_param[params.key()].append(empty)
            continue
        bars, ticks, prior_close = ctx
        for params in param_sets:
            rows, funnel = scan_gdc_session(
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
        funnel_agg[key] = {"totals": _aggregate_funnel(funnel_by_param[key])}

    phase0_gate = _evaluate_phase0_gate_params(summary_by_param)
    fingerprint_gate: dict[str, Any] | None = None
    if mode == "fingerprint" and param_sets:
        fingerprint_gate = _evaluate_fingerprint_gate(
            post_entry_by_param.get(param_sets[0].key(), {})
        )

    outcome: str | None = None
    if mode == "fingerprint" and fingerprint_gate and not fingerprint_gate.get("pass"):
        outcome = "gdc_fingerprint_fail"
    elif mode == "grid" and not phase0_gate.get("pass"):
        outcome = "gdc_fingerprint_pass_g1_fail"
    elif mode == "grid" and phase0_gate.get("pass"):
        best = phase0_gate.get("best_passing") or {}
        best_key = best.get("param")
        if best_key and skew_gate_by_param.get(best_key, {}).get("disqualified"):
            outcome = "gdc_no_skew_champion"

    variant = "gdc_fingerprint_v1" if mode == "fingerprint" else "gdc_grid_v1"

    return {
        "schema_version": SCHEMA_VERSION,
        "thesis": "gap_drive_continuation",
        "thesis_class": THESIS_CLASS,
        "variant": variant,
        "mode": mode,
        "from_date": from_date,
        "to_date": to_date,
        "code": code,
        "friction_points_per_round_trip": friction_points,
        "entry_model": "tick_break_drive_extreme_post_retrace",
        "sim_params": {
            "drive_window_close": f"{DRIVE_CLOSE_START.isoformat()}–{DRIVE_CLOSE_END.isoformat()}",
            "break_entry": f"{BREAK_START.isoformat()}–{NO_NEW_ENTRY_AFTER.isoformat()}",
            "max_trades_per_day": 1,
            "atr_period": GDC_ATR_PERIOD,
            "min_atr_pts": DEFAULT_MIN_ATR,
            "min_gap_pts": MIN_GAP_PTS,
            "exit_variant": EXIT_VARIANT,
            "max_hold_sec": DEFAULT_MAX_HOLD_SEC,
        },
        "fingerprint_params": {
            "gap_k_atr": FINGERPRINT_GAP_K_ATR,
            "retrace_max_frac": FINGERPRINT_RETRACE_MAX_FRAC,
            "k_sl": FINGERPRINT_K_SL,
            "tp_atr_k": FINGERPRINT_TP_ATR_K,
        }
        if mode == "fingerprint"
        else None,
        "fingerprint_gate": fingerprint_gate,
        "phase0_gate": phase0_gate,
        "skew_gate_by_param": skew_gate_by_param,
        "entry_slippage_sensitivity_by_param": slippage_by_param,
        "outcome_hint": outcome,
        "summary_by_param": summary_by_param,
        "post_entry_diagnosis_by_param": post_entry_by_param,
        "funnel_by_param": funnel_agg,
        "entry_count_by_param": {k: len(v) for k, v in all_rows.items()},
        "rows_by_param": all_rows,
    }
