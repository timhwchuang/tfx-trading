"""Protocols for SessionBars query layer."""

from __future__ import annotations

import datetime
from typing import Protocol

from storage.kbar_loader import KBarRecord
from storage.session_bar_cache import TodayKbarStatus


class BarStore(Protocol):
    """Read-only multi-TF bar materialization (SessionBarCache implements this)."""

    code: str
    as_of: datetime.datetime
    today_status: TodayKbarStatus

    def closed(self, tf: str) -> list[KBarRecord]: ...

    def current(self, tf: str) -> KBarRecord | None: ...

    def daily_closed(self) -> list[KBarRecord]: ...

    def daily_ma(self, period: int) -> float | None: ...

    def daily_mas(self) -> dict[str, float | None]: ...

    def on_new_1m(self, bar: KBarRecord) -> None: ...


__all__ = ["BarStore"]