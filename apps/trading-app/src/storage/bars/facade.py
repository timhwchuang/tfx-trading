"""User-facing SessionBars facade over SessionBarCache."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

from backfilldata.taiwan_calendar import DEFAULT_TRADE_DAYS_DIR
from storage.bars.executor import QueryExecutor
from storage.bars.protocols import BarStore
from storage.bars.spec import parse_query
from storage.cache_paths import DEFAULT_TICK_CACHE_DIR
from storage.kbar_loader import KBarRecord
from storage.session_bar_cache import SessionBarCache, TfSpec, TodayKbarStatus


class SessionBars:
    """Intuitive query API over Yuanta-anchored SessionBarCache."""

    def __init__(self, store: BarStore) -> None:
        self._store = store
        self._executor = QueryExecutor(store)

    @classmethod
    def load(
        cls,
        code: str,
        as_of: datetime.datetime,
        *,
        cache_dir: Path = DEFAULT_TICK_CACHE_DIR,
        tf_table: dict[str, TfSpec] | None = None,
        calendar_dir: Path = DEFAULT_TRADE_DAYS_DIR,
    ) -> SessionBars:
        cache = SessionBarCache.load(
            code,
            as_of,
            cache_dir=cache_dir,
            tf_table=tf_table,
            calendar_dir=calendar_dir,
        )
        return cls(cache)

    @classmethod
    def from_cache(cls, cache: SessionBarCache) -> SessionBars:
        return cls(cache)

    def get(self, tf: str, spec: str | int | None = None) -> Any:
        """Query bars or indicators.

        Examples:
            get("4h")              -> list[BarRecord]
            get("4h", 20)          -> last 20 closed bars
            get("4h", "last")      -> BarRecord | None
            get("1m", "ma20")      -> float | None
            get("daily", "ma20")   -> session daily MA20
            get("today")           -> TodayKbarStatus
        """
        return self._executor.execute(parse_query(tf, spec))

    def series(self, tf: str, *, n: int | None = None) -> list[KBarRecord]:
        return self._executor.series(tf, n=n)

    def closes(self, tf: str, *, n: int | None = None) -> list[float]:
        return self._executor.closes(tf, n=n)

    def on_bar(self, bar: KBarRecord) -> None:
        self._store.on_new_1m(bar)

    def reload(
        self,
        as_of: datetime.datetime | None = None,
        *,
        cache_dir: Path = DEFAULT_TICK_CACHE_DIR,
        tf_table: dict[str, TfSpec] | None = None,
        calendar_dir: Path = DEFAULT_TRADE_DAYS_DIR,
    ) -> None:
        if not isinstance(self._store, SessionBarCache):
            raise TypeError("reload() requires SessionBarCache-backed SessionBars")
        target = as_of or self._store.as_of
        refreshed = SessionBarCache.load(
            self._store.code,
            target,
            cache_dir=cache_dir,
            tf_table=tf_table or self._store.tf_table,
            calendar_dir=calendar_dir,
        )
        self._store = refreshed
        self._executor = QueryExecutor(refreshed)

    @property
    def as_of(self) -> datetime.datetime:
        return self._store.as_of

    @property
    def code(self) -> str:
        return self._store.code

    @property
    def cache(self) -> SessionBarCache:
        if not isinstance(self._store, SessionBarCache):
            raise TypeError("underlying store is not SessionBarCache")
        return self._store


__all__ = ["SessionBars"]