"""FT-007 Phase 0: 1m impulse exhaustion + tick absorption fade counterfactual."""

from __future__ import annotations

import datetime as dt
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from reporting.armed_forward_counterfactual import FRICTION_POINTS, _summarize_gross_net
from reporting.forward_pnl import _direction_sign
from reporting.volatility_baseline import DEFAULT_ATR_PERIOD, atr_series_from_bars
from reporting.vwap_stretch_fade_counterfactual import session_bucket_for_ts
from storage.kbar_loader import KBarRecord, load_kbars_csv, resolve_kbar_path
from storage.tick_loader import iter_replay_ticks, resolve_cli_tick_cache_dates

SCHEMA_VERSION = 1
SESSION_START = dt.time(8, 45)
SESSION_END = dt.time(13, 45)

DEFAULT_IMPULSE_BARS = (3, 4)
DEFAULT_IMPULSE_BODY_ATR_K = 1.0
DEFAULT_IMPULSE_VOL_PCT = 70.0
DEFAULT_ABSORB_WINDOW_SEC = 20
DEFAULT_ABSORB_MAX_MOVE_ATR_K = 0.25
DEFAULT_ABSORB_MIN_VOL = 80
DEFAULT_TP_POINTS = 12.0
DEFAULT_SL_POINTS = 10.0
DEFAULT_MAX_HOLD_SEC = 120
DEFAULT_COOLDOWN_SEC = 180
DEFAULT_MIN_ATR = 25.0

PHASE0_GROSS_MIN = 5.0
PHASE0_NET_MIN = 0.0
PHASE0_MIN_N = 20

ImpulseDir = Literal["Long", "Short"]


@dataclass(frozen=True)
class ImpulseEpisode:
    day: dt.date
    impulse_dir: ImpulseDir
    start_idx: int
    end_idx: int
    bar_end_ts: int
    entry_price: float
    atr: float
    body_sum: float
    vol_sum: int
    exhaustion_kind: str
    absorb_score: float
    session_bucket: str


def _session_bars(bars: list[KBarRecord]) -> list[KBarRecord]:
    return [b for b in bars if SESSION_START <= b.ts.time() <= SESSION_END]


def _bar_range(bar: KBarRecord) -> float:
    return max(0.0, float(bar.High - bar.Low))


def _bar_body_signed(bar: KBarRecord) -> float:
    return float(bar.Close - bar.Open)


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


def _atr_at_bar_index(bars: list[KBarRecord], idx: int, *, period: int = DEFAULT_ATR_PERIOD) -> float:
    tuples = [
        (b.High, b.Low, b.Close, b.High - b.Low, float(b.Volume)) for b in bars[: idx + 1]
    ]
    atrs = atr_series_from_bars(tuples, period=period)
    if not atrs:
        return DEFAULT_MIN_ATR
    return max(float(atrs[-1]), DEFAULT_MIN_ATR)


def _is_bull(bar: KBarRecord) -> bool:
    return bar.Close > bar.Open


def _is_bear(bar: KBarRecord) -> bool:
    return bar.Close < bar.Open


def _impulse_direction(window: list[KBarRecord]) -> ImpulseDir | None:
    if all(_is_bull(b) for b in window):
        return "Long"
    if all(_is_bear(b) for b in window):
        return "Short"
    return None


def _body_sum(window: list[KBarRecord], direction: ImpulseDir) -> float:
    if direction == "Long":
        return sum(max(0.0, b.Close - b.Open) for b in window)
    return sum(max(0.0, b.Open - b.Close) for b in window)


def _exhaustion_kind(window: list[KBarRecord], vol_p80: float) -> str | None:
    last = window[-1]
    ranges = [_bar_range(b) for b in window]
    bodies = [abs(_bar_body_signed(b)) for b in window[:-1]] or [abs(_bar_body_signed(last))]
    mean_range = statistics.mean(ranges[:-1]) if len(ranges) > 1 else ranges[0]
    mean_body = statistics.mean(bodies) if bodies else 0.0
    last_range = ranges[-1]
    last_body = abs(_bar_body_signed(last))
    if float(last.Volume) >= vol_p80 and last_range < 0.55 * mean_range:
        return "climax_compress"
    if float(last.Volume) >= vol_p80 and last_body < 0.5 * mean_body:
        return "climax_body_shrink"
    return None


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


def _against_flow_vol(
    ticks: list[tuple[int, float, int, int]],
    *,
    start_ts: int,
    end_ts: int,
    impulse_dir: ImpulseDir,
) -> tuple[float, float, float]:
    """Return (against_vol, price_move, end_price) in absorb window."""
    start_price: float | None = None
    end_price = 0.0
    against_vol = 0.0
    for ts, price, vol, tick_type in ticks:
        if ts < start_ts:
            continue
        if ts > end_ts:
            break
        if start_price is None:
            start_price = price
        end_price = price
        # tick_type 1=buy, 2=sell (Shioaji convention in this codebase)
        if impulse_dir == "Long":
            if tick_type == 2:
                against_vol += vol
        else:
            if tick_type == 1:
                against_vol += vol
    if start_price is None:
        return 0.0, 0.0, 0.0
    return against_vol, abs(end_price - start_price), end_price


def simulate_scalp_exit(
    *,
    direction: ImpulseDir,
    entry_price: float,
    entry_ts: int,
    ticks: list[tuple[int, float, int, int]],
    tp_points: float,
    sl_points: float,
    max_hold_sec: int,
) -> dict[str, Any]:
    sign = _direction_sign(direction)
    end_ts = entry_ts + max_hold_sec
    mfe = 0.0
    mae = 0.0

    for ts, price, _vol, _tt in ticks:
        if ts < entry_ts:
            continue
        if ts > end_ts:
            break
        delta = sign * (price - entry_price)
        mfe = max(mfe, delta)
        mae = max(mae, -delta)
        if delta <= -sl_points:
            return {
                "gross_pnl": round(-sl_points, 2),
                "exit_reason": "stop_loss",
                "hold_sec": ts - entry_ts,
                "mfe": round(mfe, 2),
                "mae": round(mae, 2),
            }
        if delta >= tp_points:
            return {
                "gross_pnl": round(tp_points, 2),
                "exit_reason": "take_profit",
                "hold_sec": ts - entry_ts,
                "mfe": round(mfe, 2),
                "mae": round(mae, 2),
            }

    last_price = entry_price
    last_ts = entry_ts
    for ts, price, _v, _t in ticks:
        if entry_ts <= ts <= end_ts:
            last_price = price
            last_ts = ts
    gross = sign * (last_price - entry_price)
    return {
        "gross_pnl": round(gross, 2),
        "exit_reason": "time_stop",
        "hold_sec": last_ts - entry_ts,
        "mfe": round(mfe, 2),
        "mae": round(mae, 2),
    }


def fade_direction(impulse_dir: ImpulseDir) -> ImpulseDir:
    return "Short" if impulse_dir == "Long" else "Long"


def detect_impulse_entries_for_day(
    code: str,
    day: dt.date,
    *,
    cache_dir: Path,
    impulse_bars: int = 3,
    impulse_body_atr_k: float = DEFAULT_IMPULSE_BODY_ATR_K,
    impulse_vol_pct: float = DEFAULT_IMPULSE_VOL_PCT,
    absorb_window_sec: int = DEFAULT_ABSORB_WINDOW_SEC,
    absorb_max_move_atr_k: float = DEFAULT_ABSORB_MAX_MOVE_ATR_K,
    absorb_min_vol: int = DEFAULT_ABSORB_MIN_VOL,
    tp_points: float = DEFAULT_TP_POINTS,
    sl_points: float = DEFAULT_SL_POINTS,
    max_hold_sec: int = DEFAULT_MAX_HOLD_SEC,
    cooldown_sec: int = DEFAULT_COOLDOWN_SEC,
    friction_points: float = FRICTION_POINTS,
) -> list[dict[str, Any]]:
    kpath = resolve_kbar_path(cache_dir, code, day)
    if kpath is None:
        return []
    bars = _session_bars(load_kbars_csv(kpath))
    if len(bars) < impulse_bars + 1:
        return []

    vols = [float(b.Volume) for b in bars]
    vol_p70 = _percentile(vols, impulse_vol_pct)
    vol_p80 = _percentile(vols, 80.0)
    ticks = _tick_rows_for_day(code, day, cache_dir=cache_dir)

    rows: list[dict[str, Any]] = []
    last_entry_ts: int | None = None
    i = impulse_bars - 1
    while i < len(bars):
        window = bars[i - impulse_bars + 1 : i + 1]
        direction = _impulse_direction(window)
        if direction is None:
            i += 1
            continue

        if any(float(b.Volume) < vol_p70 for b in window):
            i += 1
            continue

        atr = _atr_at_bar_index(bars, i)
        body_sum = _body_sum(window, direction)
        if body_sum < impulse_body_atr_k * atr:
            i += 1
            continue

        exh = _exhaustion_kind(window, vol_p80)
        if exh is None:
            i += 1
            continue

        bar_end_ts = int(window[-1].ts.timestamp()) + 60
        if last_entry_ts is not None and bar_end_ts - last_entry_ts < cooldown_sec:
            i += 1
            continue

        absorb_start = bar_end_ts
        absorb_end = bar_end_ts + absorb_window_sec
        against_vol, price_move, entry_price = _against_flow_vol(
            ticks,
            start_ts=absorb_start,
            end_ts=absorb_end,
            impulse_dir=direction,
        )
        max_move = absorb_max_move_atr_k * atr
        if against_vol < absorb_min_vol or price_move > max_move or entry_price <= 0:
            i += 1
            continue

        trade_dir = fade_direction(direction)
        sim = simulate_scalp_exit(
            direction=trade_dir,
            entry_price=entry_price,
            entry_ts=absorb_end,
            ticks=ticks,
            tp_points=tp_points,
            sl_points=sl_points,
            max_hold_sec=max_hold_sec,
        )
        gross = float(sim["gross_pnl"])
        net = gross - friction_points
        rows.append(
            {
                "day": day.isoformat(),
                "ts": absorb_end,
                "impulse_dir": direction,
                "direction": trade_dir,
                "entry_price": round(entry_price, 1),
                "atr": round(atr, 2),
                "impulse_bars": impulse_bars,
                "body_sum": round(body_sum, 2),
                "exhaustion_kind": exh,
                "absorb_against_vol": round(against_vol, 1),
                "absorb_price_move": round(price_move, 2),
                "absorb_score": round(against_vol / max(price_move, 0.5), 2),
                "session_bucket": session_bucket_for_ts(absorb_end),
                "gross_scalp": gross,
                "net_scalp": net,
                "scalp_sim": sim,
            }
        )
        last_entry_ts = absorb_end
        i += impulse_bars

    return rows


def _group_summary(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row[key]), []).append(row)
    return {
        g: {"scalp": _summarize_gross_net("gross_scalp", "net_scalp", sub)}
        for g, sub in sorted(groups.items())
    }


def _evaluate_phase0_gate(
    summary_by_bars_and_bucket: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    best: dict[str, Any] | None = None
    passed = False
    for bars_k, buckets in summary_by_bars_and_bucket.items():
        for bucket, metrics in buckets.items():
            if bucket == "out_of_session":
                continue
            s = metrics.get("scalp") or {}
            n = int(s.get("n") or 0)
            gross = s.get("gross_mean")
            net = s.get("net_mean")
            if gross is None or net is None:
                continue
            candidate = {
                "impulse_bars": int(bars_k),
                "session_bucket": bucket,
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


def build_impulse_absorption_payload(
    *,
    code: str,
    cache_dir: Path,
    dates: list[dt.date] | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    impulse_bars_list: tuple[int, ...] = DEFAULT_IMPULSE_BARS,
    impulse_body_atr_k: float = DEFAULT_IMPULSE_BODY_ATR_K,
    impulse_vol_pct: float = DEFAULT_IMPULSE_VOL_PCT,
    absorb_window_sec: int = DEFAULT_ABSORB_WINDOW_SEC,
    absorb_max_move_atr_k: float = DEFAULT_ABSORB_MAX_MOVE_ATR_K,
    absorb_min_vol: int = DEFAULT_ABSORB_MIN_VOL,
    tp_points: float = DEFAULT_TP_POINTS,
    sl_points: float = DEFAULT_SL_POINTS,
    max_hold_sec: int = DEFAULT_MAX_HOLD_SEC,
    cooldown_sec: int = DEFAULT_COOLDOWN_SEC,
    friction_points: float = FRICTION_POINTS,
) -> dict[str, Any]:
    if dates is None:
        if from_date is None or to_date is None:
            raise ValueError("provide dates or from_date/to_date")
        dates = resolve_cli_tick_cache_dates(
            explicit=None,
            from_cache=True,
            code=code,
            cache_dir=cache_dir,
            from_date=from_date,
            to_date=to_date,
        )
    if not dates:
        raise ValueError("no dates to process")

    all_by_bars: dict[int, list[dict[str, Any]]] = {n: [] for n in impulse_bars_list}
    for day in dates:
        for n in impulse_bars_list:
            all_by_bars[n].extend(
                detect_impulse_entries_for_day(
                    code,
                    day,
                    cache_dir=cache_dir,
                    impulse_bars=n,
                    impulse_body_atr_k=impulse_body_atr_k,
                    impulse_vol_pct=impulse_vol_pct,
                    absorb_window_sec=absorb_window_sec,
                    absorb_max_move_atr_k=absorb_max_move_atr_k,
                    absorb_min_vol=absorb_min_vol,
                    tp_points=tp_points,
                    sl_points=sl_points,
                    max_hold_sec=max_hold_sec,
                    cooldown_sec=cooldown_sec,
                    friction_points=friction_points,
                )
            )

    summary_by_bars: dict[str, Any] = {}
    summary_by_bars_and_bucket: dict[str, dict[str, Any]] = {}
    for n in impulse_bars_list:
        rows = all_by_bars[n]
        summary_by_bars[str(n)] = {
            "scalp": _summarize_gross_net("gross_scalp", "net_scalp", rows),
        }
        summary_by_bars_and_bucket[str(n)] = _group_summary(rows, "session_bucket")

    phase0_gate = _evaluate_phase0_gate(summary_by_bars_and_bucket)
    date_from = min(dates).isoformat()
    date_to = max(dates).isoformat()

    return {
        "schema_version": SCHEMA_VERSION,
        "thesis": "momentum_exhaustion_reversal",
        "from_date": date_from,
        "to_date": date_to,
        "dates": [d.isoformat() for d in dates],
        "code": code,
        "friction_points_per_round_trip": friction_points,
        "sim_params": {
            "impulse_bars_list": list(impulse_bars_list),
            "impulse_body_atr_k": impulse_body_atr_k,
            "impulse_vol_pct": impulse_vol_pct,
            "absorb_window_sec": absorb_window_sec,
            "absorb_max_move_atr_k": absorb_max_move_atr_k,
            "absorb_min_vol": absorb_min_vol,
            "tp_points": tp_points,
            "sl_points": sl_points,
            "max_hold_sec": max_hold_sec,
            "cooldown_sec": cooldown_sec,
        },
        "phase0_gate": phase0_gate,
        "summary_by_impulse_bars": summary_by_bars,
        "summary_by_bars_and_bucket": summary_by_bars_and_bucket,
        "summary_by_direction": {
            str(n): _group_summary(all_by_bars[n], "direction") for n in impulse_bars_list
        },
        "entry_count_by_bars": {str(n): len(all_by_bars[n]) for n in impulse_bars_list},
        "entries": {str(n): all_by_bars[n] for n in impulse_bars_list},
    }
