"""Phase -1: HTF long-background census at 09:30 (OSF research)."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from reporting.osf_liquidity import compute_liquidity_levels
from reporting.osf_session_context import OsfBarStore
from reporting.smc_bar_structure import (
    analyze_bos,
    daily_bias_long,
    higher_lows_1h,
    range_position,
)
from storage.cache_paths import DEFAULT_TICK_CACHE_DIR
from storage.session_bar_cache import DAY_ANCHOR

HtfMode = Literal["none", "h4_only", "h4_h1", "full"]
CENSUS_AS_OF_TIME = datetime.time(9, 30)
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class HtfFlags:
    daily_long: bool
    h4_bos_long: bool
    h4_discount: bool
    h1_tactical_long: bool
    htf_full: bool
    htf_h4_only: bool
    gap_cohort: str


def evaluate_htf_at(
    snap,
    *,
    levels=None,
) -> HtfFlags:
    price = float(snap.bars_1m[-1].Close) if snap.bars_1m else 0.0
    daily_long = daily_bias_long(snap.daily_closed, ma20=snap.daily_ma20)
    bos_4h = analyze_bos(snap.closed.get("4h", []), swing_lookback=2)
    h4_bos_long = bos_4h.last_bos == "bullish"
    h4_discount = range_position(snap.closed.get("4h", []), price, lookback=10) == "discount"
    bos_1h = analyze_bos(snap.closed.get("1h", []), swing_lookback=2)
    h1_ok = bos_1h.last_bos != "bearish" and (
        bos_1h.last_bos == "bullish" or higher_lows_1h(snap.closed.get("1h", []))
    )
    htf_full = daily_long and h4_bos_long and h4_discount and h1_ok
    htf_h4_only = h4_bos_long and h4_discount
    gap = levels.gap_cohort if levels is not None else "flat"
    return HtfFlags(
        daily_long=daily_long,
        h4_bos_long=h4_bos_long,
        h4_discount=h4_discount,
        h1_tactical_long=h1_ok,
        htf_full=htf_full,
        htf_h4_only=htf_h4_only,
        gap_cohort=gap,
    )


def htf_allows(flags: HtfFlags, mode: HtfMode) -> bool:
    if mode == "none":
        return True
    if mode == "h4_only":
        return flags.htf_h4_only
    if mode == "h4_h1":
        return flags.htf_h4_only and flags.h1_tactical_long
    return flags.htf_full


def census_one_day(
    code: str,
    day: datetime.date,
    *,
    store: OsfBarStore,
) -> dict[str, Any] | None:
    as_of = datetime.datetime.combine(day, CENSUS_AS_OF_TIME)
    or_end = datetime.datetime.combine(day, DAY_ANCHOR) + datetime.timedelta(minutes=30)
    snap_or = store.snapshot(or_end)
    snap = store.snapshot(as_of)
    levels = compute_liquidity_levels(snap_or.bars_1m, day)
    flags = evaluate_htf_at(snap, levels=levels)
    return {
        "day": day.isoformat(),
        "as_of": as_of.isoformat(),
        "gap_cohort": flags.gap_cohort,
        "gap_points": round(levels.gap_points, 1),
        "or_valid": levels.or_range.valid,
        "daily_long": flags.daily_long,
        "h4_bos_long": flags.h4_bos_long,
        "h4_discount": flags.h4_discount,
        "h1_tactical_long": flags.h1_tactical_long,
        "htf_full": flags.htf_full,
        "htf_h4_only": flags.htf_h4_only,
        "dawn_low": levels.dawn_low,
        "overnight_low": levels.overnight_low,
    }


def _pct(n: int, total: int) -> float:
    return round(n / total, 4) if total else 0.0


def _group_days_by_month(days: list[datetime.date]) -> list[tuple[str, list[datetime.date]]]:
    buckets: dict[str, list[datetime.date]] = {}
    for day in sorted(days):
        buckets.setdefault(day.strftime("%Y-%m"), []).append(day)
    return sorted(buckets.items())


def _census_rows_for_days(
    code: str,
    days: list[datetime.date],
    *,
    cache_dir: Path,
) -> list[dict[str, Any]]:
    store = OsfBarStore.load_range(code, days, cache_dir=cache_dir)
    if store is None:
        return []
    rows: list[dict[str, Any]] = []
    for day in sorted(days):
        row = census_one_day(code, day, store=store)
        if row is not None:
            rows.append(row)
    return rows


def build_census_payload(
    code: str,
    days: list[datetime.date],
    *,
    cache_dir: Path = DEFAULT_TICK_CACHE_DIR,
    batch_by_month: bool = True,
) -> dict[str, Any]:
    if not days:
        return {
            "schema_version": SCHEMA_VERSION,
            "code": code,
            "rows": [],
            "by_month": {},
            "decision_hint": "no_data",
            "avg_htf_full_pct": 0.0,
            "avg_htf_h4_only_pct": 0.0,
        }
    rows: list[dict[str, Any]] = []
    if batch_by_month and len(_group_days_by_month(days)) > 1:
        for _, month_days in _group_days_by_month(days):
            rows.extend(_census_rows_for_days(code, month_days, cache_dir=cache_dir))
    else:
        rows = _census_rows_for_days(code, days, cache_dir=cache_dir)
    if not rows:
        return {
            "schema_version": SCHEMA_VERSION,
            "code": code,
            "rows": [],
            "by_month": {},
            "decision_hint": "no_data",
            "avg_htf_full_pct": 0.0,
            "avg_htf_h4_only_pct": 0.0,
        }

    by_month: dict[str, dict[str, Any]] = {}
    for row in rows:
        month = row["day"][:7]
        bucket = by_month.setdefault(
            month,
            {
                "trading_days": 0,
                "daily_long": 0,
                "h4_bos_long": 0,
                "h4_discount": 0,
                "h1_tactical_long": 0,
                "htf_full": 0,
                "htf_h4_only": 0,
                "gap_up": 0,
                "gap_down": 0,
                "gap_flat": 0,
            },
        )
        bucket["trading_days"] += 1
        for key in (
            "daily_long",
            "h4_bos_long",
            "h4_discount",
            "h1_tactical_long",
            "htf_full",
            "htf_h4_only",
        ):
            if row[key]:
                bucket[key] += 1
        gc = row["gap_cohort"]
        if gc == "gap_up":
            bucket["gap_up"] += 1
        elif gc == "gap_down":
            bucket["gap_down"] += 1
        else:
            bucket["gap_flat"] += 1

    summary: dict[str, Any] = {}
    for month, bucket in sorted(by_month.items()):
        n = bucket["trading_days"]
        summary[month] = {
            "trading_days": n,
            "daily_long_pct": _pct(bucket["daily_long"], n),
            "h4_bos_long_pct": _pct(bucket["h4_bos_long"], n),
            "h4_discount_pct": _pct(bucket["h4_discount"], n),
            "h1_tactical_long_pct": _pct(bucket["h1_tactical_long"], n),
            "htf_full_pct": _pct(bucket["htf_full"], n),
            "htf_h4_only_pct": _pct(bucket["htf_h4_only"], n),
            "gap_up_pct": _pct(bucket["gap_up"], n),
            "gap_down_pct": _pct(bucket["gap_down"], n),
            "gap_flat_pct": _pct(bucket["gap_flat"], n),
        }

    full_pcts = [summary[m]["htf_full_pct"] for m in summary]
    h4_pcts = [summary[m]["htf_h4_only_pct"] for m in summary]
    avg_full = sum(full_pcts) / len(full_pcts) if full_pcts else 0.0
    avg_h4 = sum(h4_pcts) / len(h4_pcts) if h4_pcts else 0.0
    hint = "proceed_full"
    if avg_full < 0.10 and avg_h4 < 0.20:
        hint = "block_tighten_htf"
    elif avg_full < 0.15:
        hint = "prefer_h4_only_mainline"

    return {
        "schema_version": SCHEMA_VERSION,
        "code": code,
        "rows": rows,
        "by_month": summary,
        "decision_hint": hint,
        "avg_htf_full_pct": round(avg_full, 4),
        "avg_htf_h4_only_pct": round(avg_h4, 4),
    }