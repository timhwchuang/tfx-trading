"""Memory-efficient per-day bar context for OSF research.

One disk load per batch, then no-lookahead snapshots via bisect on precomputed
closed series. Multi-day batches size the 1m load window via daily_lookback
(linear in batch span) and rebuild untrimmed closed series so early days are
not dropped by SessionBarCache TF trim.
"""

from __future__ import annotations

import bisect
import datetime
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from storage.cache_paths import DEFAULT_TICK_CACHE_DIR
from storage.kbar_loader import KBarRecord
from storage.session_bar_cache import (
    DAY_ANCHOR,
    DAY_END,
    DAWN_END,
    NIGHT_ANCHOR,
    SessionBarCache,
    TfSpec,
    build_session_daily_bars,
    filter_bars_by_scope,
    sma,
    yuanta_resample,
)

SessionScope = Literal["day", "night", "both"]
_TF_MIN = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240}
_SCOPE = {"1m": "day", "5m": "day", "15m": "both", "1h": "both", "4h": "both"}

# OSF: daily MA20; 1h/4h MA60 needs lookback≥60 on closed series.
OSF_TF_TABLE: dict[str, TfSpec] = {
    "1m": TfSpec(1, 120, "day"),
    "5m": TfSpec(5, 12, "day"),
    "15m": TfSpec(15, 48, "both"),
    "1h": TfSpec(60, 120, "both"),
    "4h": TfSpec(240, 120, "both"),
}
# Multi-day outlook load must retain day-session 15m after night bars append.
OSF_OUTLOOK_TF_TABLE: dict[str, TfSpec] = {
    **OSF_TF_TABLE,
    "15m": TfSpec(15, 144, "both"),
}
OSF_DAILY_LOOKBACK = 28
OSF_TIMELINE_DAILY_LOOKBACK = 120
_SNAP_CACHE_MAX = 48


def _batch_span_days(days: list[datetime.date]) -> int:
    """Number of trading days that must sit inside the 1m load window.

    Callers pass trading-day lists (census/CF month-batch). Use ``len(days)``
    only — do not inflate from calendar span (sparse multi-month endpoints
    would otherwise explode memory). Sparse ranges should be month-batched.
    """
    if not days:
        return 0
    return max(1, len(days))


def load_window_daily_lookback(
    n_batch_days: int,
    *,
    daily_lookback: int = OSF_DAILY_LOOKBACK,
) -> int:
    """Trading-day window size for SessionBarCache multi-day load.

    Drive the load window via ``daily_lookback`` (linear in batch span) so early
    batch days stay inside the on-disk 1m window. Closed TFs are rebuilt
    untrimmed from that 1m series (SessionBarCache still trims live TF lookbacks).
    """
    return daily_lookback + max(0, n_batch_days - 1)


def _rebuild_closed_untrimmed(
    bars_1m: list[KBarRecord],
    tf_table: dict[str, TfSpec],
    as_of: datetime.datetime,
) -> dict[str, list[KBarRecord]]:
    """Resample full load-window 1m → closed TFs without lookback trim."""
    closed: dict[str, list[KBarRecord]] = {}
    for name, spec in tf_table.items():
        scoped = filter_bars_by_scope(bars_1m, spec.session)
        series, _ = yuanta_resample(scoped, spec.minutes, spec.session, as_of)
        closed[name] = series
    return closed


def overnight_evening_start_from_bars(
    bars_1m: Sequence[KBarRecord],
    day: datetime.date,
) -> datetime.datetime | None:
    """15:00 on the last date that has day-session 1m bars before ``day`` open.

    **Disk SSOT:** a date with day-session bars is a trading day; a date with no
    bars is not. No ``trade_days`` / holiday calendar, no weekend heuristics —
    assume kbar cache is complete and correct. Returns ``None`` when the loaded
    series has no prior day session (caller treats overnight as empty).
    """
    day_open = datetime.datetime.combine(day, DAY_ANCHOR)
    prior_day_sess = [
        b for b in filter_bars_by_scope(list(bars_1m), "day") if b.ts < day_open
    ]
    if not prior_day_sess:
        return None
    last_day = max(b.ts.date() for b in prior_day_sess)
    return datetime.datetime.combine(last_day, NIGHT_ANCHOR)


@dataclass
class BarSnapshot:
    as_of: datetime.datetime
    bars_1m: list[KBarRecord]
    closed: dict[str, list[KBarRecord]] = field(default_factory=dict)
    daily_closed: list[KBarRecord] = field(default_factory=list)
    daily_ma20: float | None = None


@dataclass
class OsfBarStore:
    """Single disk load for a date range; serves many days via bisect snapshots."""

    code: str
    trading_days: list[datetime.date]
    _bars_1m: list[KBarRecord]
    _ts_index: list[datetime.datetime]
    _closed_full: dict[str, list[KBarRecord]] = field(default_factory=dict, repr=False)
    _closed_ts_index: dict[str, list[datetime.datetime]] = field(
        default_factory=dict, repr=False
    )
    _daily_full: list[KBarRecord] = field(default_factory=list, repr=False)
    _daily_ts_index: list[datetime.datetime] = field(default_factory=list, repr=False)
    _snap_cache: dict[datetime.datetime, BarSnapshot] = field(
        default_factory=dict, repr=False
    )

    @classmethod
    def load_range(
        cls,
        code: str,
        days: list[datetime.date],
        *,
        cache_dir: Path = DEFAULT_TICK_CACHE_DIR,
        tf_table: dict[str, TfSpec] | None = None,
        daily_lookback: int = OSF_DAILY_LOOKBACK,
    ) -> OsfBarStore | None:
        if not days:
            return None
        end_day = max(days)
        as_of_end = datetime.datetime.combine(end_day, DAY_END)
        base_table = tf_table or OSF_TF_TABLE
        n_batch = _batch_span_days(days)
        # Linear load window: daily_lookback + batch span (not TF bar-count expand).
        load_daily = load_window_daily_lookback(n_batch, daily_lookback=daily_lookback)
        cache = SessionBarCache.load(
            code,
            as_of_end,
            cache_dir=cache_dir,
            tf_table=base_table,
            daily_lookback=load_daily,
        )
        bars = cache.bars_1m_as_of(as_of_end)
        if not bars:
            return None
        # Untrimmed closed series: snapshots bisect by as_of; TF lookback trim
        # would drop early-month 15m/5m/HTF and zero out funnel / setups.
        closed_full = _rebuild_closed_untrimmed(bars, base_table, as_of_end)
        closed_ts_index = {
            tf: [b.ts for b in series] for tf, series in closed_full.items()
        }
        daily_full = build_session_daily_bars(
            filter_bars_by_scope(bars, "both"),
            list(cache.trading_days),
            as_of_end,
        )
        return cls(
            code=code,
            trading_days=list(cache.trading_days),
            _bars_1m=bars,
            _ts_index=[b.ts for b in bars],
            _closed_full=closed_full,
            _closed_ts_index=closed_ts_index,
            _daily_full=daily_full,
            _daily_ts_index=[b.ts for b in daily_full],
        )

    def _slice_1m(self, as_of: datetime.datetime) -> list[KBarRecord]:
        idx = bisect.bisect_right(self._ts_index, as_of)
        return self._bars_1m[:idx]

    def _slice_series(
        self,
        series: list[KBarRecord],
        ts_index: list[datetime.datetime],
        as_of: datetime.datetime,
    ) -> list[KBarRecord]:
        end = bisect.bisect_right(ts_index, as_of)
        return series[:end]

    def snapshot(self, as_of: datetime.datetime) -> BarSnapshot:
        key = as_of.replace(second=0, microsecond=0)
        hit = self._snap_cache.get(key)
        if hit is not None:
            return hit
        if len(self._snap_cache) >= _SNAP_CACHE_MAX:
            oldest = next(iter(self._snap_cache))
            del self._snap_cache[oldest]
        snap = self._build_snapshot(as_of)
        self._snap_cache[key] = snap
        return snap

    def _build_snapshot(self, as_of: datetime.datetime) -> BarSnapshot:
        bars_1m = self._slice_1m(as_of)
        if self._closed_full:
            closed = {
                tf: self._slice_series(series, self._closed_ts_index[tf], as_of)
                for tf, series in self._closed_full.items()
            }
            daily = self._slice_series(
                self._daily_full, self._daily_ts_index, as_of
            )
            closes = [float(b.Close) for b in daily]
            # Point-in-time only: insufficient history → None (no end-of-batch fallback).
            ma20 = sma(closes, 20)
            return BarSnapshot(
                as_of=as_of,
                bars_1m=bars_1m,
                closed=closed,
                daily_closed=daily,
                daily_ma20=ma20,
            )
        closed = {"1m": bars_1m}
        for tf, minutes in _TF_MIN.items():
            if tf == "1m":
                continue
            scope: SessionScope = _SCOPE[tf]  # type: ignore[assignment]
            scoped = filter_bars_by_scope(bars_1m, scope)
            c, _ = yuanta_resample(scoped, minutes, scope, as_of)
            closed[tf] = c
        both = filter_bars_by_scope(bars_1m, "both")
        daily = build_session_daily_bars(both, self.trading_days, as_of)
        closes = [float(b.Close) for b in daily]
        return BarSnapshot(
            as_of=as_of,
            bars_1m=bars_1m,
            closed=closed,
            daily_closed=daily,
            daily_ma20=sma(closes, 20),
        )


@dataclass
class OsfDayContext:
    """Per-day view over a shared store (no extra disk I/O)."""

    code: str
    day: datetime.date
    _store: OsfBarStore

    @classmethod
    def load(
        cls,
        code: str,
        day: datetime.date,
        *,
        cache_dir: Path = DEFAULT_TICK_CACHE_DIR,
        store: OsfBarStore | None = None,
    ) -> OsfDayContext | None:
        if store is None:
            store = OsfBarStore.load_range(code, [day], cache_dir=cache_dir)
        if store is None:
            return None
        return cls(code=code, day=day, _store=store)

    @property
    def trading_days(self) -> list[datetime.date]:
        return self._store.trading_days

    def snapshot(self, as_of: datetime.datetime) -> BarSnapshot:
        return self._store.snapshot(as_of)


def session_day_bars(bars_1m: list[KBarRecord], day: datetime.date) -> list[KBarRecord]:
    start = datetime.datetime.combine(day, DAY_ANCHOR)
    end = datetime.datetime.combine(day, DAY_END)
    return [b for b in bars_1m if start <= b.ts <= end]


def overnight_bars_before_open(
    bars_1m: list[KBarRecord],
    day: datetime.date,
) -> list[KBarRecord]:
    """Bars from last observed day-session evening 15:00 through 08:44 on ``day``.

    Window start is derived only from 1m bars already loaded (disk SSOT):
    last date with day-session data → that day's 15:00. No calendar guesswork.
    Empty if no prior day-session bars exist in ``bars_1m``.
    """
    night_start = overnight_evening_start_from_bars(bars_1m, day)
    if night_start is None:
        return []
    day_open = datetime.datetime.combine(day, DAY_ANCHOR)
    return [b for b in bars_1m if night_start <= b.ts < day_open]


def dawn_bars(bars_1m: list[KBarRecord], day: datetime.date) -> list[KBarRecord]:
    start = datetime.datetime.combine(day, datetime.time(0, 0))
    end = datetime.datetime.combine(day, DAWN_END)
    return [b for b in bars_1m if start <= b.ts <= end]
