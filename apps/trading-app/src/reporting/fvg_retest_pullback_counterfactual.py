"""FT-015 Phase 0: FVG retest pullback (skew) counterfactual."""

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
from reporting.structure_calibration import compute_structure_snapshot
from reporting.volatility_baseline import atr_series_from_bars, percentile
from storage.kbar_loader import KBarRecord, load_kbars_csv, resolve_kbar_path
from storage.tick_loader import iter_replay_ticks, resolve_cli_tick_cache_dates
from strategy_vwap_momentum.structure import (
    StructureParams,
    _apply_fvg_mitigation,
    _detect_fvgs,
    _select_active_fvg,
    filter_closed_bars_1m,
    resample_time_buckets,
    session_slice_bars_1m,
)

SCHEMA_VERSION = 1
THESIS_CLASS = "skew"
FRP_ATR_PERIOD = 14

ENTRY_START = dt.time(9, 15)
NO_NEW_ENTRY_AFTER = dt.time(12, 30)
DEFAULT_MIN_ATR = 25.0
DEFAULT_MAX_HOLD_SEC = 900
EXIT_VARIANT = "atr_barrier_900s"
STRUCTURE_TF_MIN = 5

PHASE0_GROSS_MIN = 5.0
PHASE0_NET_MIN = 0.0
PHASE0_MIN_N = 15  # G3S skew

DEFAULT_SWING_LOOKBACK = (3, 5)
DEFAULT_MAX_FVG_AGE_BARS = (6, 12)
DEFAULT_VOL_PCT_MAX = (0.40,)
DEFAULT_K_SL = (0.75, 1.0, 1.25)
DEFAULT_TP_ATR_K = (1.5, 2.0, 2.5)

FINGERPRINT_SWING_LOOKBACK = 3
FINGERPRINT_MAX_FVG_AGE_BARS = 6
FINGERPRINT_VOL_PCT_MAX = 0.40
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
class FrpParams:
    swing_lookback: int
    max_fvg_age_bars: int
    vol_pct_max: float
    k_sl: float
    tp_atr_k: float

    def key(self) -> str:
        vp = f"{self.vol_pct_max:g}".replace(".", "p")
        ks = f"{self.k_sl:g}".replace(".", "p")
        tp = f"{self.tp_atr_k:g}".replace(".", "p")
        return f"sl{self.swing_lookback}_age{self.max_fvg_age_bars}_vp{vp}_ksl{ks}_tp{tp}"


@dataclass(frozen=True)
class FrpSignal:
    day: dt.date
    params: FrpParams
    direction: TradeDir
    entry_ts: int
    entry_price: float
    atr: float
    fvg_low: float
    fvg_high: float
    bos_ts: int
    fvg_age_bars: int
    vol_1s: int


def _atr_at_index(bars: list[KBarRecord], idx: int) -> float:
    tuples = [
        (b.High, b.Low, b.Close, b.High - b.Low, float(b.Volume)) for b in bars[: idx + 1]
    ]
    series = atr_series_from_bars(tuples, period=FRP_ATR_PERIOD)
    if not series:
        return DEFAULT_MIN_ATR
    return max(float(series[-1]), DEFAULT_MIN_ATR)


def _in_entry_window_ts(ts: int) -> bool:
    t = dt.datetime.fromtimestamp(ts).time()
    return ENTRY_START <= t < NO_NEW_ENTRY_AFTER


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


def _vol_1s_by_second(ticks: list[tuple[int, float, int, int]]) -> dict[int, int]:
    out: dict[int, int] = {}
    for ts, _, vol, _ in ticks:
        out[ts] = out.get(ts, 0) + vol
    return out


def _vol_threshold(samples: list[int], pct_max: float) -> float:
    if not samples:
        return float("inf")
    ordered = sorted(float(v) for v in samples)
    return percentile(ordered, pct_max)


def _fvg_age_bars(created_ts: dt.datetime, exchange_dt: dt.datetime) -> int:
    age = 0
    cursor = created_ts + dt.timedelta(minutes=STRUCTURE_TF_MIN)
    while cursor <= exchange_dt:
        age += 1
        cursor += dt.timedelta(minutes=STRUCTURE_TF_MIN)
    return age


def _active_fvg_context(
    bars: list[KBarRecord],
    *,
    atr: float,
    as_of_ts: int,
    swing_lookback: int,
) -> dict[str, Any] | None:
    params = StructureParams(structure_swing_lookback=swing_lookback)
    state = compute_structure_snapshot(bars, atr=atr, as_of_ts=as_of_ts, params=params)
    if (
        state.active_fvg_low is None
        or state.active_fvg_high is None
        or state.last_bos is None
        or state.last_bos_ts is None
        or state.bias == "Neutral"
    ):
        return None

    exchange_dt = dt.datetime.fromtimestamp(as_of_ts)
    closed = filter_closed_bars_1m(bars, exchange_dt)
    session_bars = session_slice_bars_1m(closed, exchange_dt, used_long_lookback=False)
    bars_5m = resample_time_buckets(session_bars, STRUCTURE_TF_MIN, exchange_dt)
    zones = _detect_fvgs(bars_5m)
    _apply_fvg_mitigation(zones, bars_5m)
    active = _select_active_fvg(zones, state.bias)
    if active is None:
        return None

    bos_ts = int(state.last_bos_ts.timestamp())
    if bos_ts > as_of_ts:
        return None

    age = _fvg_age_bars(active.created_ts, exchange_dt)
    direction: TradeDir = "Long" if state.last_bos == "bullish" else "Short"
    return {
        "direction": direction,
        "fvg_low": float(state.active_fvg_low),
        "fvg_high": float(state.active_fvg_high),
        "bos_ts": bos_ts,
        "fvg_age_bars": age,
        "last_bos": state.last_bos,
    }


def _price_in_fvg(price: float, fvg_low: float, fvg_high: float) -> bool:
    return fvg_low <= price <= fvg_high


def detect_frp_signal(
    bars: list[KBarRecord],
    ticks: list[tuple[int, float, int, int]],
    *,
    params: FrpParams,
    day: dt.date,
) -> tuple[FrpSignal | None, dict[str, bool]]:
    flags = {
        "bos_active_fvg": False,
        "zone_touch": False,
        "vol_ok": False,
    }
    if len(bars) < FRP_ATR_PERIOD + 5 or not ticks:
        return None, flags

    vol_by_sec = _vol_1s_by_second(ticks)
    vol_samples: list[int] = []
    atr = _atr_at_index(bars, len(bars) - 1)

    window_ticks = [(ts, price, vol, tt) for ts, price, vol, tt in ticks if _in_entry_window_ts(ts)]
    if not window_ticks:
        return None, flags

    by_minute: dict[int, list[tuple[int, float, int, int]]] = {}
    for row in window_ticks:
        minute_key = row[0] // 60
        by_minute.setdefault(minute_key, []).append(row)

    for minute_key in sorted(by_minute.keys()):
        chunk = sorted(by_minute[minute_key], key=lambda r: r[0])
        as_of_ts = chunk[-1][0]
        ctx = _active_fvg_context(
            bars,
            atr=atr,
            as_of_ts=as_of_ts,
            swing_lookback=params.swing_lookback,
        )
        if ctx is None:
            for ts, _, tick_vol, _ in chunk:
                vol_samples.append(vol_by_sec.get(ts, tick_vol))
            continue
        if ctx["fvg_age_bars"] > params.max_fvg_age_bars:
            for ts, _, tick_vol, _ in chunk:
                vol_samples.append(vol_by_sec.get(ts, tick_vol))
            continue
        flags["bos_active_fvg"] = True

        for ts, price, tick_vol, _ in chunk:
            vol_samples.append(vol_by_sec.get(ts, tick_vol))
            if not _price_in_fvg(price, ctx["fvg_low"], ctx["fvg_high"]):
                continue
            flags["zone_touch"] = True

            threshold = _vol_threshold(vol_samples[:-1], params.vol_pct_max)
            vol_1s = vol_by_sec.get(ts, tick_vol)
            if float(vol_1s) > threshold:
                continue
            flags["vol_ok"] = True

            return (
                FrpSignal(
                    day=day,
                    params=params,
                    direction=ctx["direction"],
                    entry_ts=ts,
                    entry_price=price,
                    atr=atr,
                    fvg_low=ctx["fvg_low"],
                    fvg_high=ctx["fvg_high"],
                    bos_ts=ctx["bos_ts"],
                    fvg_age_bars=int(ctx["fvg_age_bars"]),
                    vol_1s=int(vol_1s),
                ),
                flags,
            )

    return None, flags


def simulate_frp_entry(
    signal: FrpSignal,
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
    return {
        "day": signal.day.isoformat(),
        "param": signal.params.key(),
        "direction": signal.direction,
        "ts": signal.entry_ts,
        "entry_price": round(signal.entry_price, 1),
        "atr": round(signal.atr, 2),
        "fvg_low": round(signal.fvg_low, 1),
        "fvg_high": round(signal.fvg_high, 1),
        "bos_ts": signal.bos_ts,
        "fvg_age_bars": signal.fvg_age_bars,
        "vol_1s": signal.vol_1s,
        "gross_atr_sim": gross,
        "net_atr_sim": net,
        "atr_barrier_sim": sim,
        "exit_variant": EXIT_VARIANT,
    }


def scan_frp_session(
    bars: list[KBarRecord],
    *,
    params: FrpParams,
    day: dt.date,
    ticks: list[tuple[int, float, int, int]] | None = None,
    friction_points: float = FRICTION_POINTS,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    funnel: dict[str, int] = {
        "days_with_session": 0,
        "bos_active_fvg": 0,
        "zone_touch": 0,
        "vol_ok": 0,
        "entry": 0,
    }
    if not bars or not any(
        ENTRY_START <= (b.ts + dt.timedelta(minutes=1)).time() < NO_NEW_ENTRY_AFTER for b in bars
    ):
        return [], funnel

    funnel["days_with_session"] = 1
    if ticks is None:
        return [], funnel

    signal, flags = detect_frp_signal(bars, ticks, params=params, day=day)
    if flags["bos_active_fvg"]:
        funnel["bos_active_fvg"] = 1
    if flags["zone_touch"]:
        funnel["zone_touch"] = 1
    if flags["vol_ok"]:
        funnel["vol_ok"] = 1
    if signal is None:
        return [], funnel

    row = simulate_frp_entry(signal, ticks, friction_points=friction_points)
    funnel["entry"] = 1
    return [row], funnel


def detect_frp_entries_for_day(
    code: str,
    day: dt.date,
    *,
    cache_dir: Path,
    params: FrpParams,
    friction_points: float = FRICTION_POINTS,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    empty = {
        "days_with_session": 0,
        "bos_active_fvg": 0,
        "zone_touch": 0,
        "vol_ok": 0,
        "entry": 0,
    }
    kpath = resolve_kbar_path(cache_dir, code, day)
    if kpath is None:
        return [], empty
    bars = _session_bars(load_kbars_csv(kpath))
    ticks = _tick_rows_for_day(code, day, cache_dir=cache_dir)
    return scan_frp_session(bars, params=params, day=day, ticks=ticks, friction_points=friction_points)


def _aggregate_funnel(funnels: list[dict[str, int]]) -> dict[str, Any]:
    keys = ("days_with_session", "bos_active_fvg", "zone_touch", "vol_ok", "entry")
    totals = {k: sum(f.get(k, 0) for f in funnels) for k in keys}
    baf = totals["bos_active_fvg"]
    totals["bos_to_entry_rate"] = round(totals["entry"] / baf, 4) if baf else None
    zt = totals["zone_touch"]
    totals["touch_to_entry_rate"] = round(totals["entry"] / zt, 4) if zt else None
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


def _iter_param_sets(mode: Literal["fingerprint", "grid"]) -> list[FrpParams]:
    if mode == "fingerprint":
        return [
            FrpParams(
                swing_lookback=FINGERPRINT_SWING_LOOKBACK,
                max_fvg_age_bars=FINGERPRINT_MAX_FVG_AGE_BARS,
                vol_pct_max=FINGERPRINT_VOL_PCT_MAX,
                k_sl=FINGERPRINT_K_SL,
                tp_atr_k=FINGERPRINT_TP_ATR_K,
            )
        ]
    out: list[FrpParams] = []
    for sl in DEFAULT_SWING_LOOKBACK:
        for age in DEFAULT_MAX_FVG_AGE_BARS:
            for vp in DEFAULT_VOL_PCT_MAX:
                for ks in DEFAULT_K_SL:
                    for tp in DEFAULT_TP_ATR_K:
                        out.append(
                            FrpParams(
                                swing_lookback=sl,
                                max_fvg_age_bars=age,
                                vol_pct_max=vp,
                                k_sl=ks,
                                tp_atr_k=tp,
                            )
                        )
    return out


def build_frp_payload(
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
            rows, funnel = detect_frp_entries_for_day(
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
    skew_gate_by_param: dict[str, Any] = {}
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
        funnel_agg[key] = {"totals": _aggregate_funnel(funnel_by_param[key])}

    phase0_gate = _evaluate_phase0_gate_params(summary_by_param)
    fingerprint_gate: dict[str, Any] | None = None
    if mode == "fingerprint" and param_sets:
        fingerprint_gate = _evaluate_fingerprint_gate(
            post_entry_by_param.get(param_sets[0].key(), {})
        )

    outcome: str | None = None
    if mode == "fingerprint" and fingerprint_gate and not fingerprint_gate.get("pass"):
        outcome = "frp_fingerprint_fail"
    elif mode == "grid" and not phase0_gate.get("pass"):
        outcome = "frp_fingerprint_pass_g1_fail"
    elif mode == "grid" and phase0_gate.get("pass"):
        best = phase0_gate.get("best_passing") or {}
        best_key = best.get("param")
        if best_key and skew_gate_by_param.get(best_key, {}).get("disqualified"):
            outcome = "frp_no_skew_champion"

    variant = "frp_fingerprint_v1" if mode == "fingerprint" else "frp_grid_v1"

    return {
        "schema_version": SCHEMA_VERSION,
        "thesis": "fvg_retest_pullback",
        "thesis_class": THESIS_CLASS,
        "variant": variant,
        "mode": mode,
        "from_date": from_date,
        "to_date": to_date,
        "code": code,
        "friction_points_per_round_trip": friction_points,
        "entry_model": "tick_in_fvg_zone_vol_1s_p40",
        "sim_params": {
            "entry_window": f"{ENTRY_START.isoformat()}–{NO_NEW_ENTRY_AFTER.isoformat()}",
            "max_trades_per_day": 1,
            "atr_period": FRP_ATR_PERIOD,
            "min_atr_pts": DEFAULT_MIN_ATR,
            "structure_tf_min": STRUCTURE_TF_MIN,
            "exit_variant": EXIT_VARIANT,
            "max_hold_sec": DEFAULT_MAX_HOLD_SEC,
        },
        "fingerprint_params": {
            "swing_lookback": FINGERPRINT_SWING_LOOKBACK,
            "max_fvg_age_bars": FINGERPRINT_MAX_FVG_AGE_BARS,
            "vol_pct_max": FINGERPRINT_VOL_PCT_MAX,
            "k_sl": FINGERPRINT_K_SL,
            "tp_atr_k": FINGERPRINT_TP_ATR_K,
        }
        if mode == "fingerprint"
        else None,
        "fingerprint_gate": fingerprint_gate,
        "phase0_gate": phase0_gate,
        "skew_gate_by_param": skew_gate_by_param,
        "outcome_hint": outcome,
        "summary_by_param": summary_by_param,
        "post_entry_diagnosis_by_param": post_entry_by_param,
        "funnel_by_param": funnel_agg,
        "entry_count_by_param": {k: len(v) for k, v in all_rows.items()},
        "rows_by_param": all_rows,
    }
