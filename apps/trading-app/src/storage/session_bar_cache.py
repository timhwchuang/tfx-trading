"""Yuanta-anchored multi-timeframe bar cache from per-day 1m kbar CSV files."""

from __future__ import annotations

import datetime
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal, Sequence

from backfilldata.taiwan_calendar import (
    DEFAULT_TRADE_DAYS_DIR,
    resolve_trading_days_in_range_with_fallback,
)
from storage.cache_paths import DEFAULT_TICK_CACHE_DIR
from storage.kbar_loader import KBarRecord, iter_kbars_in_range, resolve_kbar_path

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


def _next_trading_day(day: datetime.date, trading_days: Sequence[datetime.date]) -> datetime.date:
    for d in trading_days:
        if d > day:
            return d
    return day + datetime.timedelta(days=1)


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
) -> datetime.date:
    """Trading day whose 13:45 closes the session opened at *evening_start* 15:00."""
    return _next_trading_day(evening_start, trading_days)


def session_label_date(
    ts: datetime.datetime,
    trading_days: Sequence[datetime.date],
) -> datetime.date | None:
    """Session-day key: 15:00 → next day-session 13:45, labeled by the 13:45 close day."""
    t = ts.time()
    d = ts.date()
    if DAY_ANCHOR <= t <= DAY_END or t == DAY_SETTLEMENT_TAIL:
        return d
    if t >= NIGHT_ANCHOR:
        return session_close_day(d, trading_days)
    if t <= DAWN_END or t == DAWN_SETTLEMENT_TAIL:
        close_day = _first_trading_day_on_or_after(d, trading_days)
        if close_day is None:
            return None
        return close_day
    return None


def kbar_file_date(
    bar: BarRecord,
    trading_days: Sequence[datetime.date],
) -> datetime.date:
    """Map a 1m bar to the on-disk kbar CSV file date (backfill bundle convention)."""
    t = bar.ts.time()
    d = bar.ts.date()
    trading = set(trading_days)

    if t >= NIGHT_ANCHOR:
        return d

    if t <= DAWN_END or t == DAWN_SETTLEMENT_TAIL:
        prev = d - datetime.timedelta(days=1)
        if prev.weekday() < 5 and prev in trading:
            return prev
        return d

    if DAY_ANCHOR <= t <= DAY_END or t == DAY_SETTLEMENT_TAIL:
        prev = d - datetime.timedelta(days=1)
        while prev.weekday() >= 5:
            prev -= datetime.timedelta(days=1)
        if prev in trading:
            return prev
        return d

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


def _tf_rebuild_trading_days_count(tf_table: dict[str, TfSpec]) -> int:
    """Trading days of 1m history needed for incremental TF resample."""
    max_days = 7
    for spec in tf_table.values():
        if spec.minutes <= 0:
            continue
        bars_per_session = 6
        if spec.session == "day":
            bars_per_session = max(1, (5 * 60 + 1) // spec.minutes)
        sessions_needed = (spec.lookback + bars_per_session - 1) // bars_per_session
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


def _estimate_trading_days_needed(tf_table: dict[str, TfSpec]) -> int:
    max_days = _MIN_TRADING_DAYS
    for spec in tf_table.values():
        if spec.minutes <= 0:
            continue
        bars_per_session = 6
        if spec.session == "day":
            bars_per_session = max(1, (5 * 60 + 1) // spec.minutes)
        sessions_needed = (spec.lookback + bars_per_session - 1) // bars_per_session
        max_days = max(max_days, sessions_needed + _TRADING_DAYS_BUFFER)
    return max(max_days, DAILY_LOOKBACK + _TRADING_DAYS_BUFFER)


def _resolve_lookback_window(
    as_of: datetime.datetime,
    n_days: int,
    *,
    calendar_dir: Path,
) -> tuple[list[datetime.date], list[datetime.date]]:
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
    ) -> None:
        self.code = code
        self.cache_dir = cache_dir
        self._calendar_dir = calendar_dir
        self.as_of = as_of
        self.tf_table = dict(tf_table or DEFAULT_TF_TABLE)
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
    ) -> SessionBarCache:
        table = tf_table or DEFAULT_TF_TABLE
        n_days = _estimate_trading_days_needed(table)
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
            )

        bars_1m = iter_kbars_in_range(code, window[0], window[-1], cache_dir=cache_dir)
        bars_1m = [b for b in bars_1m if b.ts <= as_of]
        today_status = assess_calendar_day_readiness(
            as_of.date(),
            trading_days=trading_days,
            as_of=as_of,
            memory_bars=bars_1m,
            code=code,
            cache_dir=cache_dir,
        )
        missing = _resolve_missing_trading_days(
            code,
            window,
            cache_dir=cache_dir,
            trading_days=trading_days,
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
        self._daily_closed = daily_bars[-DAILY_LOOKBACK :]

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
        self._daily_closed = daily[-DAILY_LOOKBACK :]

    def _extend_trading_days_through(self, day: datetime.date) -> None:
        if self.trading_days and day <= self.trading_days[-1]:
            return
        start = self.trading_days[-1] if self.trading_days else day
        extra, _ = resolve_trading_days_in_range_with_fallback(
            start,
            day,
            calendar_dir=self._calendar_dir,
        )
        known = set(self.trading_days)
        for d in extra:
            if d not in known:
                self.trading_days.append(d)
                known.add(d)
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
    "session_close_day",
    "session_label_date",
    "sma",
    "yuanta_resample",
]