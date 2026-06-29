"""Regime join at entry_ts for Entry Lab (no lookahead)."""

from __future__ import annotations

import datetime as dt
from typing import Any

from reporting.gap_drive_continuation_counterfactual import MIN_GAP_PTS
from reporting.structure_calibration import (
    TrendHarnessConfig,
    compute_structure_snapshot,
    compute_trend_snapshot,
)
from storage.kbar_loader import KBarRecord, iter_kbars_in_range
from strategy_vwap_momentum.structure import filter_closed_bars_1m, session_slice_bars_1m


def _session_bars_for_day(bars: list[KBarRecord]) -> list[KBarRecord]:
    if not bars:
        return []
    return list(bars)


def _atr_percentile_session(
    bars: list[KBarRecord],
    as_of_ts: int,
    entry_atr: float,
) -> float | None:
    exchange_dt = dt.datetime.fromtimestamp(as_of_ts)
    closed = filter_closed_bars_1m(bars, exchange_dt)
    session = session_slice_bars_1m(closed, exchange_dt, used_long_lookback=False)
    ranges = [
        float(b.High - b.Low)
        for b in session
        if b.ts <= exchange_dt
    ]
    if not ranges or entry_atr <= 0:
        return None
    below = sum(1 for r in ranges if r <= entry_atr)
    return round(100.0 * below / len(ranges), 1)


def _alignment_label(direction: str, regime_label: str) -> str:
    if regime_label in ("neutral", "unknown", "Flat"):
        return "neutral"
    if direction == regime_label:
        return "with_trend"
    return "counter_trend"


def regime_snapshot_for_entry(
    bars: list[KBarRecord],
    *,
    entry_ts: int,
    atr: float,
) -> dict[str, Any]:
    state = compute_structure_snapshot(bars, atr=atr, as_of_ts=entry_ts)
    trend_dir, trend_strength = compute_trend_snapshot(
        bars, atr=atr, as_of_ts=entry_ts, trend_cfg=TrendHarnessConfig()
    )
    atr_pct = _atr_percentile_session(bars, entry_ts, atr)
    return {
        "trend_dir": trend_dir,
        "trend_strength": round(float(trend_strength), 4),
        "structure_bias": state.bias,
        "structure_strength": round(float(state.strength), 4),
        "in_discount": state.in_discount,
        "in_premium": state.in_premium,
        "structure_last_bos": state.last_bos,
        "atr_percentile_session": atr_pct,
    }


def compute_alignment(
    row: dict[str, Any],
    regime: dict[str, Any],
) -> dict[str, str]:
    direction = str(row.get("direction", "Long"))
    r1 = _alignment_label(direction, regime.get("trend_dir") or "unknown")
    bias = regime.get("structure_bias") or "Neutral"
    if bias == "Neutral":
        r2 = "neutral"
    else:
        r2 = _alignment_label(direction, bias)
    if direction == "Long":
        r3 = "with_trend" if regime.get("in_discount") else (
            "counter_trend" if regime.get("in_premium") else "neutral"
        )
    else:
        r3 = "with_trend" if regime.get("in_premium") else (
            "counter_trend" if regime.get("in_discount") else "neutral"
        )
    atr_pct = regime.get("atr_percentile_session")
    if atr_pct is None:
        r4 = "unknown"
    else:
        r4 = "low_vol" if float(atr_pct) <= 50 else "high_vol"

    gdc_gap = "n/a"
    gap_pts = row.get("gap_pts")
    if gap_pts is not None:
        gap_f = float(gap_pts)
        if gap_f > MIN_GAP_PTS and direction == "Long" and bias == "Short":
            gdc_gap = "gap_up_structure_bear"
        elif gap_f > MIN_GAP_PTS and direction == "Long":
            gdc_gap = "gap_aligned"
        elif gap_f < -MIN_GAP_PTS and direction == "Short":
            gdc_gap = "gap_aligned"

    return {"r1": r1, "r2": r2, "r3": r3, "r4": r4, "gdc_gap_structure": gdc_gap}


def enrich_rows_with_regime(
    rows: list[dict[str, Any]],
    *,
    code: str,
    cache_dir: Any,
) -> None:
    """Attach regime + alignment per row. Mutates rows in place."""
    if not rows:
        return

    days: list[dt.date] = []
    for row in rows:
        day_s = str(row.get("day") or "")
        if day_s:
            days.append(dt.date.fromisoformat(day_s))
    if not days:
        return

    from pathlib import Path

    cache = Path(cache_dir)
    min_day, max_day = min(days), max(days)
    lookback_start = min_day - dt.timedelta(days=7)
    bars_all = iter_kbars_in_range(code, lookback_start, max_day, cache_dir=cache)

    for row in rows:
        day_s = str(row.get("day") or "")
        if not day_s:
            continue
        ts = int(row["ts"])
        atr = float(row.get("atr") or 0)
        regime = regime_snapshot_for_entry(bars_all, entry_ts=ts, atr=atr)
        row["regime"] = regime
        row["alignment"] = compute_alignment(row, regime)


def regime_agreement_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"n": 0}

    def _binary(align: str) -> int | None:
        if align == "with_trend":
            return 1
        if align == "counter_trend":
            return 0
        return None

    pairs: list[tuple[str, str]] = [
        ("r1", "r2"),
        ("r1", "r3"),
        ("r2", "r3"),
    ]
    agreement: dict[str, Any] = {}
    for a, b in pairs:
        same = 0
        total = 0
        for r in rows:
            al = r.get("alignment") or {}
            va, vb = al.get(a), al.get(b)
            if va in (None, "unknown", "neutral") or vb in (None, "unknown", "neutral"):
                continue
            if va == vb:
                same += 1
            total += 1
        agreement[f"{a}_vs_{b}"] = {
            "agreement_rate": round(same / total, 3) if total else None,
            "n": total,
        }
    return {"n": len(rows), "pairwise_agreement": agreement}
