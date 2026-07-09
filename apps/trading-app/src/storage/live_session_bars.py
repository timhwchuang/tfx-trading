"""Live tick feed into SessionBars via 1m aggregation."""

from __future__ import annotations

import datetime
import logging
from pathlib import Path
from typing import Any

from storage.bars import SessionBars
from storage.cache_paths import DEFAULT_TICK_CACHE_DIR, DEFAULT_TRADE_DAYS_DIR
from storage.kbar_loader import KBarRecord, append_kbar_csv, kbar_path, read_last_kbar_ts
from storage.minute_bar_aggregator import MinuteBarAggregator, minute_floor
from storage.session_bar_cache import SessionBarCache, kbar_file_date
from storage.tick_archiver import tick_to_archive_record

logger = logging.getLogger(__name__)


class LiveSessionBars:
    """Warm-load SessionBars, then push tick-derived closed 1m bars via ``on_bar``."""

    def __init__(
        self,
        bars: SessionBars,
        *,
        cache_dir: Path = DEFAULT_TICK_CACHE_DIR,
        persist_kbars: bool = False,
        as_of: datetime.datetime | None = None,
    ) -> None:
        self._bars = bars
        self._cache_dir = cache_dir
        self._persist_kbars = persist_kbars
        self._aggregator = MinuteBarAggregator()
        self._bars_written = 0
        self._ingested_ts: set[datetime.datetime] = set()
        self._path_last_ts: dict[Path, datetime.datetime] = {}
        if as_of is not None:
            self._reseed_from_disk(as_of)

    @classmethod
    def start(
        cls,
        code: str,
        as_of: datetime.datetime | None = None,
        *,
        cache_dir: Path = DEFAULT_TICK_CACHE_DIR,
        persist_kbars: bool = False,
    ) -> LiveSessionBars:
        anchor = as_of or datetime.datetime.now()
        bars = SessionBars.load(code, anchor, cache_dir=cache_dir)
        logger.info(
            "LiveSessionBars start | code=%s as_of=%s persist_kbars=%s",
            code,
            anchor,
            persist_kbars,
        )
        return cls(bars, cache_dir=cache_dir, persist_kbars=persist_kbars, as_of=anchor)

    def on_tick(self, tick: Any, tick_type: int) -> KBarRecord | None:
        """Aggregate one tick; return closed 1m bar when the minute rolls."""
        record = tick_to_archive_record(tick, tick_type)
        closed_bars = self._aggregator.on_tick(
            record.datetime,
            float(record.close),
            record.volume,
        )
        if not closed_bars:
            return None
        for bar in closed_bars:
            self._ingest_closed_bar(bar)
        return closed_bars[-1]

    def flush(self) -> KBarRecord | None:
        """Flush the open minute bar at session shutdown."""
        closed = self._aggregator.flush()
        if closed is None:
            return None
        self._ingest_closed_bar(closed)
        return closed

    def reload(
        self,
        as_of: datetime.datetime | None = None,
        *,
        calendar_dir: Path = DEFAULT_TRADE_DAYS_DIR,
    ) -> None:
        """Reload from disk (e.g. after kbars archive)."""
        target = as_of or self._bars.as_of
        self._bars.reload(
            as_of,
            cache_dir=self._cache_dir,
            calendar_dir=calendar_dir,
        )
        self._reseed_from_disk(target)

    @property
    def session_bars(self) -> SessionBars:
        return self._bars

    @property
    def bars_written(self) -> int:
        return self._bars_written

    def _session_store(self) -> SessionBarCache | None:
        try:
            store = self._bars.cache
        except (AttributeError, TypeError):
            return None
        return store if isinstance(store, SessionBarCache) else None

    def _reseed_from_disk(self, as_of: datetime.datetime) -> None:
        self._aggregator = MinuteBarAggregator()
        self._ingested_ts.clear()
        self._seed_from_cache(as_of)
        self._seed_persist_tail_ts()

    def _seed_from_cache(self, as_of: datetime.datetime) -> None:
        """Seed aggregator and dedupe set from warm-loaded 1m history."""
        store = self._session_store()
        if store is None:
            return
        bars = store.bars_1m_as_of(as_of)
        if not bars:
            return
        for bar in bars:
            self._ingested_ts.add(bar.ts)
        last = max(bars, key=lambda b: b.ts)
        last_open_minute = last.ts - datetime.timedelta(minutes=1)
        as_of_minute = minute_floor(as_of)
        if as_of_minute > last_open_minute:
            self._aggregator.seed_minute(
                as_of_minute,
                open_=last.Close,
                high=last.Close,
                low=last.Close,
                close=last.Close,
                volume=0,
            )
        elif as_of_minute == last_open_minute:
            self._aggregator.seed_minute(
                as_of_minute,
                open_=last.Open,
                high=last.High,
                low=last.Low,
                close=last.Close,
                volume=last.Volume,
            )

    def _seed_persist_tail_ts(self) -> None:
        if not self._persist_kbars:
            return
        store = self._session_store()
        if store is None:
            return
        seen: set[Path] = set()
        for bar in store.bars_1m_as_of(self._bars.as_of):
            path = self._kbar_persist_path(bar)
            if path in seen:
                continue
            seen.add(path)
            last = read_last_kbar_ts(path)
            if last is not None:
                self._path_last_ts[path] = last

    def _kbar_persist_path(self, bar: KBarRecord) -> Path:
        store = self._session_store()
        if store is not None:
            file_day = kbar_file_date(bar, store.trading_days)
        else:
            file_day = bar.ts.date()
        return kbar_path(self._cache_dir, self._bars.code, file_day)

    def _ingest_closed_bar(self, bar: KBarRecord) -> None:
        if bar.ts in self._ingested_ts:
            return
        if bar.Volume == 0:
            return
        self._ingested_ts.add(bar.ts)
        self._bars.on_bar(bar)
        self._bars_written += 1
        if self._persist_kbars and bar.Volume > 0:
            path = self._kbar_persist_path(bar)
            if append_kbar_csv(bar, path, last_ts=self._path_last_ts.get(path)):
                self._path_last_ts[path] = bar.ts
        logger.debug(
            "Live 1m closed | ts=%s C=%.0f V=%d",
            bar.ts,
            bar.Close,
            bar.Volume,
        )


__all__ = ["LiveSessionBars"]