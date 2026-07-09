"""FT-011 Phase 0: Session Confluence Breakout (SCB) long-only counterfactual."""

from __future__ import annotations

import datetime as dt
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from reporting.armed_forward_counterfactual import FRICTION_POINTS, _summarize_gross_net
from reporting.forward_pnl import _direction_sign, load_tick_series
from reporting.post_entry_diagnosis import (
    enrich_rows_with_forward_windows,
    summarize_post_entry_diagnosis,
)
from reporting.orb_counterfactual import (
    OpeningRange,
    OrbSignal,
    SESSION_START as ORB_SESSION_START,
    compute_opening_range,
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
SCB_ATR_PERIOD = 14

DEFAULT_RANGE_MINUTES = (20, 30)
DEFAULT_VOLUME_MULT = 1.4
DEFAULT_MIN_ATR = 20.0
DEFAULT_HARD_STOP_ATR_K = 1.2
DEFAULT_HARD_STOP_FLOOR_PTS = 10.0
DEFAULT_TP_ATR_K = 1.8
DEFAULT_MAX_HOLD_SEC = 1200
DEFAULT_DAILY_LOSS_LIMIT = 30.0

MORNING_START = dt.time(8, 55)
MORNING_END = dt.time(10, 30)
AFTERNOON_START = dt.time(13, 0)
AFTERNOON_END = dt.time(13, 35)
LUNCH_START = dt.time(11, 0)
LUNCH_END = dt.time(13, 0)

EXIT_VARIANT = "atr_barrier_1200s"


def _raw_atr_at_bar_index(bars: list[KBarRecord], idx: int, *, period: int = SCB_ATR_PERIOD) -> float:
    """Unclamped SMA(TR) ATR — SPEC C4 uses true ATR(14) vs min_atr_threshold."""
    tuples = [
        (b.High, b.Low, b.Close, b.High - b.Low, float(b.Volume)) for b in bars[: idx + 1]
    ]
    atrs = atr_series_from_bars(tuples, period=period)
    if not atrs:
        return 0.0
    return float(atrs[-1])


@dataclass(frozen=True)
class BarCtx:
    idx: int
    ts: int
    bar_time: dt.time
    close: float
    high: float
    low: float
    volume: float
    session_vwap: float
    atr: float


@dataclass(frozen=True)
class ScbSignal:
    day: dt.date
    range_minutes: int
    entry_ts: int
    entry_price: float
    atr: float
    session_vwap: float
    range_high: float
    range_low: float
    volume_ratio: float
    confluence_factors: dict[str, bool]
    session_bucket: str


def _param_key(range_minutes: int) -> str:
    return f"rm{range_minutes}"


def _range_end_time(range_minutes: int) -> dt.time:
    base = dt.datetime.combine(dt.date(2000, 1, 1), ORB_SESSION_START)
    return (base + dt.timedelta(minutes=range_minutes)).time()


def _in_entry_window(bar_time: dt.time) -> bool:
    if LUNCH_START <= bar_time < LUNCH_END:
        return False
    return (MORNING_START <= bar_time < MORNING_END) or (
        AFTERNOON_START <= bar_time < AFTERNOON_END
    )


def _scb_session_bucket(bar_time: dt.time) -> str:
    if MORNING_START <= bar_time < MORNING_END:
        return "morning"
    if AFTERNOON_START <= bar_time < AFTERNOON_END:
        return "close"
    return "other"


def _session_vwap_series(bars: list[KBarRecord]) -> list[float]:
    cum_pv = 0.0
    cum_vol = 0.0
    out: list[float] = []
    for bar in bars:
        vol = float(bar.Volume)
        px = float(bar.Close)
        cum_pv += px * vol
        cum_vol += vol
        out.append(cum_pv / cum_vol if cum_vol > 0 else px)
    return out


def _build_bar_contexts(bars: list[KBarRecord]) -> list[BarCtx]:
    vwaps = _session_vwap_series(bars)
    contexts: list[BarCtx] = []
    for idx, bar in enumerate(bars):
        contexts.append(
            BarCtx(
                idx=idx,
                ts=int(bar.ts.timestamp()) + 60,
                bar_time=bar.ts.time(),
                close=float(bar.Close),
                high=float(bar.High),
                low=float(bar.Low),
                volume=float(bar.Volume),
                session_vwap=vwaps[idx],
                atr=_raw_atr_at_bar_index(bars, idx, period=SCB_ATR_PERIOD),
            )
        )
    return contexts


def _vwap_slope_ok(contexts: list[BarCtx], idx: int) -> bool:
    if idx < 2:
        return False
    v0 = contexts[idx - 2].session_vwap
    v1 = contexts[idx - 1].session_vwap
    v2 = contexts[idx].session_vwap
    return v2 > v1 > v0


def _volume_ratio_ok(contexts: list[BarCtx], idx: int, *, volume_mult: float) -> float | None:
    if idx < 5:
        return None
    prev5 = [contexts[j].volume for j in range(idx - 5, idx)]
    mean_prev = statistics.mean(prev5)
    if mean_prev <= 0:
        return None
    ratio = contexts[idx].volume / mean_prev
    if ratio >= volume_mult:
        return round(ratio, 4)
    return None


def _confluence_at_bar(
    ctx: BarCtx,
    contexts: list[BarCtx],
    opening: OpeningRange,
    *,
    volume_mult: float,
    min_atr: float,
) -> tuple[dict[str, bool], float | None] | None:
    c1 = ctx.close > ctx.session_vwap
    c2 = _vwap_slope_ok(contexts, ctx.idx)
    c3 = ctx.close > opening.range_high
    c4 = ctx.atr >= min_atr
    vol_ratio = _volume_ratio_ok(contexts, ctx.idx, volume_mult=volume_mult)
    c5 = vol_ratio is not None
    factors = {"C1": c1, "C2": c2, "C3": c3, "C4": c4, "C5": c5}
    if all(factors.values()):
        return factors, vol_ratio
    return None


def _session_force_exit_ts(day: dt.date, bar_time: dt.time) -> int | None:
    if AFTERNOON_START <= bar_time < AFTERNOON_END:
        end_dt = dt.datetime.combine(day, AFTERNOON_END)
        return int(end_dt.timestamp())
    return None


def detect_scb_signal(
    contexts: list[BarCtx],
    opening: OpeningRange,
    *,
    volume_mult: float = DEFAULT_VOLUME_MULT,
    min_atr: float = DEFAULT_MIN_ATR,
) -> ScbSignal | None:
    range_end = _range_end_time(opening.range_minutes)
    day = opening.day

    for ctx in contexts:
        if ctx.bar_time < range_end:
            continue
        if not _in_entry_window(ctx.bar_time):
            continue

        hit = _confluence_at_bar(
            ctx,
            contexts,
            opening,
            volume_mult=volume_mult,
            min_atr=min_atr,
        )
        if hit is None:
            continue
        factors, vol_ratio = hit
        return ScbSignal(
            day=day,
            range_minutes=opening.range_minutes,
            entry_ts=ctx.ts,
            entry_price=ctx.close,
            atr=ctx.atr,
            session_vwap=round(ctx.session_vwap, 2),
            range_high=opening.range_high,
            range_low=opening.range_low,
            volume_ratio=vol_ratio or 0.0,
            confluence_factors=factors,
            session_bucket=_scb_session_bucket(ctx.bar_time),
        )
    return None


def simulate_scb_exit(
    signal: ScbSignal,
    ticks: list[tuple[int, float, int, int]],
    *,
    hard_stop_atr_k: float = DEFAULT_HARD_STOP_ATR_K,
    hard_stop_floor_pts: float = DEFAULT_HARD_STOP_FLOOR_PTS,
    tp_atr_k: float = DEFAULT_TP_ATR_K,
    max_hold_sec: int = DEFAULT_MAX_HOLD_SEC,
) -> dict[str, Any]:
    direction = "Long"
    entry_price = signal.entry_price
    armed_ts = signal.entry_ts
    atr = signal.atr
    sign = _direction_sign(direction)
    hard_dist = max(hard_stop_atr_k * atr, hard_stop_floor_pts)
    tp_dist = tp_atr_k * atr
    end_ts = armed_ts + max_hold_sec
    force_ts = _session_force_exit_ts(signal.day, dt.datetime.fromtimestamp(armed_ts - 60).time())
    if force_ts is not None:
        end_ts = min(end_ts, force_ts)
    mfe = 0.0
    mae = 0.0

    for ts, price, _vol, _tt in ticks:
        if ts < armed_ts:
            continue
        if ts > end_ts:
            break
        delta = sign * (price - entry_price)
        mfe = max(mfe, delta)
        mae = max(mae, -delta)
        if delta <= -hard_dist:
            return {
                "gross_pnl": round(-hard_dist, 2),
                "exit_reason": "stop_loss",
                "hold_sec": ts - armed_ts,
                "mfe": round(mfe, 2),
                "mae": round(mae, 2),
                "quick_stop": (ts - armed_ts) <= 60,
            }
        if delta >= tp_dist:
            return {
                "gross_pnl": round(tp_dist, 2),
                "exit_reason": "take_profit",
                "hold_sec": ts - armed_ts,
                "mfe": round(mfe, 2),
                "mae": round(mae, 2),
                "quick_stop": False,
            }

    last_price = entry_price
    last_ts = armed_ts
    for ts, price, _v, _t in ticks:
        if armed_ts <= ts <= end_ts:
            last_price = price
            last_ts = ts
    gross = sign * (last_price - entry_price)
    reason = "session_close" if force_ts is not None and last_ts >= force_ts - 60 else "horizon"
    return {
        "gross_pnl": round(gross, 2),
        "exit_reason": reason,
        "hold_sec": last_ts - armed_ts,
        "mfe": round(mfe, 2),
        "mae": round(mae, 2),
        "quick_stop": False,
    }


def simulate_scb_entry(
    signal: ScbSignal,
    ticks: list[tuple[int, float, int, int]],
    *,
    friction_points: float = FRICTION_POINTS,
    hard_stop_atr_k: float = DEFAULT_HARD_STOP_ATR_K,
    tp_atr_k: float = DEFAULT_TP_ATR_K,
) -> dict[str, Any]:
    sim = simulate_scb_exit(
        signal,
        ticks,
        hard_stop_atr_k=hard_stop_atr_k,
        tp_atr_k=tp_atr_k,
    )
    gross = float(sim["gross_pnl"])
    net = gross - friction_points
    return {
        "day": signal.day.isoformat(),
        "ts": signal.entry_ts,
        "param": _param_key(signal.range_minutes),
        "range_minutes": signal.range_minutes,
        "direction": "Long",
        "entry_price": signal.entry_price,
        "atr": round(signal.atr, 2),
        "session_vwap": signal.session_vwap,
        "opening_range_high": signal.range_high,
        "range_low": signal.range_low,
        "volume_ratio": signal.volume_ratio,
        "confluence_factors": signal.confluence_factors,
        "session_bucket": signal.session_bucket,
        "gross_atr_sim": gross,
        "net_atr_sim": net,
        "atr_barrier_sim": sim,
    }


def _orb_long_in_scb_window(
    bars: list[KBarRecord],
    opening: OpeningRange,
) -> OrbSignal | None:
    """First long break after range end while inside SCB entry windows (bk=0)."""
    range_end = _range_end_time(opening.range_minutes)
    upper = opening.range_high

    for idx, bar in enumerate(bars):
        if bar.ts.time() < range_end:
            continue
        if not _in_entry_window(bar.ts.time()):
            continue
        close = float(bar.Close)
        if close <= upper:
            continue
        entry_ts = int(bar.ts.timestamp()) + 60
        atr = _raw_atr_at_bar_index(bars, idx, period=SCB_ATR_PERIOD)
        return OrbSignal(
            day=opening.day,
            range_minutes=opening.range_minutes,
            buffer_atr_k=0.0,
            direction="Long",
            entry_ts=entry_ts,
            entry_price=close,
            atr=atr,
            range_high=opening.range_high,
            range_low=opening.range_low,
            range_width=opening.range_width,
        )
    return None


def _count_funnel_day(
    contexts: list[BarCtx],
    opening: OpeningRange | None,
    *,
    volume_mult: float,
    min_atr: float,
) -> dict[str, int]:
    counts = {
        "days": 1,
        "in_session_window": 0,
        "post_range": 0,
        "trend_ok": 0,
        "breakout_ok": 0,
        "vol_ok": 0,
        "entry": 0,
    }
    if opening is None:
        return counts

    range_end = _range_end_time(opening.range_minutes)
    had_window = False
    had_post = False
    had_trend = False
    had_breakout = False
    had_vol = False
    had_entry = False

    for ctx in contexts:
        if _in_entry_window(ctx.bar_time):
            had_window = True

        if ctx.bar_time < range_end:
            continue
        if not _in_entry_window(ctx.bar_time):
            continue

        c1 = ctx.close > ctx.session_vwap
        c2 = _vwap_slope_ok(contexts, ctx.idx)
        c3 = ctx.close > opening.range_high
        c4 = ctx.atr >= min_atr
        vol_ratio = _volume_ratio_ok(contexts, ctx.idx, volume_mult=volume_mult)
        c5 = vol_ratio is not None

        had_post = True
        if c1 and c2:
            had_trend = True
        if c1 and c2 and c3:
            had_breakout = True
        if c1 and c2 and c3 and c4 and c5:
            had_vol = True
            had_entry = True
            break

    if had_window:
        counts["in_session_window"] = 1
    if had_post:
        counts["post_range"] = 1
    if had_trend:
        counts["trend_ok"] = 1
    if had_breakout:
        counts["breakout_ok"] = 1
    if had_vol:
        counts["vol_ok"] = 1
    if had_entry:
        counts["entry"] = 1
    return counts


def detect_scb_entries_for_day(
    code: str,
    day: dt.date,
    *,
    cache_dir: Path,
    range_minutes: int,
    volume_mult: float = DEFAULT_VOLUME_MULT,
    min_atr: float = DEFAULT_MIN_ATR,
    friction_points: float = FRICTION_POINTS,
    daily_loss_limit: float = DEFAULT_DAILY_LOSS_LIMIT,
) -> list[dict[str, Any]]:
    kpath = resolve_kbar_path(cache_dir, code, day)
    if kpath is None:
        return []
    bars = _session_bars(load_kbars_csv(kpath))
    if len(bars) < SCB_ATR_PERIOD + 5:
        return []

    opening = compute_opening_range(bars, range_minutes, min_range_atr_k=0.0)
    if opening is None:
        return []

    contexts = _build_bar_contexts(bars)
    signal = detect_scb_signal(
        contexts,
        opening,
        volume_mult=volume_mult,
        min_atr=min_atr,
    )
    if signal is None:
        return []

    ticks = _tick_rows_for_day(code, day, cache_dir=cache_dir)
    row = simulate_scb_entry(signal, ticks, friction_points=friction_points)
    if row["net_atr_sim"] <= -daily_loss_limit:
        pass  # first-only day; circuit documented for audit
    return [row]


def _summary_block(rows: list[dict[str, Any]], gross_key: str, net_key: str) -> dict[str, Any]:
    out = _summarize_gross_net(gross_key, net_key, rows)
    if rows:
        out["quick_stop_loss_rate"] = round(
            sum(1 for r in rows if (r.get("atr_barrier_sim") or {}).get("quick_stop")) / len(rows),
            4,
        )
    else:
        out["quick_stop_loss_rate"] = None
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
        day = dt.date.fromisoformat(str(row["day"]))
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
    by_dir: dict[str, list[float]] = {}
    for row in rows:
        by_dir.setdefault(str(row.get("direction", "Long")), []).append(float(row["net_atr_sim"]))
    for direction, nets in by_dir.items():
        if nets and statistics.mean(nets) < -3:
            flags.append(f"{direction}_net_mean_lt_neg3")
    return flags


def _evaluate_phase0_gate(summary_by_param: dict[str, dict[str, Any]], rows_by_param: dict) -> dict[str, Any]:
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


def _orb_signal_to_scb(orb_sig: OrbSignal) -> ScbSignal:
    bar_time = dt.datetime.fromtimestamp(orb_sig.entry_ts - 60).time()
    return ScbSignal(
        day=orb_sig.day,
        range_minutes=orb_sig.range_minutes,
        entry_ts=orb_sig.entry_ts,
        entry_price=orb_sig.entry_price,
        atr=orb_sig.atr,
        session_vwap=0.0,
        range_high=orb_sig.range_high,
        range_low=orb_sig.range_low,
        volume_ratio=0.0,
        confluence_factors={},
        session_bucket=_scb_session_bucket(bar_time),
    )


def _orb_compare_row(
    code: str,
    day: dt.date,
    *,
    cache_dir: Path,
    range_minutes: int,
    friction_points: float,
) -> dict[str, Any]:
    kpath = resolve_kbar_path(cache_dir, code, day)
    if kpath is None:
        return {"day": day.isoformat(), "orb_long": None, "scb": None}
    bars = _session_bars(load_kbars_csv(kpath))
    if len(bars) < SCB_ATR_PERIOD + 5:
        return {"day": day.isoformat(), "orb_long": None, "scb": None}
    opening = compute_opening_range(bars, range_minutes, min_range_atr_k=0.0)
    if opening is None:
        return {"day": day.isoformat(), "orb_long": None, "scb": None}

    ticks = _tick_rows_for_day(code, day, cache_dir=cache_dir)
    orb_sig = _orb_long_in_scb_window(bars, opening)
    orb_row = None
    if orb_sig is not None:
        sim = simulate_scb_exit(_orb_signal_to_scb(orb_sig), ticks)
        gross = float(sim["gross_pnl"])
        orb_row = {
            "day": orb_sig.day.isoformat(),
            "ts": orb_sig.entry_ts,
            "direction": "Long",
            "gross_atr_sim": gross,
            "net_atr_sim": gross - friction_points,
            "atr_barrier_sim": sim,
        }

    scb_rows = detect_scb_entries_for_day(
        code,
        day,
        cache_dir=cache_dir,
        range_minutes=range_minutes,
        friction_points=friction_points,
    )
    scb_row = scb_rows[0] if scb_rows else None
    return {
        "day": day.isoformat(),
        "orb_long": orb_row,
        "scb": scb_row,
        "orb_without_scb": orb_row is not None and scb_row is None,
        "both": orb_row is not None and scb_row is not None,
    }


def build_orb_delta(
    *,
    code: str,
    cache_dir: Path,
    from_date: str,
    to_date: str,
    range_minutes: tuple[int, ...] = DEFAULT_RANGE_MINUTES,
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
    by_param: dict[str, Any] = {}
    for rm in range_minutes:
        key = _param_key(rm)
        days: list[dict[str, Any]] = []
        orb_n = 0
        scb_n = 0
        filtered = 0
        orb_net = 0.0
        scb_net = 0.0
        for day in dates:
            row = _orb_compare_row(code, day, cache_dir=cache_dir, range_minutes=rm, friction_points=friction_points)
            days.append(row)
            if row["orb_long"] is not None:
                orb_n += 1
                orb_net += float(row["orb_long"]["net_atr_sim"])
            if row["scb"] is not None:
                scb_n += 1
                scb_net += float(row["scb"]["net_atr_sim"])
            if row.get("orb_without_scb"):
                filtered += 1
        by_param[key] = {
            "orb_long_count": orb_n,
            "scb_count": scb_n,
            "orb_filtered_by_confluence": filtered,
            "orb_long_net_total": round(orb_net, 2),
            "scb_net_total": round(scb_net, 2),
            "net_delta_scb_minus_orb": round(scb_net - orb_net, 2),
            "scb_pass_rate_of_orb": round(scb_n / orb_n, 4) if orb_n else None,
            "days": days,
        }
    return {
        "from_date": from_date,
        "to_date": to_date,
        "code": code,
        "note": "ORB long-only in SCB session windows; bk=0; min_range_atr_k=0",
        "by_param": by_param,
    }


def build_scb_payload(
    *,
    code: str,
    cache_dir: Path,
    from_date: str,
    to_date: str,
    range_minutes: tuple[int, ...] = DEFAULT_RANGE_MINUTES,
    volume_mult: float = DEFAULT_VOLUME_MULT,
    min_atr: float = DEFAULT_MIN_ATR,
    friction_points: float = FRICTION_POINTS,
    variant: str = "v1_scb_long_only",
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

    all_by_param: dict[str, list[dict[str, Any]]] = {_param_key(rm): [] for rm in range_minutes}
    funnel_by_param: dict[str, dict[str, int]] = {
        _param_key(rm): {
            k: 0
            for k in (
                "days",
                "in_session_window",
                "post_range",
                "trend_ok",
                "breakout_ok",
                "vol_ok",
                "entry",
            )
        }
        for rm in range_minutes
    }

    for day in dates:
        kpath = resolve_kbar_path(cache_dir, code, day)
        if kpath is None:
            continue
        bars = _session_bars(load_kbars_csv(kpath))
        contexts = _build_bar_contexts(bars) if len(bars) >= SCB_ATR_PERIOD + 5 else []

        for rm in range_minutes:
            pkey = _param_key(rm)
            opening = compute_opening_range(bars, rm, min_range_atr_k=0.0) if bars else None
            if contexts:
                f = _count_funnel_day(
                    contexts,
                    opening,
                    volume_mult=volume_mult,
                    min_atr=min_atr,
                )
                for fk in funnel_by_param[pkey]:
                    funnel_by_param[pkey][fk] += f[fk]

            rows = detect_scb_entries_for_day(
                code,
                day,
                cache_dir=cache_dir,
                range_minutes=rm,
                volume_mult=volume_mult,
                min_atr=min_atr,
                friction_points=friction_points,
            )
            all_by_param[pkey].extend(rows)

    summary_by_param: dict[str, Any] = {}
    post_entry_by_param: dict[str, Any] = {}
    for key, rows in all_by_param.items():
        if rows:
            enrich_rows_with_forward_windows(rows, series)
        summary_by_param[key] = {
            EXIT_VARIANT: _summary_block(rows, "gross_atr_sim", "net_atr_sim"),
        }
        post_entry_by_param[key] = summarize_post_entry_diagnosis(
            rows,
            friction_points=friction_points,
        )

    funnel_out: dict[str, Any] = {}
    for pkey, totals in funnel_by_param.items():
        rates: dict[str, float | None] = {}
        if totals["days"]:
            base = totals["days"]
            rates = {
                "in_session_window_rate": round(totals["in_session_window"] / base, 4),
                "post_range_rate": round(totals["post_range"] / base, 4),
                "trend_ok_rate": round(totals["trend_ok"] / base, 4),
                "breakout_ok_rate": round(totals["breakout_ok"] / base, 4),
                "vol_ok_rate": round(totals["vol_ok"] / base, 4),
                "entry_rate": round(totals["entry"] / base, 4),
            }
        funnel_out[pkey] = {**totals, **rates}

    return {
        "schema_version": SCHEMA_VERSION,
        "thesis": "session_confluence_breakout",
        "variant": variant,
        "from_date": from_date,
        "to_date": to_date,
        "code": code,
        "direction": "Long",
        "friction_points_per_round_trip": friction_points,
        "sim_params": {
            "opening_range_minutes": list(range_minutes),
            "volume_mult": volume_mult,
            "min_atr_threshold_points": min_atr,
            "hard_stop_atr_k": DEFAULT_HARD_STOP_ATR_K,
            "hard_stop_floor_pts": DEFAULT_HARD_STOP_FLOOR_PTS,
            "tp_atr_k": DEFAULT_TP_ATR_K,
            "max_hold_sec": DEFAULT_MAX_HOLD_SEC,
            "vwap_slope_bars": 3,
            "morning_window": f"{MORNING_START.isoformat()}..{MORNING_END.isoformat()}",
            "close_window": f"{AFTERNOON_START.isoformat()}..{AFTERNOON_END.isoformat()}",
            "exit_variant": EXIT_VARIANT,
        },
        "phase0_gate": _evaluate_phase0_gate(summary_by_param, all_by_param),
        "phase0_gate_primary": "v2.1_train_2025",
        "summary_by_param": summary_by_param,
        "summary_by_session_bucket": {
            k: _group_summary(v, "session_bucket") for k, v in all_by_param.items()
        },
        "entry_count_by_param": {k: len(v) for k, v in all_by_param.items()},
        "entries": all_by_param,
        "post_entry_diagnosis_by_param": post_entry_by_param,
        "rows_by_param": all_by_param,
        "funnel_by_param": funnel_out,
    }
