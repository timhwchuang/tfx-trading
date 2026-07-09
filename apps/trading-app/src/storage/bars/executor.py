"""Execute parsed SessionBars queries against a BarStore."""

from __future__ import annotations

from storage.bars.indicators import moving_average
from storage.bars.protocols import BarStore
from storage.bars.spec import ParsedQuery, normalize_tf
from storage.kbar_loader import KBarRecord
from storage.session_bar_cache import DEFAULT_TF_TABLE, TodayKbarStatus


class QueryExecutor:
    def __init__(self, store: BarStore) -> None:
        self._store = store

    def execute(self, query: ParsedQuery) -> (
        list[KBarRecord]
        | list[float]
        | KBarRecord
        | float
        | dict[str, float | None]
        | TodayKbarStatus
        | None
    ):
        if query.kind == "today":
            return self._store.today_status

        self._validate_tf(query.tf)

        if query.kind == "series":
            bars = self._closed(query.tf)
            if query.n is not None:
                return bars[-query.n :]
            return bars

        if query.kind == "closes":
            bars = self._closed(query.tf)
            if query.n is not None:
                bars = bars[-query.n :]
            return [float(b.Close) for b in bars]

        if query.kind == "last":
            bars = self._closed(query.tf)
            return bars[-1] if bars else None

        if query.kind == "current":
            if query.tf == "daily":
                return None
            return self._store.current(query.tf)

        if query.kind == "ma":
            assert query.ma_period is not None
            if query.tf == "daily":
                return self._store.daily_ma(query.ma_period)
            closes = [float(b.Close) for b in self._closed(query.tf)]
            return moving_average(closes, query.ma_period)

        if query.kind == "mas":
            return self._store.daily_mas()

        raise KeyError(f"unsupported query kind: {query.kind}")

    def series(self, tf: str, *, n: int | None = None) -> list[KBarRecord]:
        result = self.execute(ParsedQuery(tf=normalize_tf(tf), kind="series", n=n))
        assert isinstance(result, list)
        return result

    def closes(self, tf: str, *, n: int | None = None) -> list[float]:
        result = self.execute(
            ParsedQuery(tf=normalize_tf(tf), kind="closes", n=n)
        )
        assert isinstance(result, list)
        return result

    def _closed(self, tf: str) -> list[KBarRecord]:
        if tf == "daily":
            return list(self._store.daily_closed())
        return list(self._store.closed(tf))

    def _validate_tf(self, tf: str) -> None:
        if tf == "daily":
            return
        if tf not in DEFAULT_TF_TABLE:
            known = ", ".join(sorted({*DEFAULT_TF_TABLE.keys(), "daily", "today"}))
            raise KeyError(f"unknown timeframe {tf!r}; known: {known}")


__all__ = ["QueryExecutor"]