"""Night + cross-day outlook helpers for OSF replay (post-entry / EOD context)."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, Sequence

from reporting.osf_session_context import (
    OSF_OUTLOOK_TF_TABLE,
    OsfBarStore,
    dawn_bars,
    overnight_bars_before_open,
)
from storage.kbar_loader import KBarRecord
from storage.session_bar_cache import (
    DAY_ANCHOR,
    DAY_END,
    DAWN_END,
    NIGHT_ANCHOR,
    sma,
)

H1_MA_PERIODS = (20, 60)
H4_OUTLOOK_BARS = 20


def _bar_row(b: KBarRecord, *, extras: dict[str, Any] | None = None) -> dict[str, Any]:
    row: dict[str, Any] = {
        "ts": b.ts.isoformat(),
        "O": round(float(b.Open), 1),
        "H": round(float(b.High), 1),
        "L": round(float(b.Low), 1),
        "C": round(float(b.Close), 1),
    }
    if extras:
        row.update(extras)
    return row


def h1_rows_with_mas(
    bars_1h: Sequence[KBarRecord],
    *,
    tail: int | None = None,
    ma_periods: Sequence[int] = H1_MA_PERIODS,
) -> list[dict[str, Any]]:
    series = list(bars_1h)
    if tail is not None:
        series = series[-tail:]
    closes = [float(b.Close) for b in bars_1h]
    rows: list[dict[str, Any]] = []
    for b in series:
        idx = next(i for i, x in enumerate(bars_1h) if x.ts == b.ts)
        sub = closes[: idx + 1]
        extras = {f"ma{p}": round(v, 1) if (v := sma(sub, p)) is not None else None for p in ma_periods}
        rows.append(_bar_row(b, extras=extras))
    return rows


def evening_through_dawn_bars(
    bars_1m: Sequence[KBarRecord],
    day: datetime.date,
) -> list[KBarRecord]:
    """``day`` 15:00 → next calendar dawn 05:00."""
    nxt = day + datetime.timedelta(days=1)
    start = datetime.datetime.combine(day, NIGHT_ANCHOR)
    end = datetime.datetime.combine(nxt, DAWN_END)
    return [b for b in bars_1m if start <= b.ts <= end]


def _next_calendar_day(day: datetime.date, trading_days: Sequence[datetime.date]) -> datetime.date | None:
    for d in trading_days:
        if d > day:
            return d
    return None


def build_day_outlook(
    store: OsfBarStore,
    day: datetime.date,
    *,
    as_of: datetime.datetime | None = None,
) -> dict[str, Any]:
    """Day + night + optional next-session preview for replay charts."""
    as_of = as_of or datetime.datetime.combine(day, DAY_END)
    snap = store.snapshot(as_of)
    # Use extended as_of so MA60 is computed on full 1h history, then slice for display.
    snap_full = store.snapshot(
        datetime.datetime.combine(day + datetime.timedelta(days=2), DAY_ANCHOR)
    )
    full_h1 = snap_full.closed.get("1h", [])
    h1_all_rows = h1_rows_with_mas(full_h1)
    eod_cut = datetime.datetime.combine(day, DAY_END).isoformat()
    bars_1h = [b for b in full_h1 if b.ts.isoformat() <= eod_cut]
    bars_4h = snap_full.closed.get("4h", [])
    bars_15m = snap.closed.get("15m", [])

    day_start = datetime.datetime.combine(day, DAY_ANCHOR)
    day_end = datetime.datetime.combine(day, DAY_END)
    b15_day = [b for b in bars_15m if day_start <= b.ts <= day_end]

    outlook_as_of = datetime.datetime.combine(day + datetime.timedelta(days=1), DAY_ANCHOR)
    snap_night = store.snapshot(outlook_as_of)
    night_1m = evening_through_dawn_bars(snap_night.bars_1m, day)

    next_day = _next_calendar_day(day, store.trading_days)
    next_preview: dict[str, Any] | None = None
    if next_day is not None:
        snap_next = store.snapshot(datetime.datetime.combine(next_day, DAY_ANCHOR))
        levels_next = None
        if snap_next.bars_1m:
            from reporting.osf_liquidity import compute_gap_cohort

            gap_cohort, gap_pts, day_open, ref_close = compute_gap_cohort(
                snap_next.bars_1m, next_day
            )
            dawn = dawn_bars(list(snap_next.bars_1m), next_day)
            overnight = overnight_bars_before_open(list(snap_next.bars_1m), next_day)
            next_preview = {
                "day": next_day.isoformat(),
                "gap_cohort": gap_cohort,
                "gap_points": round(gap_pts, 1),
                "day_open": day_open,
                "ref_close": ref_close,
                "dawn_low": min((float(b.Low) for b in dawn), default=None),
                "overnight_low": min((float(b.Low) for b in overnight), default=None),
            }

    night_cut = datetime.datetime.combine(day, NIGHT_ANCHOR).isoformat()
    dawn_cut = datetime.datetime.combine(day + datetime.timedelta(days=1), DAY_ANCHOR).isoformat()

    return {
        "as_of": as_of.isoformat(),
        "h1_bars": [r for r in h1_all_rows if r["ts"] <= eod_cut][-24:],
        "h1_post_night": [
            r for r in h1_all_rows if night_cut <= r["ts"] < dawn_cut
        ][-12:],
        "h1_ma_note": (
            f"Full 1h history in store: {len(full_h1)} bars; "
            f"MA60 needs ≥60 bars before each row's ts."
        ),
        "h4_bars": [_bar_row(b) for b in bars_4h[-H4_OUTLOOK_BARS:]],
        "m15_day": [_bar_row(b) for b in b15_day],
        "night_1m_summary": {
            "bars": len(night_1m),
            "high": max((float(b.High) for b in night_1m), default=None),
            "low": min((float(b.Low) for b in night_1m), default=None),
            "last_close": float(night_1m[-1].Close) if night_1m else None,
            "first_ts": night_1m[0].ts.isoformat() if night_1m else None,
            "last_ts": night_1m[-1].ts.isoformat() if night_1m else None,
        },
        "night_1h": [
            r for r in h1_all_rows if r["ts"] >= night_cut
        ][:12],
        "next_session_preview": next_preview,
    }


def load_store_for_outlook(
    code: str,
    day: datetime.date,
    *,
    cache_dir: Path,
) -> OsfBarStore | None:
    """Load target day plus following calendar days so night/dawn fit in memory."""
    days = [day, day + datetime.timedelta(days=1), day + datetime.timedelta(days=2)]
    return OsfBarStore.load_range(
        code, days, cache_dir=cache_dir, tf_table=OSF_OUTLOOK_TF_TABLE
    )