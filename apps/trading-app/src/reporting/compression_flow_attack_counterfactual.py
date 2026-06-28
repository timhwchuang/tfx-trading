"""FT-017 Phase 0: Compression flow attack (skew) counterfactual."""

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
from reporting.flow_flip_counterfactual import RollingFlowWindow
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

SESSION_START = dt.time(8, 45)
SESSION_END = dt.time(13, 45)
REGIME_MEDIAN_START = dt.time(9, 15)
ENTRY_WINDOW_START = dt.time(10, 0)
NO_NEW_ENTRY_AFTER = dt.time(12, 30)

COMPRESS_LOOKBACK_MIN = 30
ATR_PERIOD = 20
ATR_COMPRESS_FLOOR = 10.0
QUIET_WINDOW_SEC = 60
ATTACK_WINDOW_SEC = 60
VOL_FLOOR_MIN = 30
MIN_STOP_PTS = 8.0
DEFAULT_MIN_ATR = 25.0
DEFAULT_MAX_HOLD_SEC = 900
EXIT_VARIANT = "atr_barrier_900s"

PHASE0_GROSS_MIN = 5.0
PHASE0_NET_MIN = 0.0
PHASE0_MIN_N = 15

DEFAULT_COMPRESS_K = (0.35, 0.45, 0.55)
DEFAULT_ATR_REGIME_CAP = (0.70, 0.75)
DEFAULT_ATTACK_RATIO_MIN = (0.62, 0.68, 0.74)
DEFAULT_MIN_STOP_ATR_K = (0.75, 1.0, 1.25)
DEFAULT_TP_ATR_K = (1.5, 2.0, 2.5)

FINGERPRINT_COMPRESS_K = 0.45
FINGERPRINT_ATR_REGIME_CAP = 0.75
FINGERPRINT_ATTACK_RATIO_MIN = 0.68
FINGERPRINT_MIN_STOP_ATR_K = 0.75
FINGERPRINT_TP_ATR_K = 2.0

PAYOFF_RATIO_MIN = 2.5
TAIL_GROSS_MIN_PTS = 15.0
MAX_CONSECUTIVE_LOSSES = 10
MAX_CONSECUTIVE_LOSS_PTS = 150.0
WORST_MONTH_NET_PTS = -120.0
TOP3_WIN_GROSS_SHARE_MAX = 0.65

TradeDir = Literal["Long", "Short"]


@dataclass(frozen=True)
class CfaParams:
    compress_k: float
    atr_regime_cap: float
    attack_ratio_min: float
    min_stop_atr_k: float
    tp_atr_k: float

    def key(self) -> str:
        ck = f"{self.compress_k:g}".replace(".", "p")
        rc = f"{self.atr_regime_cap:g}".replace(".", "p")
        ar = f"{self.attack_ratio_min:g}".replace(".", "p")
        ms = f"{self.min_stop_atr_k:g}".replace(".", "p")
        tp = f"{self.tp_atr_k:g}".replace(".", "p")
        return f"ck{ck}_rc{rc}_ar{ar}_ms{ms}_tp{tp}"


@dataclass(frozen=True)
class CfaSignal:
    day: dt.date
    params: CfaParams
    direction: TradeDir
    trigger_ts: int
    entry_ts: int
    entry_price: float
    atr_ref: float
    atr_effective: float
    stop_dist_pts: float
    signal_1m_low: float
    signal_1m_high: float
    range_m: float
    buy_ratio_mean: float
    attack_vol: int


def _bar_close_time(bar: KBarRecord) -> dt.time:
    return (bar.ts + dt.timedelta(minutes=1)).time()


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


def _atr_at_bar_index(bars: list[KBarRecord], idx: int) -> float:
    tuples = [
        (b.High, b.Low, b.Close, b.High - b.Low, float(b.Volume))
        for b in bars[: idx + 1]
    ]
    series = atr_series_from_bars(tuples, period=ATR_PERIOD)
    if not series:
        return ATR_COMPRESS_FLOOR
    return float(series[-1])


def _atr_series(bars: list[KBarRecord]) -> list[float]:
    return [_atr_at_bar_index(bars, i) for i in range(len(bars))]


def _last_closed_bar_index(bars: list[KBarRecord], ts: int) -> int | None:
    """Index of last fully closed 1m bar at unix ts."""
    best: int | None = None
    for i, bar in enumerate(bars):
        close_ts = int((bar.ts + dt.timedelta(minutes=1)).timestamp())
        if close_ts <= ts:
            best = i
        else:
            break
    return best


def _session_atr_median_so_far(bars: list[KBarRecord], atrs: list[float], idx: int) -> float:
    vals: list[float] = []
    for i in range(idx + 1):
        ct = _bar_close_time(bars[i])
        if REGIME_MEDIAN_START <= ct <= SESSION_END:
            vals.append(float(atrs[i]))
    return statistics.median(vals) if vals else float(atrs[idx])


def _range_over_lookback(bars: list[KBarRecord], end_idx: int, lookback: int) -> float:
    start = max(0, end_idx - lookback + 1)
    window = bars[start : end_idx + 1]
    if not window:
        return 0.0
    return max(float(b.High) for b in window) - min(float(b.Low) for b in window)


def evaluate_compress_regime(
    bars: list[KBarRecord],
    atrs: list[float],
    signal_idx: int,
    *,
    params: CfaParams,
) -> tuple[bool, bool, float, float]:
    """MUST-1 at signal_1m (sealed eval point A)."""
    if signal_idx < COMPRESS_LOOKBACK_MIN - 1:
        return False, False, 0.0, 0.0
    atr_ref = float(atrs[signal_idx])
    atr_for_compress = max(atr_ref, ATR_COMPRESS_FLOOR)
    range_m = _range_over_lookback(bars, signal_idx, COMPRESS_LOOKBACK_MIN)
    compress_pass = range_m < params.compress_k * atr_for_compress
    session_med = _session_atr_median_so_far(bars, atrs, signal_idx)
    regime_pass = atr_ref < params.atr_regime_cap * session_med
    return compress_pass, regime_pass, atr_ref, range_m


def _mean_vol_1s(sec_vol: dict[int, int], start_ts: int, end_ts: int) -> float:
    """Mean vol_1s over every second in [start_ts, end_ts] (zeros included)."""
    if end_ts < start_ts:
        return 0.0
    span = end_ts - start_ts + 1
    total = sum(sec_vol.get(sec, 0) for sec in range(start_ts, end_ts + 1))
    return total / span


def _session_vol_samples_to(
    sec_vol: dict[int, int], *, end_ts: int, session_start_ts: int
) -> list[float]:
    """One vol_1s sample per elapsed session second (no per-tick duplication)."""
    if end_ts < session_start_ts:
        return []
    return [float(sec_vol.get(sec, 0)) for sec in range(session_start_ts, end_ts + 1)]


def _quiet_passes_from_samples(
    sec_vol: dict[int, int],
    session_vols: list[float],
    end_ts: int,
    *,
    session_start_ts: int,
) -> bool:
    start_ts = end_ts - QUIET_WINDOW_SEC + 1
    mean_v = _mean_vol_1s(sec_vol, start_ts, end_ts)
    idx_end = end_ts - session_start_ts
    if idx_end < 0 or not session_vols:
        return False
    subset = session_vols[: idx_end + 1]
    p50 = _percentile(subset, 50.0)
    return mean_v <= p50


def _quiet_passes(
    sec_vol: dict[int, int],
    session_start_ts: int,
    end_ts: int,
) -> bool:
    session_vols = _session_vol_samples_to(
        sec_vol, end_ts=end_ts, session_start_ts=session_start_ts
    )
    return _quiet_passes_from_samples(
        sec_vol, session_vols, end_ts, session_start_ts=session_start_ts
    )


def _vol_floor_from_samples(
    session_vols: list[float], *, end_ts: int, session_start_ts: int
) -> int:
    idx_end = end_ts - session_start_ts
    subset = session_vols[: idx_end + 1] if idx_end >= 0 else []
    p60 = _percentile(subset, 60.0) if subset else 0.0
    return max(VOL_FLOOR_MIN, int(round(p60)))


def _vol_floor(sec_vol: dict[int, int], *, end_ts: int, session_start_ts: int) -> int:
    session_vols = _session_vol_samples_to(
        sec_vol, end_ts=end_ts, session_start_ts=session_start_ts
    )
    return _vol_floor_from_samples(
        session_vols, end_ts=end_ts, session_start_ts=session_start_ts
    )


def _attack_direction(
    attack_flow: RollingFlowWindow,
    *,
    attack_ratio_min: float,
    vol_floor: int,
) -> TradeDir | None:
    total = attack_flow.total_vol
    if total < vol_floor:
        return None
    if attack_flow.buy_ratio >= attack_ratio_min:
        return "Long"
    if attack_flow.sell_ratio >= attack_ratio_min:
        return "Short"
    return None


def detect_cfa_signal(
    bars: list[KBarRecord],
    ticks: list[tuple[int, float, int, int]],
    *,
    params: CfaParams,
    day: dt.date,
) -> tuple[CfaSignal | None, dict[str, bool]]:
    flags = {
        "compress_pass": False,
        "regime_pass": False,
        "quiet_pass": False,
        "attack_signal": False,
    }
    if not bars or not ticks:
        return None, flags

    atrs = _atr_series(bars)
    if len(atrs) != len(bars):
        return None, flags

    entry_start_ts = int(dt.datetime.combine(day, ENTRY_WINDOW_START).timestamp())
    entry_deadline_ts = int(dt.datetime.combine(day, NO_NEW_ENTRY_AFTER).timestamp())
    session_start_ts = int(dt.datetime.combine(day, SESSION_START).timestamp())

    sec_vol: dict[int, int] = {}
    session_vol_samples: list[float] = []
    last_finalized_sec = session_start_ts - 1
    last_quiet_check_ts: int | None = None

    pending_attack_end: int | None = None
    attack_flow: RollingFlowWindow | None = None
    attack_window_start_ts: int | None = None

    def _finalize_seconds_through(ts: int) -> None:
        nonlocal last_finalized_sec
        while last_finalized_sec < ts:
            last_finalized_sec += 1
            session_vol_samples.append(float(sec_vol.get(last_finalized_sec, 0)))

    def _finalize_attack(trigger_ts: int, flow: RollingFlowWindow) -> CfaSignal | None:
        nonlocal flags
        if trigger_ts >= entry_deadline_ts:
            return None
        if attack_window_start_ts is not None and attack_window_start_ts < entry_start_ts:
            return None

        direction = _attack_direction(
            flow,
            attack_ratio_min=params.attack_ratio_min,
            vol_floor=_vol_floor_from_samples(
                session_vol_samples,
                end_ts=trigger_ts,
                session_start_ts=session_start_ts,
            ),
        )
        if direction is None:
            return None

        # MUST-4: attack_signal = ratio+vol only (independent of compress/regime).
        flags["attack_signal"] = True

        signal_idx = _last_closed_bar_index(bars, trigger_ts)
        if signal_idx is None:
            return None

        compress_ok, regime_ok, atr_ref, range_m = evaluate_compress_regime(
            bars, atrs, signal_idx, params=params
        )
        if compress_ok:
            flags["compress_pass"] = True
        if regime_ok:
            flags["regime_pass"] = True
        if not (compress_ok and regime_ok):
            return None

        atr_effective = max(atr_ref, DEFAULT_MIN_ATR)
        signal_bar = bars[signal_idx]

        entry_ts: int | None = None
        entry_price: float | None = None
        for tick_ts, price, _, _ in ticks:
            if tick_ts > trigger_ts:
                entry_ts = tick_ts
                entry_price = price
                break
        if entry_ts is None or entry_price is None:
            return None
        if entry_ts >= entry_deadline_ts:
            return None

        if direction == "Long":
            struct_dist = entry_price - float(signal_bar.Low)
        else:
            struct_dist = float(signal_bar.High) - entry_price
        stop_dist = max(struct_dist, params.min_stop_atr_k * atr_effective)
        if stop_dist < MIN_STOP_PTS:
            return None

        return CfaSignal(
            day=day,
            params=params,
            direction=direction,
            trigger_ts=trigger_ts,
            entry_ts=entry_ts,
            entry_price=entry_price,
            atr_ref=atr_ref,
            atr_effective=atr_effective,
            stop_dist_pts=stop_dist,
            signal_1m_low=float(signal_bar.Low),
            signal_1m_high=float(signal_bar.High),
            range_m=range_m,
            buy_ratio_mean=round(flow.buy_ratio, 4),
            attack_vol=flow.total_vol,
        )

    for ts, price, volume, tick_type in ticks:
        sec_vol[ts] = sec_vol.get(ts, 0) + volume
        _finalize_seconds_through(ts)

        if pending_attack_end is not None and attack_flow is not None:
            if ts <= pending_attack_end:
                attack_flow.push(ts, volume, tick_type)
                continue
            sig = _finalize_attack(pending_attack_end, attack_flow)
            pending_attack_end = None
            attack_flow = None
            attack_window_start_ts = None
            if sig is not None:
                return sig, flags

        if ts < entry_start_ts:
            continue

        if pending_attack_end is not None:
            continue

        if last_quiet_check_ts == ts:
            continue
        last_quiet_check_ts = ts

        quiet_end = ts
        if _quiet_passes_from_samples(
            sec_vol,
            session_vol_samples,
            quiet_end,
            session_start_ts=session_start_ts,
        ):
            flags["quiet_pass"] = True
            pending_attack_end = quiet_end + ATTACK_WINDOW_SEC
            attack_window_start_ts = quiet_end + 1
            attack_flow = RollingFlowWindow(ATTACK_WINDOW_SEC)

    if pending_attack_end is not None and attack_flow is not None:
        sig = _finalize_attack(pending_attack_end, attack_flow)
        if sig is not None:
            return sig, flags

    return None, flags


def simulate_cfa_entry(
    signal: CfaSignal,
    ticks: list[tuple[int, float, int, int]],
    *,
    friction_points: float = FRICTION_POINTS,
    max_hold_sec: int = DEFAULT_MAX_HOLD_SEC,
) -> dict[str, Any]:
    effective_k = signal.stop_dist_pts / signal.atr_effective
    sim = simulate_atr_barrier_exit(
        direction=signal.direction,
        entry_price=signal.entry_price,
        armed_ts=signal.entry_ts,
        atr=signal.atr_effective,
        ticks=ticks,
        hard_stop_atr_k=effective_k,
        tp_atr_k=signal.params.tp_atr_k,
        max_hold_sec=max_hold_sec,
    )
    gross = float(sim["gross_pnl"])
    net = gross - friction_points
    slip: dict[str, float] = {}
    for extra in (0, 1, 2):
        slip[str(extra)] = round(gross - friction_points - extra, 2)
    slippage_pts = 0.0
    slippage_ratio = (
        round(slippage_pts / signal.stop_dist_pts, 4) if signal.stop_dist_pts > 0 else None
    )
    return {
        "day": signal.day.isoformat(),
        "param": signal.params.key(),
        "direction": signal.direction,
        "trigger_ts": signal.trigger_ts,
        "ts": signal.entry_ts,
        "entry_price": round(signal.entry_price, 1),
        "atr_ref": round(signal.atr_ref, 2),
        "atr_effective": round(signal.atr_effective, 2),
        "stop_dist_pts": round(signal.stop_dist_pts, 2),
        "slippage_ratio": slippage_ratio,
        "signal_1m_low": round(signal.signal_1m_low, 1),
        "signal_1m_high": round(signal.signal_1m_high, 1),
        "range_m": round(signal.range_m, 2),
        "buy_ratio_mean": signal.buy_ratio_mean,
        "attack_vol": signal.attack_vol,
        "gross_atr_sim": gross,
        "net_atr_sim": net,
        "entry_slippage_sensitivity_pts": slip,
        "atr_barrier_sim": sim,
        "exit_variant": EXIT_VARIANT,
    }


def scan_cfa_session(
    bars: list[KBarRecord],
    *,
    params: CfaParams,
    day: dt.date,
    ticks: list[tuple[int, float, int, int]] | None = None,
    friction_points: float = FRICTION_POINTS,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    funnel: dict[str, int] = {
        "days_with_session": 0,
        "compress_pass": 0,
        "regime_pass": 0,
        "quiet_pass": 0,
        "attack_signal": 0,
        "entry": 0,
    }
    if not bars:
        return [], funnel

    funnel["days_with_session"] = 1
    if ticks is None:
        return [], funnel

    signal, flags = detect_cfa_signal(bars, ticks, params=params, day=day)
    if flags["compress_pass"]:
        funnel["compress_pass"] = 1
    if flags["regime_pass"]:
        funnel["regime_pass"] = 1
    if flags["quiet_pass"]:
        funnel["quiet_pass"] = 1
    if flags["attack_signal"]:
        funnel["attack_signal"] = 1
    if signal is None:
        return [], funnel

    row = simulate_cfa_entry(signal, ticks, friction_points=friction_points)
    funnel["entry"] = 1
    return [row], funnel


def _tick_rows_for_day(code: str, day: dt.date, *, cache_dir: Path) -> list[tuple[int, float, int, int]]:
    rows: list[tuple[int, float, int, int]] = []
    for tick in iter_replay_ticks(code, [day], cache_dir=cache_dir):
        t = tick.datetime.time()
        if t < SESSION_START or t > SESSION_END:
            continue
        rows.append(
            (
                int(tick.datetime.timestamp()),
                float(tick.close),
                int(tick.volume),
                int(tick.tick_type),
            )
        )
    return rows


def detect_cfa_entries_for_day(
    code: str,
    day: dt.date,
    *,
    cache_dir: Path,
    params: CfaParams,
    friction_points: float = FRICTION_POINTS,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    empty = _empty_cfa_funnel()
    kpath = resolve_kbar_path(cache_dir, code, day)
    if kpath is None:
        return [], empty

    bars = _session_bars(load_kbars_csv(kpath))
    ticks = _tick_rows_for_day(code, day, cache_dir=cache_dir)
    return scan_cfa_session(
        bars,
        params=params,
        day=day,
        ticks=ticks,
        friction_points=friction_points,
    )


def _empty_cfa_funnel() -> dict[str, int]:
    return {
        "days_with_session": 0,
        "compress_pass": 0,
        "regime_pass": 0,
        "quiet_pass": 0,
        "attack_signal": 0,
        "entry": 0,
    }


def _aggregate_funnel(funnels: list[dict[str, int]]) -> dict[str, Any]:
    keys = (
        "days_with_session",
        "compress_pass",
        "regime_pass",
        "quiet_pass",
        "attack_signal",
        "entry",
    )
    totals = {k: sum(f.get(k, 0) for f in funnels) for k in keys}
    cp = totals["compress_pass"]
    totals["compress_to_entry_rate"] = round(totals["entry"] / cp, 4) if cp else None
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


def _iter_param_sets(mode: Literal["fingerprint", "grid"]) -> list[CfaParams]:
    if mode == "fingerprint":
        return [
            CfaParams(
                compress_k=FINGERPRINT_COMPRESS_K,
                atr_regime_cap=FINGERPRINT_ATR_REGIME_CAP,
                attack_ratio_min=FINGERPRINT_ATTACK_RATIO_MIN,
                min_stop_atr_k=FINGERPRINT_MIN_STOP_ATR_K,
                tp_atr_k=FINGERPRINT_TP_ATR_K,
            )
        ]
    out: list[CfaParams] = []
    for ck in DEFAULT_COMPRESS_K:
        for rc in DEFAULT_ATR_REGIME_CAP:
            for ar in DEFAULT_ATTACK_RATIO_MIN:
                for ms in DEFAULT_MIN_STOP_ATR_K:
                    for tp in DEFAULT_TP_ATR_K:
                        out.append(
                            CfaParams(
                                compress_k=ck,
                                atr_regime_cap=rc,
                                attack_ratio_min=ar,
                                min_stop_atr_k=ms,
                                tp_atr_k=tp,
                            )
                        )
    return out


def build_cfa_payload(
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
            rows, funnel = detect_cfa_entries_for_day(
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
        outcome = "cfa_fingerprint_fail"
    elif mode == "grid" and not phase0_gate.get("pass"):
        outcome = "cfa_fingerprint_pass_g1_fail"
    elif mode == "grid" and phase0_gate.get("pass"):
        best = phase0_gate.get("best_passing") or {}
        best_key = best.get("param")
        if best_key and skew_gate_by_param.get(best_key, {}).get("disqualified"):
            outcome = "cfa_no_skew_champion"

    variant = "cfa_fingerprint_v1" if mode == "fingerprint" else "cfa_grid_v1"

    return {
        "schema_version": SCHEMA_VERSION,
        "thesis": "compression_flow_attack",
        "thesis_class": THESIS_CLASS,
        "variant": variant,
        "mode": mode,
        "from_date": from_date,
        "to_date": to_date,
        "code": code,
        "friction_points_per_round_trip": friction_points,
        "entry_model": "tick_chase_on_attack",
        "sim_params": {
            "entry_window": f"{ENTRY_WINDOW_START.isoformat()}–{NO_NEW_ENTRY_AFTER.isoformat()}",
            "compress_lookback_min": COMPRESS_LOOKBACK_MIN,
            "quiet_window_sec": QUIET_WINDOW_SEC,
            "attack_window_sec": ATTACK_WINDOW_SEC,
            "max_trades_per_day": 1,
            "atr_period": ATR_PERIOD,
            "atr_compress_floor": ATR_COMPRESS_FLOOR,
            "min_atr_pts": DEFAULT_MIN_ATR,
            "min_stop_pts": MIN_STOP_PTS,
            "exit_variant": EXIT_VARIANT,
            "max_hold_sec": DEFAULT_MAX_HOLD_SEC,
        },
        "fingerprint_params": {
            "compress_k": FINGERPRINT_COMPRESS_K,
            "atr_regime_cap": FINGERPRINT_ATR_REGIME_CAP,
            "attack_ratio_min": FINGERPRINT_ATTACK_RATIO_MIN,
            "min_stop_atr_k": FINGERPRINT_MIN_STOP_ATR_K,
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
