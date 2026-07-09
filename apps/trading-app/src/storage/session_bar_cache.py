"""Yuanta-anchored multi-timeframe bar cache from per-day 1m kbar CSV files."""

from __future__ import annotations

import datetime
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal, Sequence

from storage.cache_paths import DEFAULT_TICK_CACHE_DIR, DEFAULT_TRADE_DAYS_DIR
from storage.kbar_loader import KBarRecord, iter_kbars_in_range, resolve_kbar_path
from storage.taiwan_calendar import resolve_trading_days_in_range_with_fallback
from storage.tick_loader import date_range

logger = logging.getLogger(__name__)

SessionScope = Literal["day", "night", "both"]

DAY_ANCHOR = datetime.time(8, 45)
DAY_END = datetime.time(13, 45)
DAY_SETTLEMENT_TAIL = datetime.time(13, 46)
NIGHT_ANCHOR = datetime.time(15, 0)
DAWN_END = datetime.time(5, 0)
DAWN_SETTLEMENT_TAIL = datetime.time(5, 1)

BarRecord = KBarRecord

_TRADING_DAYS_BUFFER = 5
_MIN_TRADING_DAYS = 10
_EDGE_TOLERANCE_MIN = 1

EXPECTED_DAY_BARS = 300
EXPECTED_DAWN_BARS = 300


@dataclass(frozen=True)
class TfSpec:
    minutes: int
    lookback: int
    session: SessionScope = "both"


DEFAULT_TF_TABLE: dict[str, TfSpec] = {
    "1m": TfSpec(1, 300, "day"),
    "3m": TfSpec(3, 100, "day"),
    "5m": TfSpec(5, 12, "day"),
    "15m": TfSpec(15, 24, "both"),
    "30m": TfSpec(30, 20, "both"),
    "1h": TfSpec(60, 20, "both"),
    "4h": TfSpec(240, 40, "both"),
}

DAILY_LOOKBACK = 90
DAILY_MA_PERIODS = (5, 20, 60)


@dataclass(frozen=True)
class TodayKbarStatus:
    """Bundle-aware readiness for calendar day D (disk candidates + optional memory)."""

    date: datetime.date
    file_exists: bool
    total_bars: int
    dawn_bars: int
    day_bars: int
    is_saturday: bool
    is_trading_day: bool
    ready: bool
    reason: str


@dataclass
class _TfSeries:
    closed: list[BarRecord] = field(default_factory=list)
    current: BarRecord | None = None


def _combine(day: datetime.date, t: datetime.time) -> datetime.datetime:
    return datetime.datetime.combine(day, t)


def _bar_minute_end(bar: BarRecord) -> datetime.datetime:
    return bar.ts + datetime.timedelta(minutes=1)


def _is_day_settlement_tail(bar: BarRecord) -> bool:
    return bar.ts.time() == DAY_SETTLEMENT_TAIL


def _is_dawn_settlement_tail(bar: BarRecord) -> bool:
    return bar.ts.time() == DAWN_SETTLEMENT_TAIL


def _in_day_session(bar: BarRecord) -> bool:
    t = bar.ts.time()
    return DAY_ANCHOR <= t <= DAY_END or _is_day_settlement_tail(bar)


def _in_dawn_session(bar: BarRecord) -> bool:
    t = bar.ts.time()
    return t <= DAWN_END or _is_dawn_settlement_tail(bar)


def _in_night_session(bar: BarRecord) -> bool:
    t = bar.ts.time()
    return t <= DAWN_END or t >= NIGHT_ANCHOR


def count_session_bars(bars: Sequence[BarRecord]) -> tuple[int, int, int]:
    dawn = sum(1 for b in bars if _in_dawn_session(b))
    day = sum(1 for b in bars if _in_day_session(b))
    return len(bars), dawn, day


def _session_count_kind(bar: BarRecord) -> Literal["dawn", "day"] | None:
    if _in_dawn_session(bar):
        return "dawn"
    if _in_day_session(bar):
        return "day"
    return None


def _assess_today_status(
    day: datetime.date,
    *,
    trading_days: Sequence[datetime.date],
    file_exists: bool,
    total_bars: int,
    dawn_bars: int,
    day_bars: int,
) -> TodayKbarStatus:
    """Shared readiness logic for on-disk and in-memory 1m bar sets."""
    is_saturday = day.weekday() == 5
    is_trading = day in set(trading_days)
    if not file_exists:
        return TodayKbarStatus(
            date=day,
            file_exists=False,
            total_bars=0,
            dawn_bars=0,
            day_bars=0,
            is_saturday=is_saturday,
            is_trading_day=is_trading,
            ready=False,
            reason="missing_file",
        )

    total, dawn, day_n = total_bars, dawn_bars, day_bars

    if is_saturday:
        min_dawn = EXPECTED_DAWN_BARS - _EDGE_TOLERANCE_MIN
        ready = dawn >= min_dawn
        reason = "ok" if ready else f"dawn_short:{dawn}<{min_dawn}"
        return TodayKbarStatus(
            date=day,
            file_exists=True,
            total_bars=total,
            dawn_bars=dawn,
            day_bars=day_n,
            is_saturday=True,
            is_trading_day=is_trading,
            ready=ready,
            reason=reason,
        )

    if not is_trading:
        return TodayKbarStatus(
            date=day,
            file_exists=True,
            total_bars=total,
            dawn_bars=dawn,
            day_bars=day_n,
            is_saturday=False,
            is_trading_day=False,
            ready=False,
            reason="not_trading_day",
        )

    min_day = EXPECTED_DAY_BARS - _EDGE_TOLERANCE_MIN
    if day_n >= min_day:
        ready, reason = True, "ok"
    elif dawn >= (EXPECTED_DAWN_BARS - _EDGE_TOLERANCE_MIN) and day_n == 0:
        # Monday / post-holiday: dawn-only so far before 08:45
        ready, reason = True, "dawn_only_ok"
    else:
        ready = False
        reason = f"day_short:{day_n}<{min_day}"

    return TodayKbarStatus(
        date=day,
        file_exists=True,
        total_bars=total,
        dawn_bars=dawn,
        day_bars=day_n,
        is_saturday=False,
        is_trading_day=True,
        ready=ready,
        reason=reason,
    )


def filter_bars_by_scope(bars: Sequence[BarRecord], scope: SessionScope) -> list[BarRecord]:
    if scope == "day":
        return [b for b in bars if _in_day_session(b)]
    if scope == "night":
        return [b for b in bars if _in_night_session(b)]
    return [b for b in bars if _in_day_session(b) or _in_night_session(b)]


def _next_trading_day(
    day: datetime.date,
    trading_days: Sequence[datetime.date],
) -> datetime.date | None:
    """Next observed session close day after *day*, or None (do not invent weekdays).

    Disk SSOT: Friday night stays unlabeled until a later day-session is observed
    (e.g. Tue after typhoon Mon), rather than guessing Monday via calendar math.
    """
    for d in trading_days:
        if d > day:
            return d
    return None


def _first_trading_day_on_or_after(
    day: datetime.date,
    trading_days: Sequence[datetime.date],
) -> datetime.date | None:
    for d in trading_days:
        if d >= day:
            return d
    return None


def _evening_start_for_close_day(close_day: datetime.date) -> datetime.date:
    """Calendar date of 15:00 that opens the session closing on *close_day* 13:45."""
    prev = close_day - datetime.timedelta(days=1)
    while prev.weekday() >= 5:
        prev -= datetime.timedelta(days=1)
    return prev


def session_close_day(
    evening_start: datetime.date,
    trading_days: Sequence[datetime.date],
) -> datetime.date | None:
    """Trading day whose 13:45 closes the session opened at *evening_start* 15:00.

    Returns None when no later close day is present in ``trading_days`` (defer label).
    """
    return _next_trading_day(evening_start, trading_days)


def session_label_date(
    ts: datetime.datetime,
    trading_days: Sequence[datetime.date],
) -> datetime.date | None:
    """Session-day key: 15:00 → next day-session 13:45, labeled by the 13:45 close day.

    Night/dawn bars without a later observed close day stay unlabeled (None).
    """
    t = ts.time()
    d = ts.date()
    if DAY_ANCHOR <= t <= DAY_END or t == DAY_SETTLEMENT_TAIL:
        return d
    if t >= NIGHT_ANCHOR:
        return session_close_day(d, trading_days)
    if t <= DAWN_END or t == DAWN_SETTLEMENT_TAIL:
        return _first_trading_day_on_or_after(d, trading_days)
    return None


def _prior_bundle_file_day(
    day: datetime.date,
    trading_days: Sequence[datetime.date],
) -> datetime.date:
    """Evening-open file date that may hold *day* dawn/day bars (bundle convention).

    Prefer last observed close day before *day*. If the sparse disk ``trading_days``
    list has no prior entry yet (live rollover), fall back to previous weekday so
    bundle paths still resolve.
    """
    prior = [x for x in trading_days if x < day]
    if prior:
        return prior[-1]
    prev = day - datetime.timedelta(days=1)
    while prev.weekday() >= 5:
        prev -= datetime.timedelta(days=1)
    return prev


def kbar_file_date(
    bar: BarRecord,
    trading_days: Sequence[datetime.date],
) -> datetime.date:
    """Map a 1m bar to the on-disk kbar CSV file date (backfill bundle convention)."""
    t = bar.ts.time()
    d = bar.ts.date()

    if t >= NIGHT_ANCHOR:
        return d

    if t <= DAWN_END or t == DAWN_SETTLEMENT_TAIL:
        return _prior_bundle_file_day(d, trading_days)

    if DAY_ANCHOR <= t <= DAY_END or t == DAY_SETTLEMENT_TAIL:
        return _prior_bundle_file_day(d, trading_days)

    return d


def kbar_file_dates_for_calendar_day(
    day: datetime.date,
    trading_days: Sequence[datetime.date],
) -> set[datetime.date]:
    """On-disk file keys that may hold bars with ``ts.date() == day``."""
    return {
        kbar_file_date(
            KBarRecord(_combine(day, NIGHT_ANCHOR), 0.0, 0.0, 0.0, 0.0, 0),
            trading_days,
        ),
        kbar_file_date(
            KBarRecord(_combine(day, datetime.time(3, 0)), 0.0, 0.0, 0.0, 0.0, 0),
            trading_days,
        ),
        kbar_file_date(
            KBarRecord(_combine(day, datetime.time(10, 0)), 0.0, 0.0, 0.0, 0.0, 0),
            trading_days,
        ),
    }


def _any_kbar_file_exists(
    code: str,
    cache_dir: Path,
    dates: Iterable[datetime.date],
) -> bool:
    return any(resolve_kbar_path(cache_dir, code, d) is not None for d in dates)


def filter_bars_for_calendar_day(
    bars: Sequence[BarRecord],
    day: datetime.date,
    *,
    as_of: datetime.datetime | None = None,
) -> list[BarRecord]:
    """Bars whose ``ts.date()`` equals *day* (optional *as_of* ceiling)."""
    scoped = [b for b in bars if b.ts.date() == day]
    if as_of is not None:
        scoped = [b for b in scoped if b.ts <= as_of]
    return scoped


def disk_exists_for_calendar_day(
    code: str,
    day: datetime.date,
    *,
    cache_dir: Path,
    trading_days: Sequence[datetime.date],
) -> bool:
    """True when any bundle candidate file exists for calendar *day*."""
    return _any_kbar_file_exists(
        code,
        cache_dir,
        kbar_file_dates_for_calendar_day(day, trading_days),
    )


def load_disk_bars_for_calendar_day(
    code: str,
    day: datetime.date,
    *,
    cache_dir: Path,
    trading_days: Sequence[datetime.date],
    as_of: datetime.datetime | None = None,
) -> tuple[list[BarRecord], bool]:
    """Load bundle candidate files; return bars with ``ts.date()==day`` and disk_found."""
    from storage.kbar_loader import dedupe_kbars, load_kbars_csv

    merged: list[BarRecord] = []
    disk_found = False
    for file_day in sorted(kbar_file_dates_for_calendar_day(day, trading_days)):
        path = resolve_kbar_path(cache_dir, code, file_day)
        if path is None:
            continue
        disk_found = True
        loaded = load_kbars_csv(path)
        merged.extend(filter_bars_for_calendar_day(loaded, day, as_of=as_of))
    return dedupe_kbars(merged), disk_found


def assess_calendar_day_readiness(
    day: datetime.date,
    *,
    trading_days: Sequence[datetime.date],
    as_of: datetime.datetime | None = None,
    memory_bars: Sequence[BarRecord] | None = None,
    code: str | None = None,
    cache_dir: Path | None = None,
    file_exists: bool | None = None,
) -> TodayKbarStatus:
    """Canonical calendar-day readiness (bundle-aware disk + optional memory)."""
    scoped_memory = filter_bars_for_calendar_day(memory_bars or [], day, as_of=as_of)
    disk_bars: list[BarRecord] = []
    disk_found = False
    if code is not None and cache_dir is not None:
        disk_bars, disk_found = load_disk_bars_for_calendar_day(
            code,
            day,
            cache_dir=cache_dir,
            trading_days=trading_days,
            as_of=as_of,
        )

    by_ts: dict[datetime.datetime, BarRecord] = {b.ts: b for b in disk_bars}
    for bar in scoped_memory:
        by_ts[bar.ts] = bar
    today_bars = sorted(by_ts.values(), key=lambda b: b.ts)

    if file_exists is not None:
        exists = file_exists
    else:
        exists = (
            disk_found
            or (
                code is not None
                and cache_dir is not None
                and disk_exists_for_calendar_day(
                    code, day, cache_dir=cache_dir, trading_days=trading_days
                )
            )
            or bool(scoped_memory)
        )

    total, dawn, day_n = count_session_bars(today_bars)
    return _assess_today_status(
        day,
        trading_days=trading_days,
        file_exists=exists,
        total_bars=total,
        dawn_bars=dawn,
        day_bars=day_n,
    )


def assess_today_from_bars(
    bars: Sequence[BarRecord],
    day: datetime.date,
    *,
    trading_days: Sequence[datetime.date],
    as_of: datetime.datetime | None = None,
    file_exists: bool | None = None,
) -> TodayKbarStatus:
    """Assess calendar-day readiness from an in-memory 1m bar set."""
    return assess_calendar_day_readiness(
        day,
        trading_days=trading_days,
        as_of=as_of,
        memory_bars=bars,
        file_exists=file_exists,
    )


def assess_today_kbar_file(
    code: str,
    day: datetime.date,
    *,
    cache_dir: Path,
    trading_days: Sequence[datetime.date],
    as_of: datetime.datetime | None = None,
) -> TodayKbarStatus:
    """Assess calendar-day readiness from on-disk bundle kbar files."""
    return assess_calendar_day_readiness(
        day,
        trading_days=trading_days,
        as_of=as_of,
        code=code,
        cache_dir=cache_dir,
    )


def _resolve_missing_trading_days(
    code: str,
    window: Sequence[datetime.date],
    *,
    cache_dir: Path,
    trading_days: Sequence[datetime.date],
) -> list[datetime.date]:
    missing: list[datetime.date] = []
    for day in window:
        candidates = kbar_file_dates_for_calendar_day(day, trading_days)
        if not _any_kbar_file_exists(code, cache_dir, candidates):
            missing.append(day)
    return missing


def _aggregate(bars: Sequence[BarRecord], close_ts: datetime.datetime) -> BarRecord | None:
    if not bars:
        return None
    ordered = sorted(bars, key=lambda b: b.ts)
    return BarRecord(
        ts=close_ts,
        Open=float(ordered[0].Open),
        High=max(float(b.High) for b in ordered),
        Low=min(float(b.Low) for b in ordered),
        Close=float(ordered[-1].Close),
        Volume=sum(int(b.Volume) for b in ordered),
    )


def yuanta_resample_instance(
    bars_1m: Sequence[BarRecord],
    anchor_dt: datetime.datetime,
    end_dt: datetime.datetime,
    tf_min: int,
    as_of: datetime.datetime,
) -> tuple[list[BarRecord], BarRecord | None]:
    """Resample one session instance; bar ``ts`` = close time (Yuanta convention)."""
    if tf_min <= 0:
        return [], None
    prev_close = anchor_dt
    closed: list[BarRecord] = []
    i = 0
    while True:
        close_dt = min(anchor_dt + datetime.timedelta(minutes=tf_min * (i + 1)), end_dt)
        if close_dt <= prev_close:
            break
        chunk = [
            b
            for b in bars_1m
            if prev_close < _bar_minute_end(b) <= close_dt and b.ts <= as_of
        ]
        bar = _aggregate(chunk, close_dt)
        if bar is not None:
            if close_dt <= as_of:
                closed.append(bar)
            else:
                return closed, bar
        if close_dt >= end_dt:
            break
        prev_close = close_dt
        i += 1
    return closed, None


def _day_segment_bounds(day: datetime.date) -> tuple[datetime.datetime, datetime.datetime]:
    return _combine(day, DAY_ANCHOR), _combine(day, DAY_END)


def _night_segment_bounds(day: datetime.date) -> tuple[datetime.datetime, datetime.datetime]:
    end_day = day + datetime.timedelta(days=1)
    return _combine(day, NIGHT_ANCHOR), _combine(end_day, DAWN_END)


def yuanta_resample(
    bars_1m: Sequence[BarRecord],
    tf_min: int,
    scope: SessionScope,
    as_of: datetime.datetime,
) -> tuple[list[BarRecord], BarRecord | None]:
    """Resample 1m bars across calendar days using Yuanta session anchors."""
    if not bars_1m:
        return [], None

    dates = sorted({b.ts.date() for b in bars_1m})
    closed_all: list[BarRecord] = []
    current: BarRecord | None = None

    for day in dates:
        day_bars = [b for b in bars_1m if b.ts.date() == day]
        if scope in ("day", "both"):
            anchor, end = _day_segment_bounds(day)
            seg_closed, seg_current = yuanta_resample_instance(
                day_bars, anchor, end, tf_min, as_of
            )
            closed_all.extend(seg_closed)
            if seg_current is not None:
                current = seg_current
        if scope in ("night", "both"):
            anchor, end = _night_segment_bounds(day)
            seg_bars = [
                b
                for b in bars_1m
                if anchor < _bar_minute_end(b) <= end and b.ts <= as_of
            ]
            seg_closed, seg_current = yuanta_resample_instance(
                seg_bars, anchor, end, tf_min, as_of
            )
            closed_all.extend(seg_closed)
            if seg_current is not None:
                current = seg_current

    deduped = {bar.ts: bar for bar in closed_all}
    return sorted(deduped.values(), key=lambda b: b.ts), current


def build_session_daily_bars(
    bars_1m: Sequence[BarRecord],
    trading_days: Sequence[datetime.date],
    as_of: datetime.datetime,
) -> list[BarRecord]:
    """One daily bar per session (15:00 → next day-session 13:45), labeled by close day."""
    buckets: dict[datetime.date, list[BarRecord]] = {}
    for bar in bars_1m:
        if bar.ts > as_of:
            continue
        label = session_label_date(bar.ts, trading_days)
        if label is None:
            continue
        buckets.setdefault(label, []).append(bar)

    daily: list[BarRecord] = []
    for label in sorted(buckets):
        close_ts = _combine(label, DAY_END)
        if close_ts > as_of:
            continue
        bar = _aggregate(buckets[label], close_ts)
        if bar is not None:
            daily.append(bar)
    return daily


def sma(values: Sequence[float], period: int) -> float | None:
    if period <= 0 or len(values) < period:
        return None
    return sum(values[-period:]) / period


def daily_mas(closes: Sequence[float]) -> dict[str, float | None]:
    return {f"ma{p}": sma(closes, p) for p in DAILY_MA_PERIODS}


def _bars_per_trading_day(spec: TfSpec) -> int:
    """Closed bars expected per trading day for lookback → day-count conversion.

    Day session ≈ 08:45–13:45 (301 minutes). Night ≈ 15:00–05:00 (841 minutes).
    Using a flat ``6`` for ``\"both\"`` massively under-counts bars/day and over-loads
    history when lookback is large.
    """
    minutes = max(spec.minutes, 1)
    day_n = max(1, (5 * 60 + 1) // minutes)
    night_n = max(1, (14 * 60 + 1) // minutes)
    if spec.session == "day":
        return day_n
    if spec.session == "night":
        return night_n
    return day_n + night_n


def _tf_rebuild_trading_days_count(tf_table: dict[str, TfSpec]) -> int:
    """Trading days of 1m history needed for incremental TF resample."""
    max_days = 7
    for spec in tf_table.values():
        if spec.minutes <= 0:
            continue
        per_day = _bars_per_trading_day(spec)
        sessions_needed = (spec.lookback + per_day - 1) // per_day
        max_days = max(max_days, sessions_needed + _TRADING_DAYS_BUFFER)
    return max_days


def _tf_tail_trading_window(
    trading_days: Sequence[datetime.date],
    as_of_date: datetime.date,
    n_days: int,
) -> list[datetime.date]:
    eligible = [d for d in trading_days if d <= as_of_date]
    if not eligible:
        return []
    return eligible[-n_days:] if len(eligible) >= n_days else list(eligible)


def list_kbar_file_dates(
    code: str,
    cache_dir: Path,
    start: datetime.date,
    end: datetime.date,
) -> list[datetime.date]:
    """Dates with an on-disk kbar file in ``[start, end]`` (disk SSOT for load window)."""
    if end < start:
        return []
    return [
        d
        for d in date_range(start, end)
        if resolve_kbar_path(cache_dir, code, d) is not None
    ]


def observed_day_session_dates(
    bars_1m: Sequence[BarRecord],
    as_of: datetime.datetime,
) -> list[datetime.date]:
    """Session close days evidenced by day-session 1m bars (disk SSOT).

    A date with day-session bars is a trading day; dates without bars are not.
    """
    days: set[datetime.date] = set()
    for bar in bars_1m:
        if bar.ts > as_of:
            continue
        if _in_day_session(bar):
            days.add(bar.ts.date())
    return sorted(days)


# Prior evening-open file lag for day-tape discovery (weekend-safe). Not holiday logic.
BUNDLE_DISCOVER_PAD_DAYS = 7


def discover_session_close_days(
    code: str,
    cache_dir: Path,
    *,
    from_date: datetime.date | None = None,
    to_date: datetime.date | None = None,
) -> list[datetime.date]:
    """Session close days with day-session 1m in ``[from_date, to_date]`` (disk SSOT).

    On-disk file keys are evening-open dates and may hold the **next** calendar
    day's day tape. Load includes file keys from
    ``from_date - BUNDLE_DISCOVER_PAD_DAYS`` so a clamped ``--from-date`` still
    sees that prior evening file; returned days are filtered to the range only.

    When ``to_date`` is None, ``as_of`` is the max loaded bar ts (not the last
    file key) so day tape with ``ts.date`` after the key is still counted.
    """
    import re

    pat = re.compile(rf"^{re.escape(code)}_kbars_(\d{{4}}-\d{{2}}-\d{{2}})\.csv$")
    file_days = sorted(
        {
            datetime.date.fromisoformat(m.group(1))
            for path in cache_dir.glob(f"{code}_kbars_*.csv")
            if (m := pat.match(path.name)) is not None
        }
    )
    if not file_days:
        return []

    lo_bound = (
        file_days[0]
        if from_date is None
        else from_date - datetime.timedelta(days=BUNDLE_DISCOVER_PAD_DAYS)
    )
    # File keys (evening-open) in pad..to_date; prior key alone holds next day's day tape.
    hi_key = file_days[-1] if to_date is None else to_date
    load_keys = [d for d in file_days if lo_bound <= d <= hi_key]
    if not load_keys:
        return []
    bars = iter_kbars_in_range(code, load_keys[0], load_keys[-1], cache_dir=cache_dir)
    # File key ≠ bar ts.date (bundle). Bound by to_date when set; else use loaded bars.
    if to_date is not None:
        as_of = _combine(to_date, DAY_END)
    elif bars:
        as_of = max(b.ts for b in bars)
    else:
        as_of = _combine(file_days[-1], DAY_END)
    days = observed_day_session_dates(bars, as_of)
    if from_date is not None:
        days = [d for d in days if d >= from_date]
    if to_date is not None:
        days = [d for d in days if d <= to_date]
    return days


def _index_bars_for_daily(
    bars: Iterable[BarRecord],
    trading_days: Sequence[datetime.date],
) -> dict[datetime.date, dict[datetime.datetime, BarRecord]]:
    index: dict[datetime.date, dict[datetime.datetime, BarRecord]] = {}
    for bar in bars:
        label = session_label_date(bar.ts, trading_days)
        if label is None:
            continue
        index.setdefault(label, {})[bar.ts] = bar
    return index


def _daily_label_needs_refresh(
    bar: BarRecord,
    trading_days: Sequence[datetime.date],
    as_of: datetime.datetime,
) -> bool:
    label = session_label_date(bar.ts, trading_days)
    if label is None:
        return False
    return _combine(label, DAY_END) <= as_of


def _estimate_trading_days_needed(
    tf_table: dict[str, TfSpec],
    *,
    daily_lookback: int = DAILY_LOOKBACK,
) -> int:
    max_days = _MIN_TRADING_DAYS
    for spec in tf_table.values():
        if spec.minutes <= 0:
            continue
        per_day = _bars_per_trading_day(spec)
        sessions_needed = (spec.lookback + per_day - 1) // per_day
        max_days = max(max_days, sessions_needed + _TRADING_DAYS_BUFFER)
    return max(max_days, daily_lookback + _TRADING_DAYS_BUFFER)


def _resolve_lookback_window(
    as_of: datetime.datetime,
    n_days: int,
    *,
    calendar_dir: Path,
) -> tuple[list[datetime.date], list[datetime.date]]:
    """Calendar-based window (empty-disk / readiness fallback only)."""
    end = as_of.date()
    span = max(n_days * 2, 90)
    start = end - datetime.timedelta(days=span)
    trading_days, _ = resolve_trading_days_in_range_with_fallback(
        start,
        end,
        calendar_dir=calendar_dir,
    )
    eligible = [d for d in trading_days if d <= end]
    window = eligible[-n_days:] if len(eligible) >= n_days else eligible
    return list(trading_days), window


def _resolve_disk_load_start(
    code: str,
    as_of: datetime.datetime,
    n_days: int,
    *,
    cache_dir: Path,
) -> datetime.date | None:
    """Earliest kbar file date covering the last *n_days* files on disk (≤ as_of).

    Expands the calendar scan span when too few files are found (sparse archive /
    long outages). Logs a warning if still short of *n_days* after the cap.
    """
    end = as_of.date()
    scan_span = max(n_days * 3, 120)
    scan_cap = max(n_days * 10, 400)
    file_dates: list[datetime.date] = []
    start = end
    while True:
        start = end - datetime.timedelta(days=scan_span)
        file_dates = list_kbar_file_dates(code, cache_dir, start, end)
        if len(file_dates) >= n_days or scan_span >= scan_cap:
            break
        scan_span = min(scan_cap, max(scan_span * 2, scan_span + n_days * 2))
    if not file_dates:
        return None
    if len(file_dates) < n_days:
        logger.warning(
            "SessionBarCache disk window short: requested_n=%s found_n=%s "
            "scan_start=%s as_of=%s code=%s",
            n_days,
            len(file_dates),
            start.isoformat(),
            as_of.isoformat(sep=" ", timespec="minutes"),
            code,
        )
    selected = file_dates[-n_days:] if len(file_dates) >= n_days else file_dates
    return selected[0]


def _merge_trading_days_for_as_of(
    observed: list[datetime.date],
    as_of: datetime.datetime,
    *,
    calendar_dir: Path,
) -> list[datetime.date]:
    """Disk-observed close days + soft calendar tip only **before day open**.

    At/after ``DAY_ANCHOR`` with no day-session bars, pin-yi must not invent a
    close day (typhoon / missing tape at EOD stays off ``trading_days``).
    """
    days = set(observed)
    as_of_day = as_of.date()
    if as_of_day not in days and as_of.time() < DAY_ANCHOR:
        # Live pre-open only: readiness before first day-session bar.
        cal, _ = resolve_trading_days_in_range_with_fallback(
            as_of_day - datetime.timedelta(days=7),
            as_of_day,
            calendar_dir=calendar_dir,
        )
        if as_of_day in cal:
            days.add(as_of_day)
    return sorted(days)


class SessionBarCache:
    """In-memory Yuanta-style multi-TF bars from ``tick_cache`` 1m files."""

    def __init__(
        self,
        code: str,
        cache_dir: Path,
        as_of: datetime.datetime,
        *,
        tf_table: dict[str, TfSpec] | None = None,
        trading_days: Sequence[datetime.date],
        bars_1m: list[BarRecord],
        missing_trading_days: list[datetime.date],
        today_status: TodayKbarStatus,
        calendar_dir: Path = DEFAULT_TRADE_DAYS_DIR,
        daily_lookback: int = DAILY_LOOKBACK,
    ) -> None:
        self.code = code
        self.cache_dir = cache_dir
        self._calendar_dir = calendar_dir
        self.as_of = as_of
        self.tf_table = dict(tf_table or DEFAULT_TF_TABLE)
        self._daily_lookback = daily_lookback
        self.trading_days = list(trading_days)
        self.missing_trading_days = list(missing_trading_days)
        self.today_status = today_status
        self._lock = threading.RLock()
        self._bars_1m_map: dict[datetime.datetime, BarRecord] = {
            b.ts: b for b in bars_1m
        }
        self._daily_source = _index_bars_for_daily(bars_1m, trading_days)
        self._today_count_day: datetime.date | None = None
        self._today_total = 0
        self._today_dawn = 0
        self._today_day = 0
        self._disk_today_exists = False
        self._series: dict[str, _TfSeries] = {}
        self._daily_closed: list[BarRecord] = []
        self._build()

    @classmethod
    def load(
        cls,
        code: str,
        as_of: datetime.datetime,
        *,
        cache_dir: Path = DEFAULT_TICK_CACHE_DIR,
        tf_table: dict[str, TfSpec] | None = None,
        calendar_dir: Path = DEFAULT_TRADE_DAYS_DIR,
        daily_lookback: int = DAILY_LOOKBACK,
    ) -> SessionBarCache:
        """Load 1m kbars from disk and build multi-TF series.

        **Disk SSOT for history:** load window is the last *n* on-disk kbar files
        (not calendar trading days). Session close days (``trading_days``) are
        dates with day-session bars present. No file ⇒ not a trading day; calendar
        is only a soft tip for live pre-open readiness / empty-cache fallback.
        """
        table = tf_table or DEFAULT_TF_TABLE
        n_days = _estimate_trading_days_needed(table, daily_lookback=daily_lookback)
        end = as_of.date()
        disk_start = _resolve_disk_load_start(
            code, as_of, n_days, cache_dir=cache_dir
        )

        if disk_start is not None:
            bars_1m = iter_kbars_in_range(code, disk_start, end, cache_dir=cache_dir)
            bars_1m = [b for b in bars_1m if b.ts <= as_of]
            observed = observed_day_session_dates(bars_1m, as_of)
            trading_days = _merge_trading_days_for_as_of(
                observed, as_of, calendar_dir=calendar_dir
            )
            # Disk SSOT: absence of a file means non-trading, not "missing".
            missing: list[datetime.date] = []
        else:
            # Empty cache: calendar window for structure / readiness only.
            trading_days, window = _resolve_lookback_window(
                as_of, n_days, calendar_dir=calendar_dir
            )
            if not window:
                today_status = assess_calendar_day_readiness(
                    as_of.date(),
                    trading_days=trading_days,
                    as_of=as_of,
                    memory_bars=[],
                    code=code,
                    cache_dir=cache_dir,
                )
                return cls(
                    code,
                    cache_dir,
                    as_of,
                    tf_table=table,
                    trading_days=trading_days,
                    bars_1m=[],
                    missing_trading_days=[],
                    today_status=today_status,
                    calendar_dir=calendar_dir,
                    daily_lookback=daily_lookback,
                )
            bars_1m = iter_kbars_in_range(
                code, window[0], window[-1], cache_dir=cache_dir
            )
            bars_1m = [b for b in bars_1m if b.ts <= as_of]
            observed = observed_day_session_dates(bars_1m, as_of)
            if observed:
                trading_days = _merge_trading_days_for_as_of(
                    observed, as_of, calendar_dir=calendar_dir
                )
            missing = _resolve_missing_trading_days(
                code,
                window,
                cache_dir=cache_dir,
                trading_days=trading_days,
            )

        today_status = assess_calendar_day_readiness(
            as_of.date(),
            trading_days=trading_days,
            as_of=as_of,
            memory_bars=bars_1m,
            code=code,
            cache_dir=cache_dir,
        )

        return cls(
            code,
            cache_dir,
            as_of,
            tf_table=table,
            trading_days=trading_days,
            bars_1m=bars_1m,
            missing_trading_days=missing,
            today_status=today_status,
            calendar_dir=calendar_dir,
            daily_lookback=daily_lookback,
        )

    def _bars_1m_list(self) -> list[BarRecord]:
        return sorted(self._bars_1m_map.values(), key=lambda b: b.ts)

    def bars_1m_as_of(self, as_of: datetime.datetime) -> list[BarRecord]:
        with self._lock:
            return sorted(
                (b for b in self._bars_1m_map.values() if b.ts <= as_of),
                key=lambda b: b.ts,
            )

    def _bars_1m_tail(self) -> list[BarRecord]:
        n_days = _tf_rebuild_trading_days_count(self.tf_table)
        window = _tf_tail_trading_window(
            self.trading_days,
            self.as_of.date(),
            n_days,
        )
        if not window:
            return self._bars_1m_list()
        carry_day = window[0] - datetime.timedelta(days=1)
        cutoff = datetime.datetime.combine(carry_day, NIGHT_ANCHOR)
        return sorted(
            (b for b in self._bars_1m_map.values() if b.ts >= cutoff),
            key=lambda b: b.ts,
        )

    def _build(self) -> None:
        bars_1m = self._bars_1m_list()
        for name, spec in self.tf_table.items():
            scoped = filter_bars_by_scope(bars_1m, spec.session)
            closed, current = yuanta_resample(
                scoped, spec.minutes, spec.session, self.as_of
            )
            if spec.lookback > 0:
                closed = closed[-spec.lookback :]
            self._series[name] = _TfSeries(closed=closed, current=current)

        daily_bars = build_session_daily_bars(
            filter_bars_by_scope(bars_1m, "both"),
            self.trading_days,
            self.as_of,
        )
        self._daily_closed = daily_bars[-self._daily_lookback :]

    def _rebuild_tf_series(self) -> None:
        """Resample recent 1m tail and merge with older closed bars (live hot path)."""
        tail = self._bars_1m_tail()
        for name, spec in self.tf_table.items():
            existing = self._series.get(name)
            scoped = filter_bars_by_scope(tail, spec.session)
            new_closed, current = yuanta_resample(
                scoped, spec.minutes, spec.session, self.as_of
            )
            prefix: list[BarRecord] = []
            if existing and existing.closed:
                if new_closed:
                    split_ts = new_closed[0].ts
                    prefix = [b for b in existing.closed if b.ts < split_ts]
                else:
                    prefix = list(existing.closed)
            merged: dict[datetime.datetime, BarRecord] = {b.ts: b for b in prefix}
            for bar in new_closed:
                merged[bar.ts] = bar
            closed = sorted(merged.values(), key=lambda b: b.ts)
            if spec.lookback > 0:
                closed = closed[-spec.lookback :]
            self._series[name] = _TfSeries(closed=closed, current=current)

    def _rebuild_daily_closed(self) -> None:
        daily: list[BarRecord] = []
        for label in sorted(self._daily_source):
            close_ts = _combine(label, DAY_END)
            if close_ts > self.as_of:
                continue
            bar = _aggregate(self._daily_source[label].values(), close_ts)
            if bar is not None:
                daily.append(bar)
        self._daily_closed = daily[-self._daily_lookback :]

    def _note_observed_trading_day(self, day: datetime.date) -> None:
        """Record a session close day evidenced by a day-session bar (disk SSOT)."""
        if day in self.trading_days:
            return
        self.trading_days.append(day)
        self.trading_days.sort()

    def _extend_trading_days_through(self, day: datetime.date) -> None:
        """Soft calendar tip for **current as_of day only**, before day open.

        Matches ``_merge_trading_days_for_as_of`` (R1). No pin-yi bulk insert of
        historical close days — those require ``_note_observed_trading_day``.
        """
        if day in self.trading_days:
            return
        if day != self.as_of.date() or self.as_of.time() >= DAY_ANCHOR:
            return
        cal, _ = resolve_trading_days_in_range_with_fallback(
            day - datetime.timedelta(days=7),
            day,
            calendar_dir=self._calendar_dir,
        )
        if day in cal:
            self.trading_days.append(day)
            self.trading_days.sort()

    def _ensure_today_counts(self, day: datetime.date) -> None:
        if self._today_count_day == day:
            return
        self._extend_trading_days_through(day)
        self._today_count_day = day
        baseline = assess_calendar_day_readiness(
            day,
            trading_days=self.trading_days,
            as_of=self.as_of,
            memory_bars=self._bars_1m_map.values(),
            code=self.code,
            cache_dir=self.cache_dir,
        )
        self._disk_today_exists = baseline.file_exists
        self._today_total = baseline.total_bars
        self._today_dawn = baseline.dawn_bars
        self._today_day = baseline.day_bars

    def _apply_today_count_delta(
        self,
        bar: BarRecord,
        day: datetime.date,
        delta: int,
    ) -> None:
        if bar.ts.date() != day or bar.ts > self.as_of:
            return
        self._today_total += delta
        kind = _session_count_kind(bar)
        if kind == "dawn":
            self._today_dawn += delta
        elif kind == "day":
            self._today_day += delta

    def _refresh_today_status(self, day: datetime.date) -> None:
        exists = self._disk_today_exists or self._today_total > 0
        self.today_status = _assess_today_status(
            day,
            trading_days=self.trading_days,
            file_exists=exists,
            total_bars=self._today_total,
            dawn_bars=self._today_dawn,
            day_bars=self._today_day,
        )

    def _index_one_bar(self, bar: BarRecord) -> None:
        label = session_label_date(bar.ts, self.trading_days)
        if label is None:
            return
        self._daily_source.setdefault(label, {})[bar.ts] = bar

    def _unindex_one_bar(self, bar: BarRecord) -> None:
        label = session_label_date(bar.ts, self.trading_days)
        if label is None:
            return
        bucket = self._daily_source.get(label)
        if bucket is not None:
            bucket.pop(bar.ts, None)

    def closed(self, tf: str) -> list[BarRecord]:
        with self._lock:
            series = self._series.get(tf)
            if series is None:
                raise KeyError(f"unknown timeframe: {tf!r}")
            return list(series.closed)

    def current(self, tf: str) -> BarRecord | None:
        with self._lock:
            series = self._series.get(tf)
            if series is None:
                raise KeyError(f"unknown timeframe: {tf!r}")
            return series.current

    def daily_closed(self) -> list[BarRecord]:
        with self._lock:
            return list(self._daily_closed)

    def daily_closes(self) -> list[float]:
        with self._lock:
            return [float(b.Close) for b in self._daily_closed]

    def daily_ma(self, period: int) -> float | None:
        with self._lock:
            return sma(self.daily_closes(), period)

    def daily_mas(self) -> dict[str, float | None]:
        with self._lock:
            return daily_mas(self.daily_closes())

    def on_new_1m(self, bar: BarRecord) -> None:
        """Incremental live ingest: O(tail) TF resample; O(1) same-day counters, O(disk) on rollover."""
        with self._lock:
            if bar.ts > self.as_of:
                self.as_of = bar.ts
            day = self.as_of.date()
            prev = self._bars_1m_map.get(bar.ts)
            self._bars_1m_map[bar.ts] = bar
            if prev is not None:
                self._unindex_one_bar(prev)
            if _in_day_session(bar):
                self._note_observed_trading_day(bar.ts.date())
            self._index_one_bar(bar)

            if self._today_count_day != day:
                self._ensure_today_counts(day)
            else:
                if prev is not None:
                    self._apply_today_count_delta(prev, day, -1)
                self._apply_today_count_delta(bar, day, +1)
            self._refresh_today_status(day)

            self._rebuild_tf_series()
            if _daily_label_needs_refresh(bar, self.trading_days, self.as_of):
                self._rebuild_daily_closed()


__all__ = [
    "BarRecord",
    "DAILY_LOOKBACK",
    "DAILY_MA_PERIODS",
    "DEFAULT_TF_TABLE",
    "EXPECTED_DAWN_BARS",
    "EXPECTED_DAY_BARS",
    "SessionBarCache",
    "TfSpec",
    "TodayKbarStatus",
    "assess_calendar_day_readiness",
    "assess_today_from_bars",
    "assess_today_kbar_file",
    "disk_exists_for_calendar_day",
    "filter_bars_for_calendar_day",
    "load_disk_bars_for_calendar_day",
    "build_session_daily_bars",
    "count_session_bars",
    "daily_mas",
    "filter_bars_by_scope",
    "kbar_file_date",
    "kbar_file_dates_for_calendar_day",
    "BUNDLE_DISCOVER_PAD_DAYS",
    "discover_session_close_days",
    "list_kbar_file_dates",
    "observed_day_session_dates",
    "session_close_day",
    "session_label_date",
    "sma",
    "yuanta_resample",
]