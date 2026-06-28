"""FT-009 Phase 0: Opening Range Breakout (ORB) counterfactual."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from reporting.armed_forward_counterfactual import (
    FRICTION_POINTS,
    _summarize_gross_net,
    simulate_atr_barrier_exit,
)
from reporting.short_breakout_counterfactual import (
    PHASE0_GROSS_MIN,
    PHASE0_MIN_N,
    PHASE0_NET_MIN,
    _atr_at_bar_index,
    _tick_rows_for_day,
)
from reporting.volatility_baseline import DEFAULT_ATR_PERIOD
from storage.kbar_loader import KBarRecord, load_kbars_csv, resolve_kbar_path
from storage.tick_loader import resolve_cli_tick_cache_dates

SCHEMA_VERSION = 1
SESSION_START = dt.time(8, 45)
SESSION_END = dt.time(13, 45)

DEFAULT_RANGE_MINUTES = (15, 30)
DEFAULT_BUFFER_ATR_KS = (0.0, 0.15)
DEFAULT_MIN_RANGE_ATR_K = 0.5
DEFAULT_MIN_ATR = 25.0

OrbDir = Literal["Long", "Short"]


@dataclass(frozen=True)
class OpeningRange:
    day: dt.date
    range_minutes: int
    range_high: float
    range_low: float
    range_width: float
    range_end_ts: int
    atr: float


@dataclass(frozen=True)
class OrbSignal:
    day: dt.date
    range_minutes: int
    buffer_atr_k: float
    direction: OrbDir
    entry_ts: int
    entry_price: float
    atr: float
    range_high: float
    range_low: float
    range_width: float


def _session_bars(bars: list[KBarRecord]) -> list[KBarRecord]:
    return [b for b in bars if SESSION_START <= b.ts.time() <= SESSION_END]


def _range_end_time(range_minutes: int) -> dt.time:
    base = dt.datetime.combine(dt.date(2000, 1, 1), SESSION_START)
    return (base + dt.timedelta(minutes=range_minutes)).time()


def _param_key(range_minutes: int, buffer_atr_k: float) -> str:
    bk = f"{buffer_atr_k:g}".replace(".", "p")
    return f"rm{range_minutes}_bk{bk}"


def compute_opening_range(
    bars: list[KBarRecord],
    range_minutes: int,
    *,
    min_range_atr_k: float = DEFAULT_MIN_RANGE_ATR_K,
) -> OpeningRange | None:
    range_end = _range_end_time(range_minutes)
    range_bars = [b for b in bars if SESSION_START <= b.ts.time() < range_end]
    if len(range_bars) < max(1, range_minutes // 2):
        return None

    range_high = max(float(b.High) for b in range_bars)
    range_low = min(float(b.Low) for b in range_bars)
    range_width = range_high - range_low
    last_idx = bars.index(range_bars[-1])
    atr = _atr_at_bar_index(bars, last_idx)
    if range_width < min_range_atr_k * atr:
        return None

    range_end_ts = int(range_bars[-1].ts.timestamp()) + 60
    return OpeningRange(
        day=range_bars[0].ts.date(),
        range_minutes=range_minutes,
        range_high=round(range_high, 1),
        range_low=round(range_low, 1),
        range_width=round(range_width, 2),
        range_end_ts=range_end_ts,
        atr=atr,
    )


def detect_orb_signal(
    bars: list[KBarRecord],
    opening: OpeningRange,
    *,
    buffer_atr_k: float,
) -> OrbSignal | None:
    range_end = _range_end_time(opening.range_minutes)
    threshold = buffer_atr_k * opening.atr
    upper = opening.range_high + threshold
    lower = opening.range_low - threshold

    for idx, bar in enumerate(bars):
        if bar.ts.time() < range_end:
            continue
        close = float(bar.Close)
        direction: OrbDir | None = None
        if close > upper:
            direction = "Long"
        elif close < lower:
            direction = "Short"
        if direction is None:
            continue

        entry_ts = int(bar.ts.timestamp()) + 60
        atr = _atr_at_bar_index(bars, idx)
        return OrbSignal(
            day=opening.day,
            range_minutes=opening.range_minutes,
            buffer_atr_k=buffer_atr_k,
            direction=direction,
            entry_ts=entry_ts,
            entry_price=close,
            atr=atr,
            range_high=opening.range_high,
            range_low=opening.range_low,
            range_width=opening.range_width,
        )
    return None


def simulate_orb_entry(
    signal: OrbSignal,
    ticks: list[tuple[int, float, int, int]],
    *,
    hard_stop_atr_k: float = 0.75,
    tp_atr_k: float = 2.0,
    friction_points: float = FRICTION_POINTS,
) -> dict[str, Any]:
    atr_sim = simulate_atr_barrier_exit(
        direction=signal.direction,
        entry_price=signal.entry_price,
        armed_ts=signal.entry_ts,
        atr=signal.atr,
        ticks=ticks,
        hard_stop_atr_k=hard_stop_atr_k,
        tp_atr_k=tp_atr_k,
    )
    gross_atr = float(atr_sim["gross_pnl"])
    net_atr = gross_atr - friction_points
    return {
        "day": signal.day.isoformat(),
        "ts": signal.entry_ts,
        "range_minutes": signal.range_minutes,
        "buffer_atr_k": signal.buffer_atr_k,
        "direction": signal.direction,
        "entry_price": signal.entry_price,
        "atr": round(signal.atr, 2),
        "range_high": signal.range_high,
        "range_low": signal.range_low,
        "range_width": signal.range_width,
        "gross_atr_sim": gross_atr,
        "net_atr_sim": net_atr,
        "atr_barrier_sim": atr_sim,
    }


def detect_orb_entries_for_day(
    code: str,
    day: dt.date,
    *,
    cache_dir: Path,
    range_minutes: int,
    buffer_atr_k: float,
    min_range_atr_k: float = DEFAULT_MIN_RANGE_ATR_K,
    hard_stop_atr_k: float = 0.75,
    tp_atr_k: float = 2.0,
    friction_points: float = FRICTION_POINTS,
) -> list[dict[str, Any]]:
    kpath = resolve_kbar_path(cache_dir, code, day)
    if kpath is None:
        return []
    bars = _session_bars(load_kbars_csv(kpath))
    if len(bars) < 25:
        return []

    opening = compute_opening_range(bars, range_minutes, min_range_atr_k=min_range_atr_k)
    if opening is None:
        return []

    signal = detect_orb_signal(bars, opening, buffer_atr_k=buffer_atr_k)
    if signal is None:
        return []

    ticks = _tick_rows_for_day(code, day, cache_dir=cache_dir)
    return [
        simulate_orb_entry(
            signal,
            ticks,
            hard_stop_atr_k=hard_stop_atr_k,
            tp_atr_k=tp_atr_k,
            friction_points=friction_points,
        )
    ]


def _summary_block(rows: list[dict[str, Any]], gross_key: str, net_key: str) -> dict[str, Any]:
    return _summarize_gross_net(gross_key, net_key, rows)


def _group_summary(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row[key]), []).append(row)
    return {
        g: {"atr_barrier_180s": _summary_block(sub, "gross_atr_sim", "net_atr_sim")}
        for g, sub in sorted(groups.items())
    }


def _evaluate_phase0_gate_params(
    summary_by_param: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    best: dict[str, Any] | None = None
    passed = False
    for param, metrics in summary_by_param.items():
        s = metrics.get("atr_barrier_180s") or {}
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


def build_orb_payload(
    *,
    code: str,
    cache_dir: Path,
    from_date: str,
    to_date: str,
    range_minutes: tuple[int, ...] = DEFAULT_RANGE_MINUTES,
    buffer_atr_ks: tuple[float, ...] = DEFAULT_BUFFER_ATR_KS,
    min_range_atr_k: float = DEFAULT_MIN_RANGE_ATR_K,
    hard_stop_atr_k: float = 0.75,
    tp_atr_k: float = 2.0,
    friction_points: float = FRICTION_POINTS,
    variant: str = "v1_orb_first_break",
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

    all_by_param: dict[str, list[dict[str, Any]]] = {}
    days_with_range: dict[str, int] = {}
    days_with_break: dict[str, int] = {}

    for rm in range_minutes:
        for bk in buffer_atr_ks:
            all_by_param[_param_key(rm, bk)] = []
            days_with_range[_param_key(rm, bk)] = 0
            days_with_break[_param_key(rm, bk)] = 0

    for day in dates:
        kpath = resolve_kbar_path(cache_dir, code, day)
        if kpath is None:
            continue
        bars = _session_bars(load_kbars_csv(kpath))

        for rm in range_minutes:
            opening = compute_opening_range(bars, rm, min_range_atr_k=min_range_atr_k)
            for bk in buffer_atr_ks:
                key = _param_key(rm, bk)
                if opening is not None:
                    days_with_range[key] += 1
                rows = detect_orb_entries_for_day(
                    code,
                    day,
                    cache_dir=cache_dir,
                    range_minutes=rm,
                    buffer_atr_k=bk,
                    min_range_atr_k=min_range_atr_k,
                    hard_stop_atr_k=hard_stop_atr_k,
                    tp_atr_k=tp_atr_k,
                    friction_points=friction_points,
                )
                if rows:
                    days_with_break[key] += 1
                all_by_param[key].extend(rows)

    summary_by_param: dict[str, Any] = {}
    for key, rows in all_by_param.items():
        summary_by_param[key] = {
            "atr_barrier_180s": _summary_block(rows, "gross_atr_sim", "net_atr_sim"),
        }

    phase0_gate = _evaluate_phase0_gate_params(summary_by_param)

    return {
        "schema_version": SCHEMA_VERSION,
        "thesis": "opening_range_breakout",
        "variant": variant,
        "from_date": from_date,
        "to_date": to_date,
        "code": code,
        "friction_points_per_round_trip": friction_points,
        "sim_params": {
            "range_minutes": list(range_minutes),
            "buffer_atr_ks": list(buffer_atr_ks),
            "min_range_atr_k": min_range_atr_k,
            "first_break_only": True,
            "max_trades_per_day": 1,
            "hard_stop_atr_k": hard_stop_atr_k,
            "tp_atr_k": tp_atr_k,
            "max_hold_sec": 180,
            "session_open": SESSION_START.isoformat(),
            "atr_method": "sma_tr_period_20",
        },
        "phase0_gate": phase0_gate,
        "phase0_gate_primary": "01-04_aggregate",
        "summary_by_param": summary_by_param,
        "summary_by_direction": {
            k: _group_summary(v, "direction") for k, v in all_by_param.items()
        },
        "days_with_valid_range": days_with_range,
        "days_with_breakout": days_with_break,
        "entry_count_by_param": {k: len(v) for k, v in all_by_param.items()},
        "entries": all_by_param,
    }
