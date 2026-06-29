"""FT-019 Phase 0: Sweep FVG breakout trail (skew) counterfactual."""

from __future__ import annotations

import datetime as dt
import statistics
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal

from reporting.armed_forward_counterfactual import FRICTION_POINTS, _summarize_gross_net
from reporting.forward_pnl import load_tick_series
from reporting.post_entry_diagnosis import (
    enrich_rows_with_forward_windows,
    summarize_post_entry_diagnosis,
)
from reporting.short_breakout_counterfactual import _session_bars
from reporting.simulate_fvg_mid_trail_skew_exit import simulate_fvg_mid_trail_skew_exit
from reporting.volatility_baseline import atr_series_from_bars
from storage.kbar_loader import KBarRecord, load_kbars_csv, resolve_kbar_path
from storage.tick_loader import iter_replay_ticks, resolve_cli_tick_cache_dates
from strategy_vwap_momentum.structure import (
    _FvgZone,
    _apply_fvg_mitigation,
    _detect_fvgs,
    filter_closed_bars_1m,
    resample_time_buckets,
    session_slice_bars_1m,
)

SCHEMA_VERSION = 1
THESIS_CLASS = "skew"
EXIT_VARIANT = "fvg_mid_trail_skew_900s"
STRUCTURE_TF_MIN = 5
SFBT_ATR_PERIOD = 14
MIN_RISK_PTS = 8.0

ENTRY_START = dt.time(9, 15)
NO_NEW_ENTRY_AFTER = dt.time(12, 30)
DEFAULT_MIN_ATR = 25.0
DEFAULT_MAX_HOLD_SEC = 900
FINGERPRINT_WINDOW_SEC = 900

PHASE0_GROSS_MIN = 5.0
PHASE0_NET_MIN = 0.0
PHASE0_MIN_N = 15

FINGERPRINT_SWEEP_LB = 45
FINGERPRINT_SWEEP_K = 0.25
FINGERPRINT_RECLAIM_SEC = 120
FINGERPRINT_SWING_LB = 3
FINGERPRINT_FVG_AGE = 6
FINGERPRINT_BE_RISK = 1.0
FINGERPRINT_TRAIL_ARM_RISK = 2.0
FINGERPRINT_TRAIL_ARM_ATR = 1.5
FINGERPRINT_TRAIL_DIST = 0.5
FINGERPRINT_HARD_TP = 4.0

DEFAULT_SWEEP_LB = (30, 45, 60)
DEFAULT_SWEEP_K = (0.15, 0.25, 0.35)
DEFAULT_RECLAIM_SEC = (60, 120, 180)
DEFAULT_SWING_LB = (3, 5)
DEFAULT_FVG_AGE = (4, 6, 8)
DEFAULT_BE_RISK = (0.75, 1.0)
DEFAULT_TRAIL_ARM_RISK = (1.5, 2.0)
DEFAULT_TRAIL_ARM_ATR = (1.0, 1.5)
DEFAULT_TRAIL_DIST = (0.4, 0.5, 0.6)
DEFAULT_HARD_TP: tuple[float | None, ...] = (None, 3.0, 4.0)

PAYOFF_RATIO_MIN = 2.5
TAIL_GROSS_MIN_PTS = 15.0
MAX_CONSECUTIVE_LOSSES = 10
MAX_CONSECUTIVE_LOSS_PTS = 150.0
WORST_MONTH_NET_PTS = -120.0
TOP3_WIN_GROSS_SHARE_MAX = 0.65


@dataclass(frozen=True)
class SfbtParams:
    sweep_lookback_min: int
    sweep_k: float
    reclaim_window_sec: int
    swing_lookback: int
    max_fvg_age_bars: int
    be_risk_k: float
    trail_arm_risk_k: float
    trail_arm_atr_k: float
    trail_dist_atr_k: float
    hard_tp_risk_k: float | None

    def key(self) -> str:
        sk = f"{self.sweep_k:g}".replace(".", "p")
        be = f"{self.be_risk_k:g}".replace(".", "p")
        tar = f"{self.trail_arm_risk_k:g}".replace(".", "p")
        taa = f"{self.trail_arm_atr_k:g}".replace(".", "p")
        td = f"{self.trail_dist_atr_k:g}".replace(".", "p")
        if self.hard_tp_risk_k is None:
            tp = "none"
        else:
            tp = f"{self.hard_tp_risk_k:g}".replace(".", "p")
        return (
            f"slb{self.sweep_lookback_min}_sk{sk}_rc{self.reclaim_window_sec}_"
            f"sw{self.swing_lookback}_age{self.max_fvg_age_bars}_be{be}_"
            f"tar{tar}_taa{taa}_td{td}_tp{tp}"
        )

    def entry_key(self) -> tuple[int, float, int, int, int]:
        return (
            self.sweep_lookback_min,
            self.sweep_k,
            self.reclaim_window_sec,
            self.swing_lookback,
            self.max_fvg_age_bars,
        )


@dataclass(frozen=True)
class SfbtSignal:
    day: dt.date
    params: SfbtParams
    direction: Literal["Long"]
    entry_ts: int
    entry_price: float
    atr: float
    fvg_low: float
    fvg_high: float
    fvg_mid: float
    sweep_ts: int
    reclaim_ts: int
    swing_low: float


def _empty_sfbt_funnel() -> dict[str, int]:
    return {
        "days_with_session": 0,
        "sweep_signal": 0,
        "reclaim_ok": 0,
        "fvg_active": 0,
        "breakout_signal": 0,
        "entry": 0,
    }


def _bar_close_ts(bar: KBarRecord) -> int:
    return int(bar.ts.timestamp()) + 60


def _atr_at_index(bars: list[KBarRecord], idx: int) -> float:
    tuples = [
        (b.High, b.Low, b.Close, b.High - b.Low, float(b.Volume)) for b in bars[: idx + 1]
    ]
    series = atr_series_from_bars(tuples, period=SFBT_ATR_PERIOD)
    if not series:
        return DEFAULT_MIN_ATR
    return max(float(series[-1]), DEFAULT_MIN_ATR)


def _index_at_close_time(bars: list[KBarRecord], close_t: dt.time) -> int | None:
    for i, bar in enumerate(bars):
        bar_close = (bar.ts + dt.timedelta(minutes=1)).time()
        if bar_close == close_t:
            return i
    return None


def _in_entry_window_ts(ts: int) -> bool:
    t = dt.datetime.fromtimestamp(ts).time()
    return ENTRY_START <= t < NO_NEW_ENTRY_AFTER


def _closed_bars_1m_up_to(bars: list[KBarRecord], as_of_ts: int) -> list[KBarRecord]:
    return [b for b in bars if _bar_close_ts(b) <= as_of_ts]


def _swing_pool(
    bars: list[KBarRecord],
    as_of_ts: int,
    lookback_min: int,
) -> list[tuple[int, float]]:
    closed = _closed_bars_1m_up_to(bars, as_of_ts)
    if len(closed) < 3:
        return []
    window = closed[-lookback_min:] if len(closed) >= lookback_min else closed
    window_ts = {b.ts for b in window}
    out: list[tuple[int, float]] = []
    for i in range(1, len(closed) - 1):
        bar_i = closed[i]
        if bar_i.ts not in window_ts:
            continue
        if bar_i.Low < closed[i - 1].Low and bar_i.Low < closed[i + 1].Low:
            confirm_ts = _bar_close_ts(closed[i + 1])
            if confirm_ts <= as_of_ts:
                out.append((confirm_ts, float(bar_i.Low)))
    return out


def _fvg_created_close_ts(created_ts: dt.datetime) -> int:
    return int(created_ts.timestamp()) + STRUCTURE_TF_MIN * 60


def _fvg_age_bars(created_ts: dt.datetime, exchange_dt: dt.datetime) -> int:
    age = 0
    cursor = created_ts + dt.timedelta(minutes=STRUCTURE_TF_MIN)
    while cursor <= exchange_dt:
        age += 1
        cursor += dt.timedelta(minutes=STRUCTURE_TF_MIN)
    return age


def _price_in_fvg(price: float, fvg_low: float, fvg_high: float) -> bool:
    return fvg_low <= price <= fvg_high


def _qualifying_bullish_fvg(
    bars: list[KBarRecord],
    *,
    as_of_ts: int,
    sweep_ts: int,
    max_fvg_age_bars: int,
) -> dict[str, Any] | None:
    exchange_dt = dt.datetime.fromtimestamp(as_of_ts)
    closed = filter_closed_bars_1m(bars, exchange_dt)
    session_bars = session_slice_bars_1m(closed, exchange_dt, used_long_lookback=False)
    bars_5m = resample_time_buckets(session_bars, STRUCTURE_TF_MIN, exchange_dt)
    zones = _detect_fvgs(bars_5m)
    _apply_fvg_mitigation(zones, bars_5m)

    candidates: list[tuple[int, _FvgZone]] = []
    for zone in zones:
        if zone.side != "bullish" or zone.mitigated:
            continue
        created_close = _fvg_created_close_ts(zone.created_ts)
        if sweep_ts >= created_close:
            continue
        age = _fvg_age_bars(zone.created_ts, exchange_dt)
        if age > max_fvg_age_bars:
            continue
        candidates.append((created_close, zone))

    if not candidates:
        return None

    _, best = max(candidates, key=lambda x: x[0])
    fvg_mid = (best.fvg_low + best.fvg_high) / 2.0
    return {
        "fvg_low": float(best.fvg_low),
        "fvg_high": float(best.fvg_high),
        "fvg_mid": float(fvg_mid),
        "created_ts": _fvg_created_close_ts(best.created_ts),
    }


def _entry_window_ticks(
    ticks: list[tuple[int, float, int, int]],
) -> list[tuple[int, float, int, int]]:
    return [t for t in ticks if _in_entry_window_ts(t[0])]


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


def detect_sfbt_signal(
    bars: list[KBarRecord],
    ticks: list[tuple[int, float, int, int]],
    *,
    params: SfbtParams,
    day: dt.date,
    atr: float,
) -> tuple[SfbtSignal | None, dict[str, bool]]:
    flags: dict[str, bool] = {
        "sweep_signal": False,
        "reclaim_ok": False,
        "fvg_active": False,
        "breakout_signal": False,
    }

    pending_sweep: dict[str, Any] | None = None
    reclaim_ts: int | None = None
    sweep_ts: int | None = None
    swing_low: float | None = None
    linked_fvg: dict[str, Any] | None = None
    last_fvg_refresh_ts: int = 0
    last_swing_scan_ts: int = 0
    cached_swings: list[tuple[int, float]] = []
    entry_done = False

    for ts, price, _vol, _tt in ticks:
        if not _in_entry_window_ts(ts):
            continue
        if entry_done:
            break

        if ts - last_swing_scan_ts >= 60:
            cached_swings = _swing_pool(bars, ts, params.sweep_lookback_min)
            last_swing_scan_ts = ts

        if pending_sweep is not None and reclaim_ts is None:
            deadline = int(pending_sweep["ts"]) + params.reclaim_window_sec
            if ts > deadline:
                pending_sweep = None
                sweep_ts = None
                swing_low = None
                linked_fvg = None

        if pending_sweep is None and reclaim_ts is None:
            for _confirm_ts, low in cached_swings:
                threshold = low - params.sweep_k * atr
                if price < threshold:
                    pending_sweep = {"ts": ts, "L": low}
                    sweep_ts = ts
                    swing_low = low
                    flags["sweep_signal"] = True
                    linked_fvg = None
                    break

        if pending_sweep is not None and reclaim_ts is None and ts > int(pending_sweep["ts"]):
            if price > float(pending_sweep["L"]):
                reclaim_ts = ts
                flags["reclaim_ok"] = True
                linked_fvg = None
                last_fvg_refresh_ts = 0

        if reclaim_ts is not None and sweep_ts is not None and not entry_done:
            if linked_fvg is None or ts - last_fvg_refresh_ts >= STRUCTURE_TF_MIN * 60:
                linked_fvg = _qualifying_bullish_fvg(
                    bars,
                    as_of_ts=ts,
                    sweep_ts=sweep_ts,
                    max_fvg_age_bars=params.max_fvg_age_bars,
                )
                last_fvg_refresh_ts = ts
            fvg_ctx = linked_fvg
            if fvg_ctx is None:
                continue
            flags["fvg_active"] = True

            fl = fvg_ctx["fvg_low"]
            fh = fvg_ctx["fvg_high"]
            fmid = fvg_ctx["fvg_mid"]

            if _price_in_fvg(price, fl, fh):
                continue

            if price > fh:
                flags["breakout_signal"] = True
                risk_unit = price - fmid
                if risk_unit < MIN_RISK_PTS:
                    continue
                entry_done = True
                return (
                    SfbtSignal(
                        day=day,
                        params=params,
                        direction="Long",
                        entry_ts=ts,
                        entry_price=price,
                        atr=atr,
                        fvg_low=fl,
                        fvg_high=fh,
                        fvg_mid=fmid,
                        sweep_ts=sweep_ts,
                        reclaim_ts=reclaim_ts,
                        swing_low=float(swing_low or pending_sweep["L"]),
                    ),
                    flags,
                )

    return None, flags


def simulate_sfbt_entry(
    signal: SfbtSignal,
    ticks: list[tuple[int, float, int, int]],
    *,
    friction_points: float = FRICTION_POINTS,
    max_hold_sec: int = DEFAULT_MAX_HOLD_SEC,
) -> dict[str, Any]:
    sim = simulate_fvg_mid_trail_skew_exit(
        direction=signal.direction,
        entry_price=signal.entry_price,
        entry_ts=signal.entry_ts,
        fvg_mid=signal.fvg_mid,
        atr=signal.atr,
        ticks=ticks,
        be_risk_k=signal.params.be_risk_k,
        trail_arm_risk_k=signal.params.trail_arm_risk_k,
        trail_arm_atr_k=signal.params.trail_arm_atr_k,
        trail_dist_atr_k=signal.params.trail_dist_atr_k,
        hard_tp_risk_k=signal.params.hard_tp_risk_k,
        max_hold_sec=max_hold_sec,
        min_atr_pts=DEFAULT_MIN_ATR,
    )
    gross = float(sim["gross_pnl"])
    net = gross - friction_points
    risk_unit = signal.entry_price - signal.fvg_mid
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
        "fvg_low": round(signal.fvg_low, 1),
        "fvg_high": round(signal.fvg_high, 1),
        "fvg_mid": round(signal.fvg_mid, 1),
        "risk_unit": round(risk_unit, 2),
        "sweep_ts": signal.sweep_ts,
        "reclaim_ts": signal.reclaim_ts,
        "swing_low": round(signal.swing_low, 1),
        "gross_atr_sim": gross,
        "net_atr_sim": net,
        "entry_slippage_sensitivity_pts": slip,
        "fvg_mid_trail_sim": sim,
        "exit_variant": EXIT_VARIANT,
    }


def scan_sfbt_session(
    bars: list[KBarRecord],
    *,
    params: SfbtParams,
    day: dt.date,
    ticks: list[tuple[int, float, int, int]] | None = None,
    friction_points: float = FRICTION_POINTS,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    funnel = _empty_sfbt_funnel()
    if not bars or not any(
        ENTRY_START <= (b.ts + dt.timedelta(minutes=1)).time() < NO_NEW_ENTRY_AFTER for b in bars
    ):
        return [], funnel

    funnel["days_with_session"] = 1
    if ticks is None:
        return [], funnel

    atr_idx = _index_at_close_time(bars, dt.time(9, 14))
    if atr_idx is None:
        return [], funnel
    atr = _atr_at_index(bars, atr_idx)

    signal, flags = detect_sfbt_signal(
        bars, _entry_window_ticks(ticks), params=params, day=day, atr=atr
    )
    if flags["sweep_signal"]:
        funnel["sweep_signal"] = 1
    if flags["reclaim_ok"]:
        funnel["reclaim_ok"] = 1
    if flags["fvg_active"]:
        funnel["fvg_active"] = 1
    if flags["breakout_signal"]:
        funnel["breakout_signal"] = 1

    if signal is None:
        return [], funnel

    row = simulate_sfbt_entry(signal, ticks, friction_points=friction_points)
    funnel["entry"] = 1
    return [row], funnel


def detect_sfbt_entries_for_day(
    code: str,
    day: dt.date,
    *,
    cache_dir: Path,
    params: SfbtParams,
    friction_points: float = FRICTION_POINTS,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    kpath = resolve_kbar_path(cache_dir, code, day)
    if kpath is None:
        return [], _empty_sfbt_funnel()
    bars = _session_bars(load_kbars_csv(kpath))
    ticks = _tick_rows_for_day(code, day, cache_dir=cache_dir)
    return scan_sfbt_session(bars, params=params, day=day, ticks=ticks, friction_points=friction_points)


def _flags_to_funnel(flags: dict[str, bool], *, has_session: bool) -> dict[str, int]:
    funnel = _empty_sfbt_funnel()
    if not has_session:
        return funnel
    funnel["days_with_session"] = 1
    if flags.get("sweep_signal"):
        funnel["sweep_signal"] = 1
    if flags.get("reclaim_ok"):
        funnel["reclaim_ok"] = 1
    if flags.get("fvg_active"):
        funnel["fvg_active"] = 1
    if flags.get("breakout_signal"):
        funnel["breakout_signal"] = 1
    return funnel


def _aggregate_funnel(funnels: list[dict[str, int]]) -> dict[str, Any]:
    keys = (
        "days_with_session",
        "sweep_signal",
        "reclaim_ok",
        "fvg_active",
        "breakout_signal",
        "entry",
    )
    totals = {k: sum(f.get(k, 0) for f in funnels) for k in keys}
    fa = totals["fvg_active"]
    totals["fvg_to_entry_rate"] = round(totals["entry"] / fa, 4) if fa else None
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
        return "sfbt_fingerprint_fail_direction"
    if n < PHASE0_MIN_N and med is not None and float(med) > 0:
        return "sfbt_fingerprint_fail_n"
    if n < PHASE0_MIN_N:
        return "sfbt_fingerprint_fail_n"
    return "sfbt_fingerprint_fail_direction"


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
        return {
            "exit_gap": None,
            "pct_mfe_ge_1atr": None,
            "pct_hit_2R": None,
        }
    mfes: list[float] = []
    grosses: list[float] = []
    mfe_ge_1atr = 0
    hit_2r = 0
    for row in rows:
        sim = row.get("fvg_mid_trail_sim") or {}
        mfe = sim.get("mfe")
        atr = float(row.get("atr") or 0)
        risk_unit = float(row.get("risk_unit") or 0)
        grosses.append(float(row["gross_atr_sim"]))
        if mfe is not None:
            mfes.append(float(mfe))
            if atr > 0 and float(mfe) >= atr:
                mfe_ge_1atr += 1
            if risk_unit > 0 and float(mfe) >= 2.0 * risk_unit:
                hit_2r += 1
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
        "pct_hit_2R": round(hit_2r / len(rows), 4) if rows else None,
        "mfe_median": round(mfe_med, 2) if mfe_med is not None else None,
        "barrier_gross_median": round(gross_med, 2) if gross_med is not None else None,
    }


def _iter_param_sets(mode: Literal["fingerprint", "grid"]) -> list[SfbtParams]:
    if mode == "fingerprint":
        return [
            SfbtParams(
                sweep_lookback_min=FINGERPRINT_SWEEP_LB,
                sweep_k=FINGERPRINT_SWEEP_K,
                reclaim_window_sec=FINGERPRINT_RECLAIM_SEC,
                swing_lookback=FINGERPRINT_SWING_LB,
                max_fvg_age_bars=FINGERPRINT_FVG_AGE,
                be_risk_k=FINGERPRINT_BE_RISK,
                trail_arm_risk_k=FINGERPRINT_TRAIL_ARM_RISK,
                trail_arm_atr_k=FINGERPRINT_TRAIL_ARM_ATR,
                trail_dist_atr_k=FINGERPRINT_TRAIL_DIST,
                hard_tp_risk_k=FINGERPRINT_HARD_TP,
            )
        ]
    out: list[SfbtParams] = []
    for slb in DEFAULT_SWEEP_LB:
        for sk in DEFAULT_SWEEP_K:
            for rc in DEFAULT_RECLAIM_SEC:
                for sw in DEFAULT_SWING_LB:
                    for age in DEFAULT_FVG_AGE:
                        for be in DEFAULT_BE_RISK:
                            for tar in DEFAULT_TRAIL_ARM_RISK:
                                for taa in DEFAULT_TRAIL_ARM_ATR:
                                    for td in DEFAULT_TRAIL_DIST:
                                        for hp in DEFAULT_HARD_TP:
                                            out.append(
                                                SfbtParams(
                                                    sweep_lookback_min=slb,
                                                    sweep_k=sk,
                                                    reclaim_window_sec=rc,
                                                    swing_lookback=sw,
                                                    max_fvg_age_bars=age,
                                                    be_risk_k=be,
                                                    trail_arm_risk_k=tar,
                                                    trail_arm_atr_k=taa,
                                                    trail_dist_atr_k=td,
                                                    hard_tp_risk_k=hp,
                                                )
                                            )
    return out


def _finalize_param_block(
    *,
    key: str,
    rows: list[dict[str, Any]],
    funnel_days: list[dict[str, int]],
    series: Any,
    friction_points: float,
    enrich_forward: bool,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    if rows and enrich_forward and series is not None:
        enrich_rows_with_forward_windows(rows, series)
    summary = {EXIT_VARIANT: _summarize_gross_net("gross_atr_sim", "net_atr_sim", rows)}
    post_entry = summarize_post_entry_diagnosis(rows, friction_points=friction_points)
    skew = _evaluate_skew_gate(rows, friction_points=friction_points)
    slippage = _slippage_sensitivity_summary(rows)
    exit_diag = _exit_diagnostics(rows)
    funnel = {"totals": _aggregate_funnel(funnel_days)}
    return summary, post_entry, skew, slippage, exit_diag, funnel


def build_sfbt_payload(
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
    series = None if mode == "grid" else load_tick_series(code, sorted_dates, cache_dir=cache_dir)
    param_sets = _iter_param_sets(mode)

    summary_by_param: dict[str, Any] = {}
    post_entry_by_param: dict[str, Any] = {}
    skew_gate_by_param: dict[str, Any] = {}
    slippage_by_param: dict[str, Any] = {}
    exit_diag_by_param: dict[str, Any] = {}
    funnel_agg: dict[str, Any] = {}
    all_rows: dict[str, list[dict[str, Any]]] = {}
    entry_count_by_param: dict[str, int] = {}

    if mode == "grid":
        by_entry: dict[tuple[int, float, int, int, int], list[SfbtParams]] = defaultdict(list)
        for params in param_sets:
            by_entry[params.entry_key()].append(params)

        day_ctx: dict[dt.date, dict[str, Any]] = {}
        for day in dates:
            kpath = resolve_kbar_path(cache_dir, code, day)
            if kpath is None:
                day_ctx[day] = {"has_session": False}
                continue
            bars = _session_bars(load_kbars_csv(kpath))
            ticks = _tick_rows_for_day(code, day, cache_dir=cache_dir)
            window_ticks = _entry_window_ticks(ticks)
            atr_idx = _index_at_close_time(bars, dt.time(9, 14)) if bars else None
            if atr_idx is None or not window_ticks:
                day_ctx[day] = {"has_session": False}
                continue
            day_ctx[day] = {
                "has_session": True,
                "bars": bars,
                "ticks": ticks,
                "window_ticks": window_ticks,
                "atr": _atr_at_index(bars, atr_idx),
            }

        for _ek, batch_params in by_entry.items():
            probe = batch_params[0]
            batch_rows = {p.key(): [] for p in batch_params}
            batch_funnel = {p.key(): [] for p in batch_params}
            for day in dates:
                ctx = day_ctx[day]
                if not ctx.get("has_session"):
                    empty = _empty_sfbt_funnel()
                    for params in batch_params:
                        batch_funnel[params.key()].append(empty)
                    continue
                signal, flags = detect_sfbt_signal(
                    ctx["bars"],
                    ctx["window_ticks"],
                    params=probe,
                    day=day,
                    atr=float(ctx["atr"]),
                )
                base_funnel = _flags_to_funnel(flags, has_session=True)
                for params in batch_params:
                    key = params.key()
                    funnel = dict(base_funnel)
                    if signal is not None:
                        bound = replace(signal, params=params)
                        batch_rows[key].append(
                            simulate_sfbt_entry(
                                bound,
                                ctx["ticks"],
                                friction_points=friction_points,
                            )
                        )
                        funnel["entry"] = 1
                    batch_funnel[key].append(funnel)

            for params in batch_params:
                key = params.key()
                rows = batch_rows[key]
                entry_count_by_param[key] = len(rows)
                s, pe, sk, sl, ex, fu = _finalize_param_block(
                    key=key,
                    rows=rows,
                    funnel_days=batch_funnel[key],
                    series=series,
                    friction_points=friction_points,
                    enrich_forward=False,
                )
                summary_by_param[key] = s
                post_entry_by_param[key] = pe
                skew_gate_by_param[key] = sk
                slippage_by_param[key] = sl
                exit_diag_by_param[key] = ex
                funnel_agg[key] = fu
    else:
        all_rows = {p.key(): [] for p in param_sets}
        funnel_by_param: dict[str, list[dict[str, int]]] = {p.key(): [] for p in param_sets}

        for day in dates:
            kpath = resolve_kbar_path(cache_dir, code, day)
            if kpath is None:
                empty = _empty_sfbt_funnel()
                for params in param_sets:
                    funnel_by_param[params.key()].append(empty)
                continue
            bars = _session_bars(load_kbars_csv(kpath))
            ticks = _tick_rows_for_day(code, day, cache_dir=cache_dir)
            for params in param_sets:
                rows, funnel = scan_sfbt_session(
                    bars,
                    params=params,
                    day=day,
                    ticks=ticks,
                    friction_points=friction_points,
                )
                key = params.key()
                all_rows[key].extend(rows)
                funnel_by_param[key].append(funnel)

        for key, rows in all_rows.items():
            entry_count_by_param[key] = len(rows)
            s, pe, sk, sl, ex, fu = _finalize_param_block(
                key=key,
                rows=rows,
                funnel_days=funnel_by_param[key],
                series=series,
                friction_points=friction_points,
                enrich_forward=True,
            )
            summary_by_param[key] = s
            post_entry_by_param[key] = pe
            skew_gate_by_param[key] = sk
            slippage_by_param[key] = sl
            exit_diag_by_param[key] = ex
            funnel_agg[key] = fu

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
        outcome = "sfbt_fingerprint_pass_g1_fail"
    elif mode == "grid" and phase0_gate.get("pass"):
        best = phase0_gate.get("best_passing") or {}
        best_key = best.get("param")
        if best_key and skew_gate_by_param.get(best_key, {}).get("disqualified"):
            outcome = "sfbt_no_skew_champion"

    variant = "sfbt_fingerprint_v1" if mode == "fingerprint" else "sfbt_grid_v1"

    return {
        "schema_version": SCHEMA_VERSION,
        "thesis": "sweep_fvg_breakout_trail",
        "thesis_class": THESIS_CLASS,
        "variant": variant,
        "mode": mode,
        "from_date": from_date,
        "to_date": to_date,
        "code": code,
        "friction_points_per_round_trip": friction_points,
        "entry_model": "sweep_reclaim_fvg_breakout_long_only",
        "sim_params": {
            "entry_window": "09:15–12:30",
            "max_trades_per_day": 1,
            "atr_period": SFBT_ATR_PERIOD,
            "min_atr_pts": DEFAULT_MIN_ATR,
            "min_risk_pts": MIN_RISK_PTS,
            "structure_tf_min": STRUCTURE_TF_MIN,
            "exit_variant": EXIT_VARIANT,
            "max_hold_sec": DEFAULT_MAX_HOLD_SEC,
            "fingerprint_window_sec": FINGERPRINT_WINDOW_SEC,
        },
        "fingerprint_params": {
            "sweep_lookback_min": FINGERPRINT_SWEEP_LB,
            "sweep_k": FINGERPRINT_SWEEP_K,
            "reclaim_window_sec": FINGERPRINT_RECLAIM_SEC,
            "swing_lookback": FINGERPRINT_SWING_LB,
            "max_fvg_age_bars": FINGERPRINT_FVG_AGE,
            "be_risk_k": FINGERPRINT_BE_RISK,
            "trail_arm_risk_k": FINGERPRINT_TRAIL_ARM_RISK,
            "trail_arm_atr_k": FINGERPRINT_TRAIL_ARM_ATR,
            "trail_dist_atr_k": FINGERPRINT_TRAIL_DIST,
            "hard_tp_risk_k": FINGERPRINT_HARD_TP,
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
        "entry_count_by_param": entry_count_by_param,
        "rows_by_param": all_rows if mode == "fingerprint" else {},
    }
