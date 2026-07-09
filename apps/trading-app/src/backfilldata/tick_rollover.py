"""Cross-month continuous futures: merge R2 afternoon ticks into R1 day cache."""

from __future__ import annotations

import datetime
import logging
import re
from typing import Any

from storage.tick_loader import (
    DEFAULT_TICK_RANGE_END,
    ReplayTick,
    commit_ticks_cache,
    fetch_ticks_for_date,
    load_merged_tick_cache,
    merge_ticks,
)

logger = logging.getLogger(__name__)

_ROLL_CODE_RE = re.compile(r"^(.+R)(\d+)$")

# TMFR1 day session ends ~13:30 on settlement; TMFR2 carries 13:30–13:45.
ROLLOVER_AFTERNOON_START = datetime.time(13, 30, 0)
EXPECTED_LAST_TICK_MINUTE = datetime.time(13, 44)
# R1 stops ~13:29–13:30 on settlement; earlier cutoffs are partial-cache gaps, not rollover.
ROLLOVER_TAIL_MINUTE_LO = datetime.time(13, 28)
ROLLOVER_TAIL_MINUTE_HI = datetime.time(13, 30)
SESSION_OPEN = datetime.time(8, 45)
# Full R1 day session is ~285 distinct minutes (08:45–13:29).
SETTLEMENT_R1_MIN_MINUTES = 280
SETTLEMENT_TAIL_CONTIGUOUS_MINUTES = 5


def next_continuous_code(code: str) -> str | None:
    """TMFR1 → TMFR2; returns None when pattern does not apply."""
    m = _ROLL_CODE_RE.match(code)
    if not m:
        return None
    return f"{m.group(1)}{int(m.group(2)) + 1}"


def _minute_floor(ts: datetime.datetime) -> datetime.datetime:
    return ts.replace(second=0, microsecond=0)


def _has_contiguous_tail(
    minutes: set[datetime.datetime], last: datetime.datetime, n: int
) -> bool:
    for i in range(n):
        if last - datetime.timedelta(minutes=i) not in minutes:
            return False
    return True


def _day_session_minutes(ticks: list[ReplayTick], date: datetime.date) -> set[datetime.datetime]:
    """08:45–13:45 calendar minutes on *date* (excludes night session)."""
    minutes: set[datetime.datetime] = set()
    for t in ticks:
        if t.datetime.date() != date:
            continue
        tt = t.datetime.time()
        if SESSION_OPEN <= tt <= DEFAULT_TICK_RANGE_END:
            minutes.add(_minute_floor(t.datetime))
    return minutes


def _last_day_session_minute(
    ticks: list[ReplayTick], date: datetime.date
) -> datetime.datetime | None:
    minutes = _day_session_minutes(ticks, date)
    return max(minutes) if minutes else None


def _day_session_complete_through(
    ticks: list[ReplayTick], date: datetime.date, through: datetime.time
) -> bool:
    """True when every day-session minute through *through* has at least one tick."""
    minutes = _day_session_minutes(ticks, date)
    if not minutes:
        return False
    last = max(minutes)
    if last < datetime.datetime.combine(date, through):
        return False
    afternoon_start = datetime.datetime.combine(date, ROLLOVER_AFTERNOON_START)
    afternoon_end = datetime.datetime.combine(date, through)
    cur = afternoon_start
    while cur <= afternoon_end:
        if cur not in minutes:
            return False
        cur += datetime.timedelta(minutes=1)
    return True


def _third_wednesday(year: int, month: int) -> datetime.date:
    d = datetime.date(year, month, 1)
    while d.weekday() != 2:
        d += datetime.timedelta(days=1)
    return d + datetime.timedelta(weeks=2)


def is_near_month_settlement_day(date: datetime.date) -> bool:
    """TAIFEX near-month settlement is typically the 3rd Wednesday."""
    return date == _third_wednesday(date.year, date.month)


def ticks_need_rollover_afternoon(
    ticks: list[ReplayTick], date: datetime.date
) -> bool:
    """True when R1 day session ends at settlement (~13:29) and needs R2 afternoon."""
    if not ticks:
        return False
    if not is_near_month_settlement_day(date):
        return False
    if _day_session_complete_through(ticks, date, EXPECTED_LAST_TICK_MINUTE):
        return False
    minutes = _day_session_minutes(ticks, date)
    if len(minutes) < SETTLEMENT_R1_MIN_MINUTES:
        return False
    first_minute = min(minutes)
    if first_minute.time() != SESSION_OPEN:
        return False
    last_minute = _last_day_session_minute(ticks, date)
    if last_minute is None:
        return False
    expected_last = datetime.datetime.combine(date, EXPECTED_LAST_TICK_MINUTE)
    if last_minute > expected_last:
        return False
    last_t = last_minute.time()
    if ROLLOVER_AFTERNOON_START <= last_t <= EXPECTED_LAST_TICK_MINUTE:
        return True
    # Classic R1 settlement stop ~13:28–13:30.
    if last_t < ROLLOVER_TAIL_MINUTE_LO or last_t > ROLLOVER_TAIL_MINUTE_HI:
        return False
    if not _has_contiguous_tail(
        minutes, last_minute, SETTLEMENT_TAIL_CONTIGUOUS_MINUTES
    ):
        return False
    missing_tail = int((expected_last - last_minute).total_seconds() // 60)
    # Settlement leaves only the R2 afternoon window (13:30–13:44).
    if missing_tail < 14 or missing_tail > 16:
        return False
    return True


def tick_tail_missing_minutes(
    ticks: list[ReplayTick], date: datetime.date
) -> int:
    if not ticks:
        return EXPECTED_DAY_TICK_MINUTES()
    expected_last = datetime.datetime.combine(date, EXPECTED_LAST_TICK_MINUTE)
    last = _last_day_session_minute(ticks, date)
    if last is None or last >= expected_last:
        return 0
    return int((expected_last - last).total_seconds() // 60)


def EXPECTED_DAY_TICK_MINUTES() -> int:
    start = DEFAULT_TICK_RANGE_START_MINUTES()
    end = EXPECTED_LAST_TICK_MINUTE.hour * 60 + EXPECTED_LAST_TICK_MINUTE.minute
    return end - start + 1


def DEFAULT_TICK_RANGE_START_MINUTES() -> int:
    return 8 * 60 + 45


def merge_rollover_afternoon_ticks(
    api: Any,
    code: str,
    date: datetime.date,
    *,
    cache_dir: Any,
    simulation: bool,
    resolve_contract: Any,
    overwrite: bool = False,
) -> tuple[int, int]:
    """Fetch next continuous contract 13:30–13:45 ticks and merge into *code* cache.

    Returns ``(afternoon_ticks_fetched, merged_tick_count)``.
    """
    next_code = next_continuous_code(code)
    if next_code is None:
        return 0, 0

    existing = load_merged_tick_cache(cache_dir, code, date)
    last = _last_day_session_minute(existing, date)
    partial_afternoon = (
        last is not None
        and ROLLOVER_AFTERNOON_START <= last.time() <= EXPECTED_LAST_TICK_MINUTE
        and not _day_session_complete_through(existing, date, EXPECTED_LAST_TICK_MINUTE)
    )
    if not ticks_need_rollover_afternoon(existing, date) and not overwrite:
        return 0, len(existing)

    contract = resolve_contract(api, next_code)
    afternoon = fetch_ticks_for_date(
        api,
        contract,
        date,
        time_start=ROLLOVER_AFTERNOON_START,
        time_end=DEFAULT_TICK_RANGE_END,
        simulation=simulation,
    )
    if not afternoon:
        logger.warning(
            "%s %s: %s 13:30–13:45 無 tick，無法補跨月尾盤",
            code,
            date.isoformat(),
            next_code,
        )
        return 0, len(existing)

    merged = merge_ticks(
        existing,
        afternoon,
        time_start=ROLLOVER_AFTERNOON_START,
        time_end=DEFAULT_TICK_RANGE_END,
        replace_window=overwrite or partial_afternoon,
    )
    _, n = commit_ticks_cache(cache_dir, code, date, merged)
    logger.info(
        "跨月合併 %s %s | %s afternoon=%d → merged=%d ticks",
        code,
        date.isoformat(),
        next_code,
        len(afternoon),
        n,
    )
    return len(afternoon), n


def merge_rollover_afternoon_batch(
    api: Any,
    code: str,
    dates: list[datetime.date],
    *,
    cache_dir: Any,
    simulation: bool,
    resolve_contract: Any,
    overwrite: bool = False,
) -> list[datetime.date]:
    """Merge rollover afternoon for each date that needs it. Returns repaired dates."""
    repaired: list[datetime.date] = []
    for date in dates:
        n_fetch, _ = merge_rollover_afternoon_ticks(
            api,
            code,
            date,
            cache_dir=cache_dir,
            simulation=simulation,
            resolve_contract=resolve_contract,
            overwrite=overwrite,
        )
        if n_fetch > 0:
            merged = load_merged_tick_cache(cache_dir, code, date)
            if _day_session_complete_through(
                merged, date, EXPECTED_LAST_TICK_MINUTE
            ):
                repaired.append(date)
    return repaired
