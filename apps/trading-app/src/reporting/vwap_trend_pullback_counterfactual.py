"""FT-010 Phase 0: VWAP trend pullback (long-only) counterfactual."""

from __future__ import annotations

import datetime as dt
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from reporting.armed_forward_counterfactual import FRICTION_POINTS, _summarize_gross_net
from reporting.forward_pnl import _direction_sign
from reporting.short_breakout_counterfactual import (
    PHASE0_GROSS_MIN,
    PHASE0_MIN_N,
    PHASE0_NET_MIN,
    _atr_at_bar_index,
    _session_bars,
    _tick_rows_for_day,
)
from reporting.vwap_stretch_fade_counterfactual import session_bucket_for_ts
from storage.kbar_loader import KBarRecord, load_kbars_csv, resolve_kbar_path
from storage.tick_loader import resolve_cli_tick_cache_dates

SCHEMA_VERSION = 1
VTP_ATR_PERIOD = 14

DEFAULT_STRETCH_K = 1.5
DEFAULT_STRETCH_LOOKBACK_MIN = 15
DEFAULT_RECENCY_MAX_BARS = (6, 8, 10)
DEFAULT_UPPER_BUF_K = 0.12
DEFAULT_LOWER_BUF_K = 0.05
DEFAULT_PULLBACK_VOL_RATIO_MAX = 0.85
DEFAULT_ATTACK_VOL_MULT = 1.5
DEFAULT_MIN_ATR = 25.0

DEFAULT_HARD_STOP_ATR_K = 1.0
DEFAULT_HARD_STOP_FLOOR_PTS = 9.0
DEFAULT_TP_ATR_K = 1.8
DEFAULT_MAX_HOLD_SEC = 1200

MORNING_START = dt.time(8, 55)
MORNING_END = dt.time(11, 0)
AFTERNOON_START = dt.time(13, 0)
AFTERNOON_END = dt.time(13, 35)

EXIT_VARIANT = "atr_barrier_1200s"


@dataclass(frozen=True)
class BarCtx:
    idx: int
    ts: int
    close: float
    high: float
    low: float
    volume: float
    session_vwap: float
    atr: float


@dataclass(frozen=True)
class VtpSignal:
    day: dt.date
    recency_max_bars: int
    entry_ts: int
    entry_price: float
    atr: float
    session_vwap: float
    stretch_high: float
    stretch_bar_idx: int
    recency_bars: int
    session_bucket: str


def _param_key(recency_max_bars: int) -> str:
    return f"rcy{recency_max_bars}"


def _in_entry_window(bar_time: dt.time) -> bool:
    return (MORNING_START <= bar_time < MORNING_END) or (
        AFTERNOON_START <= bar_time < AFTERNOON_END
    )


def _session_vwap_series(bars: list[KBarRecord]) -> list[float]:
    """Session cumulative VWAP at each bar (close × volume weighted)."""
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
                close=float(bar.Close),
                high=float(bar.High),
                low=float(bar.Low),
                volume=float(bar.Volume),
                session_vwap=vwaps[idx],
                atr=_atr_at_bar_index(bars, idx, period=VTP_ATR_PERIOD),
            )
        )
    return contexts


def _env_filters(ctx: BarCtx, contexts: list[BarCtx]) -> bool:
    if ctx.atr < DEFAULT_MIN_ATR:
        return False
    if ctx.close <= ctx.session_vwap:
        return False
    if ctx.idx < 2:
        return False
    v0 = contexts[ctx.idx - 2].session_vwap
    v1 = contexts[ctx.idx - 1].session_vwap
    v2 = ctx.session_vwap
    if not (v2 > v1 > v0):
        return False
    return True


def _stretch_in_lookback(
    contexts: list[BarCtx],
    idx: int,
    *,
    stretch_k: float,
    lookback_bars: int,
) -> tuple[int, float] | None:
    """Return (stretch_bar_idx, stretch_high) if stretch occurred in lookback."""
    start = max(0, idx - lookback_bars + 1)
    stretch_bar_idx: int | None = None
    stretch_high = 0.0
    for j in range(start, idx + 1):
        c = contexts[j]
        threshold = c.session_vwap + stretch_k * c.atr
        if c.high >= threshold:
            if stretch_bar_idx is None:
                stretch_bar_idx = j
            stretch_high = max(stretch_high, c.high)
    if stretch_bar_idx is None:
        return None
    return stretch_bar_idx, stretch_high


def _buffer_zone(ctx: BarCtx, *, upper_buf_k: float, lower_buf_k: float) -> tuple[float, float]:
    upper = ctx.session_vwap + upper_buf_k * ctx.atr
    lower = ctx.session_vwap - lower_buf_k * ctx.atr
    return lower, upper


def _volume_ok(
    contexts: list[BarCtx],
    idx: int,
    stretch_bar_idx: int,
    *,
    pullback_vol_ratio_max: float,
    attack_vol_mult: float,
) -> bool:
    if idx < 5:
        return False
    stretch_vol = contexts[stretch_bar_idx].volume
    if stretch_vol <= 0:
        return False
    pullback_vols = [contexts[j].volume for j in range(stretch_bar_idx, idx)]
    if not pullback_vols:
        return False
    if statistics.median(pullback_vols) >= stretch_vol * pullback_vol_ratio_max:
        return False
    prev5 = [contexts[j].volume for j in range(idx - 5, idx)]
    mean_prev = statistics.mean(prev5)
    if mean_prev <= 0:
        return False
    return contexts[idx].volume >= mean_prev * attack_vol_mult


def detect_vtp_signal(
    contexts: list[BarCtx],
    *,
    recency_max_bars: int,
    stretch_k: float = DEFAULT_STRETCH_K,
    stretch_lookback_min: int = DEFAULT_STRETCH_LOOKBACK_MIN,
    upper_buf_k: float = DEFAULT_UPPER_BUF_K,
    lower_buf_k: float = DEFAULT_LOWER_BUF_K,
    pullback_vol_ratio_max: float = DEFAULT_PULLBACK_VOL_RATIO_MAX,
    attack_vol_mult: float = DEFAULT_ATTACK_VOL_MULT,
    require_volume_filter: bool = True,
) -> VtpSignal | None:
    day = dt.datetime.fromtimestamp(contexts[0].ts).date()
    for ctx in contexts:
        bar_time = dt.datetime.fromtimestamp(ctx.ts - 60).time()
        if not _in_entry_window(bar_time):
            continue
        if not _env_filters(ctx, contexts):
            continue

        stretch = _stretch_in_lookback(
            contexts,
            ctx.idx,
            stretch_k=stretch_k,
            lookback_bars=stretch_lookback_min,
        )
        if stretch is None:
            continue
        stretch_bar_idx, stretch_high = stretch
        recency_bars = ctx.idx - stretch_bar_idx
        if recency_bars > recency_max_bars:
            continue

        buf_lo, buf_hi = _buffer_zone(ctx, upper_buf_k=upper_buf_k, lower_buf_k=lower_buf_k)
        if not (buf_lo <= ctx.close <= buf_hi):
            continue
        if require_volume_filter and not _volume_ok(
            contexts,
            ctx.idx,
            stretch_bar_idx,
            pullback_vol_ratio_max=pullback_vol_ratio_max,
            attack_vol_mult=attack_vol_mult,
        ):
            continue

        tp_cap = stretch_high
        if tp_cap <= ctx.close:
            continue

        return VtpSignal(
            day=day,
            recency_max_bars=recency_max_bars,
            entry_ts=ctx.ts,
            entry_price=ctx.close,
            atr=ctx.atr,
            session_vwap=round(ctx.session_vwap, 2),
            stretch_high=round(stretch_high, 2),
            stretch_bar_idx=stretch_bar_idx,
            recency_bars=recency_bars,
            session_bucket=session_bucket_for_ts(ctx.ts),
        )
    return None


def simulate_vtp_exit(
    signal: VtpSignal,
    ticks: list[tuple[int, float, int, int]],
    *,
    hard_stop_atr_k: float = DEFAULT_HARD_STOP_ATR_K,
    hard_stop_floor_pts: float = DEFAULT_HARD_STOP_FLOOR_PTS,
    tp_atr_k: float = DEFAULT_TP_ATR_K,
    max_hold_sec: int = DEFAULT_MAX_HOLD_SEC,
) -> dict[str, Any]:
    """Long exit with ATR stop floor and TP capped at stretch_high."""
    direction = "Long"
    entry_price = signal.entry_price
    armed_ts = signal.entry_ts
    atr = signal.atr
    sign = _direction_sign(direction)
    hard_dist = max(hard_stop_atr_k * atr, hard_stop_floor_pts)
    tp_dist = min(tp_atr_k * atr, signal.stretch_high - entry_price)
    if tp_dist <= 0:
        tp_dist = tp_atr_k * atr
    end_ts = armed_ts + max_hold_sec
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
    return {
        "gross_pnl": round(gross, 2),
        "exit_reason": "horizon",
        "hold_sec": last_ts - armed_ts,
        "mfe": round(mfe, 2),
        "mae": round(mae, 2),
        "quick_stop": False,
    }


def simulate_vtp_entry(
    signal: VtpSignal,
    ticks: list[tuple[int, float, int, int]],
    *,
    friction_points: float = FRICTION_POINTS,
    hard_stop_atr_k: float = DEFAULT_HARD_STOP_ATR_K,
    tp_atr_k: float = DEFAULT_TP_ATR_K,
) -> dict[str, Any]:
    sim = simulate_vtp_exit(
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
        "recency_max_bars": signal.recency_max_bars,
        "param": _param_key(signal.recency_max_bars),
        "direction": "Long",
        "entry_price": signal.entry_price,
        "atr": round(signal.atr, 2),
        "session_vwap": signal.session_vwap,
        "stretch_high": signal.stretch_high,
        "recency_bars": signal.recency_bars,
        "session_bucket": signal.session_bucket,
        "gross_atr_sim": gross,
        "net_atr_sim": net,
        "atr_barrier_sim": sim,
    }


def detect_vtp_entries_for_day(
    code: str,
    day: dt.date,
    *,
    cache_dir: Path,
    recency_max_bars: int,
    stretch_k: float = DEFAULT_STRETCH_K,
    friction_points: float = FRICTION_POINTS,
    require_volume_filter: bool = True,
) -> list[dict[str, Any]]:
    kpath = resolve_kbar_path(cache_dir, code, day)
    if kpath is None:
        return []
    bars = _session_bars(load_kbars_csv(kpath))
    if len(bars) < VTP_ATR_PERIOD + 5:
        return []

    contexts = _build_bar_contexts(bars)
    signal = detect_vtp_signal(
        contexts,
        recency_max_bars=recency_max_bars,
        stretch_k=stretch_k,
        require_volume_filter=require_volume_filter,
    )
    if signal is None:
        return []

    ticks = _tick_rows_for_day(code, day, cache_dir=cache_dir)
    return [simulate_vtp_entry(signal, ticks, friction_points=friction_points)]


def _count_stretch_days(
    code: str,
    day: dt.date,
    *,
    cache_dir: Path,
    stretch_k: float = DEFAULT_STRETCH_K,
) -> tuple[bool, bool]:
    """Return (had_stretch_env, had_buffer_touch) for funnel."""
    kpath = resolve_kbar_path(cache_dir, code, day)
    if kpath is None:
        return False, False
    bars = _session_bars(load_kbars_csv(kpath))
    if len(bars) < VTP_ATR_PERIOD + 5:
        return False, False
    contexts = _build_bar_contexts(bars)
    had_stretch = False
    had_buffer = False
    for ctx in contexts:
        bar_time = dt.datetime.fromtimestamp(ctx.ts - 60).time()
        if not _in_entry_window(bar_time):
            continue
        if not _env_filters(ctx, contexts):
            continue
        stretch = _stretch_in_lookback(
            contexts,
            ctx.idx,
            stretch_k=stretch_k,
            lookback_bars=DEFAULT_STRETCH_LOOKBACK_MIN,
        )
        if stretch is None:
            continue
        had_stretch = True
        buf_lo, buf_hi = _buffer_zone(
            ctx,
            upper_buf_k=DEFAULT_UPPER_BUF_K,
            lower_buf_k=DEFAULT_LOWER_BUF_K,
        )
        if buf_lo <= ctx.close <= buf_hi:
            had_buffer = True
    return had_stretch, had_buffer


def _summary_block(rows: list[dict[str, Any]], gross_key: str, net_key: str) -> dict[str, Any]:
    out = _summarize_gross_net(gross_key, net_key, rows)
    stops = [r for r in rows if (r.get("atr_barrier_sim") or {}).get("exit_reason") == "stop_loss"]
    if rows:
        out["quick_stop_loss_rate"] = round(
            sum(1 for r in rows if (r.get("atr_barrier_sim") or {}).get("quick_stop")) / len(rows),
            4,
        )
    else:
        out["quick_stop_loss_rate"] = None
    out["stop_loss_rate"] = round(len(stops) / len(rows), 4) if rows else None
    return out


def _evaluate_phase0_gate(summary_by_param: dict[str, dict[str, Any]]) -> dict[str, Any]:
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
            if best is None or (net > best.get("net_mean", -1e9)):
                best = candidate
    return {
        "pass": passed,
        "gross_mean_min": PHASE0_GROSS_MIN,
        "net_mean_min": PHASE0_NET_MIN,
        "min_n": PHASE0_MIN_N,
        "best_passing": best,
    }


def build_vtp_payload(
    *,
    code: str,
    cache_dir: Path,
    from_date: str,
    to_date: str,
    recency_max_bars: tuple[int, ...] = DEFAULT_RECENCY_MAX_BARS,
    stretch_k: float = DEFAULT_STRETCH_K,
    friction_points: float = FRICTION_POINTS,
    variant: str = "v1_vtp_long_only",
    require_volume_filter: bool = True,
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

    all_by_param: dict[str, list[dict[str, Any]]] = {
        _param_key(r): [] for r in recency_max_bars
    }
    stretch_days = 0
    buffer_touch_days = 0
    trading_days = 0

    for day in dates:
        kpath = resolve_kbar_path(cache_dir, code, day)
        if kpath is None:
            continue
        trading_days += 1
        had_stretch, had_buffer = _count_stretch_days(code, day, cache_dir=cache_dir, stretch_k=stretch_k)
        if had_stretch:
            stretch_days += 1
        if had_buffer:
            buffer_touch_days += 1

        for recency in recency_max_bars:
            rows = detect_vtp_entries_for_day(
                code,
                day,
                cache_dir=cache_dir,
                recency_max_bars=recency,
                stretch_k=stretch_k,
                friction_points=friction_points,
                require_volume_filter=require_volume_filter,
            )
            all_by_param[_param_key(recency)].extend(rows)

    summary_by_param: dict[str, Any] = {}
    for key, rows in all_by_param.items():
        summary_by_param[key] = {
            EXIT_VARIANT: _summary_block(rows, "gross_atr_sim", "net_atr_sim"),
        }

    funnel = {
        "trading_days": trading_days,
        "days_with_stretch_env": stretch_days,
        "days_with_buffer_touch": buffer_touch_days,
        "stretch_to_buffer_rate": round(buffer_touch_days / stretch_days, 4) if stretch_days else None,
        "structural_band_unreachable": (
            stretch_days > 0 and buffer_touch_days / stretch_days < 0.25
        ),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "variant": variant,
        "code": code,
        "from_date": from_date,
        "to_date": to_date,
        "direction": "Long",
        "friction_points": friction_points,
        "stretch_k": stretch_k,
        "recency_max_bars_grid": list(recency_max_bars),
        "require_volume_filter": require_volume_filter,
        "exit": {
            "hard_stop_atr_k": DEFAULT_HARD_STOP_ATR_K,
            "hard_stop_floor_pts": DEFAULT_HARD_STOP_FLOOR_PTS,
            "tp_atr_k": DEFAULT_TP_ATR_K,
            "max_hold_sec": DEFAULT_MAX_HOLD_SEC,
            "variant": EXIT_VARIANT,
        },
        "entry_count_by_param": {k: len(v) for k, v in all_by_param.items()},
        "rows_by_param": all_by_param,
        "summary_by_param": summary_by_param,
        "funnel": funnel,
        "phase0_gate": _evaluate_phase0_gate(summary_by_param),
    }
