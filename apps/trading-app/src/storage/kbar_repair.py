"""Fill missing kbar rows from tick-derived 1m OHLCV."""

from __future__ import annotations

import datetime
import logging
import shutil
from pathlib import Path

from storage.cache_audit import aggregate_ticks_to_minute_bars
from storage.cache_paths import DEFAULT_KBAR_CACHE_DIR
from storage.kbar_loader import (
    KBarRecord,
    dedupe_kbars,
    kbars_cache_gz_path,
    kbars_cache_path,
    load_kbars_csv,
    resolve_kbars_cache_path,
    save_kbars_csv,
)
from storage.tick_loader import (
    DEFAULT_TICK_RANGE_END,
    load_merged_tick_cache,
)
from storage.tick_rollover import (
    EXPECTED_LAST_TICK_MINUTE,
    ROLLOVER_AFTERNOON_START,
    _day_session_complete_through,
    is_near_month_settlement_day,
)

logger = logging.getLogger(__name__)


def _kbar_ts_for_tick_minute(minute: datetime.datetime) -> datetime.datetime:
    return minute + datetime.timedelta(minutes=1)


def _resolve_kbar_write_path(
    tick_cache_dir: Path,
    kbar_cache_dir: Path | None,
    code: str,
    date: datetime.date,
    *,
    mirror_to_tick_cache: bool = True,
) -> Path:
    """Resolve plain CSV write target (never ``*.csv.gz``)."""
    roots: list[Path] = []
    if mirror_to_tick_cache:
        roots.append(tick_cache_dir)
    if kbar_cache_dir is not None:
        roots.append(kbar_cache_dir)
    elif not mirror_to_tick_cache:
        roots.append(tick_cache_dir)
    for root in roots:
        plain = kbars_cache_path(root, code, date)
        gz = kbars_cache_gz_path(root, code, date)
        if plain.is_file() or gz.is_file():
            return plain
    if mirror_to_tick_cache:
        return kbars_cache_path(tick_cache_dir, code, date)
    return kbars_cache_path(kbar_cache_dir or tick_cache_dir, code, date)


def _load_existing_kbars(
    tick_cache_dir: Path,
    kbar_cache_dir: Path | None,
    code: str,
    date: datetime.date,
    *,
    mirror_to_tick_cache: bool = True,
) -> tuple[list[KBarRecord], Path]:
    """Load existing bars; primary ``kbar_cache`` wins over tick mirror when both exist."""
    write_path = _resolve_kbar_write_path(
        tick_cache_dir, kbar_cache_dir, code, date, mirror_to_tick_cache=mirror_to_tick_cache
    )
    by_ts: dict[datetime.datetime, KBarRecord] = {}
    roots: list[Path] = []
    if mirror_to_tick_cache:
        roots.append(tick_cache_dir)
    if kbar_cache_dir is not None:
        roots.append(kbar_cache_dir)
    elif not mirror_to_tick_cache:
        roots.append(tick_cache_dir)
    for root in roots:
        path = resolve_kbars_cache_path(root, code, date)
        if path is None:
            continue
        for bar in dedupe_kbars(load_kbars_csv(path)):
            by_ts[bar.ts] = bar
    return sorted(by_ts.values(), key=lambda b: b.ts), write_path


def kbar_gaps_from_ticks(
    code: str,
    date: datetime.date,
    *,
    cache_dir: Path,
) -> list[datetime.datetime]:
    """Return kbar ``ts`` values missing on disk but derivable from ticks."""
    ticks = load_merged_tick_cache(cache_dir, code, date)
    if not ticks:
        return []
    minute_bars = aggregate_ticks_to_minute_bars(ticks)
    existing_path = resolve_kbars_cache_path(cache_dir, code, date)
    existing_ts: set[datetime.datetime] = set()
    if existing_path is not None:
        existing_ts = {b.ts for b in load_kbars_csv(existing_path)}
    missing: list[datetime.datetime] = []
    start = datetime.datetime.combine(date, datetime.time(8, 46))
    end = datetime.datetime.combine(date, DEFAULT_TICK_RANGE_END)
    cur = start
    while cur <= end:
        tick_minute = cur - datetime.timedelta(minutes=1)
        if tick_minute in minute_bars and cur not in existing_ts:
            missing.append(cur)
        cur += datetime.timedelta(minutes=1)
    return missing


def repair_kbars_from_ticks(
    code: str,
    date: datetime.date,
    *,
    tick_cache_dir: Path,
    kbar_cache_dir: Path | None = None,
    mirror_to_tick_cache: bool = True,
    overwrite_from_tick_minute: datetime.time | None = None,
    rebuild_all_from_ticks: bool = False,
) -> int:
    """Insert or refresh kbar rows from ticks. Returns rows added or overwritten."""
    ticks = load_merged_tick_cache(tick_cache_dir, code, date)
    if not ticks:
        return 0
    minute_bars = aggregate_ticks_to_minute_bars(ticks)

    existing, write_path = _load_existing_kbars(
        tick_cache_dir,
        kbar_cache_dir,
        code,
        date,
        mirror_to_tick_cache=mirror_to_tick_cache,
    )
    if not existing and not rebuild_all_from_ticks:
        rebuild_all_from_ticks = True
    by_ts = {} if rebuild_all_from_ticks else {b.ts: b for b in existing}
    changed = 0

    for minute, bar in minute_bars.items():
        kts = _kbar_ts_for_tick_minute(minute)
        if not (datetime.time(8, 46) <= kts.time() <= DEFAULT_TICK_RANGE_END):
            continue
        overwrite = rebuild_all_from_ticks or (
            overwrite_from_tick_minute is not None
            and minute.time() >= overwrite_from_tick_minute
        )
        if kts in by_ts and not overwrite:
            continue
        if kts in by_ts:
            changed += 1
        else:
            changed += 1
        by_ts[kts] = KBarRecord(
            ts=kts,
            Open=bar.Open,
            High=bar.High,
            Low=bar.Low,
            Close=bar.Close,
            Volume=bar.Volume,
        )

    prune_afternoon_orphans = (
        rebuild_all_from_ticks
        or overwrite_from_tick_minute is not None
        or (
            is_near_month_settlement_day(date)
            and _day_session_complete_through(
                ticks, date, EXPECTED_LAST_TICK_MINUTE
            )
        )
    )
    if prune_afternoon_orphans:
        for kts in list(by_ts.keys()):
            tick_minute = kts - datetime.timedelta(minutes=1)
            if tick_minute.time() >= ROLLOVER_AFTERNOON_START:
                if tick_minute not in minute_bars:
                    del by_ts[kts]
                    changed += 1

    if changed == 0:
        return 0

    merged = sorted(by_ts.values(), key=lambda b: b.ts)
    write_path.parent.mkdir(parents=True, exist_ok=True)
    save_kbars_csv(merged, write_path)
    gz_path = kbars_cache_gz_path(write_path.parent, code, date)
    if gz_path.is_file():
        gz_path.unlink()
    logger.info(
        "kbar 補洞 %s %s | Δ%d rows → %s (%d bars)",
        code,
        date.isoformat(),
        changed,
        write_path.name,
        len(merged),
    )

    kdir = kbar_cache_dir or DEFAULT_KBAR_CACHE_DIR
    if mirror_to_tick_cache:
        tick_path = kbars_cache_path(tick_cache_dir, code, date)
        if write_path != tick_path:
            tick_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(write_path, tick_path)
            tick_gz = kbars_cache_gz_path(tick_cache_dir, code, date)
            if tick_gz.is_file():
                tick_gz.unlink()
    if kdir != write_path.parent:
        dst = kbars_cache_path(kdir, code, date)
        if write_path != dst:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(write_path, dst)
            dst_gz = kbars_cache_gz_path(kdir, code, date)
            if dst_gz.is_file():
                dst_gz.unlink()

    return changed


def afternoon_kbar_tick_mismatch_dates(
    code: str,
    dates: list[datetime.date],
    *,
    tick_cache_dir: Path,
    kbar_cache_dir: Path | None,
    mirror_to_tick_cache: bool = True,
) -> set[datetime.date]:
    """Days where 13:30+ kbars disagree with tick-derived OHLC (post-rollover stale)."""
    mismatched: set[datetime.date] = set()
    for date in dates:
        ticks = load_merged_tick_cache(tick_cache_dir, code, date)
        if not ticks:
            continue
        minute_bars = aggregate_ticks_to_minute_bars(ticks)
        existing, write_path = _load_existing_kbars(
            tick_cache_dir,
            kbar_cache_dir,
            code,
            date,
            mirror_to_tick_cache=mirror_to_tick_cache,
        )
        if not existing and not write_path.is_file():
            continue
        by_ts = {b.ts: b for b in existing}
        for minute, bar in minute_bars.items():
            if minute.time() < ROLLOVER_AFTERNOON_START:
                continue
            kts = _kbar_ts_for_tick_minute(minute)
            kbar = by_ts.get(kts)
            if kbar is None:
                continue
            if (
                abs(bar.Open - kbar.Open) > 0.01
                or abs(bar.High - kbar.High) > 0.01
                or abs(bar.Low - kbar.Low) > 0.01
                or abs(bar.Close - kbar.Close) > 0.01
                or bar.Volume != kbar.Volume
            ):
                mismatched.add(date)
                break
    return mismatched


def repair_kbars_batch(
    code: str,
    dates: list[datetime.date],
    *,
    tick_cache_dir: Path,
    kbar_cache_dir: Path | None = DEFAULT_KBAR_CACHE_DIR,
    mirror_to_tick_cache: bool = True,
    rollover_dates: set[datetime.date] | None = None,
) -> list[tuple[datetime.date, int]]:
    full_rebuild = set(rollover_dates or ())
    afternoon_fix = afternoon_kbar_tick_mismatch_dates(
        code,
        dates,
        tick_cache_dir=tick_cache_dir,
        kbar_cache_dir=kbar_cache_dir,
        mirror_to_tick_cache=mirror_to_tick_cache,
    ) - full_rebuild
    results: list[tuple[datetime.date, int]] = []
    for date in dates:
        if date in full_rebuild:
            n = repair_kbars_from_ticks(
                code,
                date,
                tick_cache_dir=tick_cache_dir,
                kbar_cache_dir=kbar_cache_dir,
                mirror_to_tick_cache=mirror_to_tick_cache,
                rebuild_all_from_ticks=True,
            )
        elif date in afternoon_fix:
            n = repair_kbars_from_ticks(
                code,
                date,
                tick_cache_dir=tick_cache_dir,
                kbar_cache_dir=kbar_cache_dir,
                mirror_to_tick_cache=mirror_to_tick_cache,
                overwrite_from_tick_minute=ROLLOVER_AFTERNOON_START,
            )
        else:
            n = repair_kbars_from_ticks(
                code,
                date,
                tick_cache_dir=tick_cache_dir,
                kbar_cache_dir=kbar_cache_dir,
                mirror_to_tick_cache=mirror_to_tick_cache,
            )
        if n > 0:
            results.append((date, n))
    return results
