"""Market calendar port — exchange session/time helpers injected into TradingEngine."""

from __future__ import annotations

import datetime
from typing import Protocol

import trading_engine.calendar.taifex as taifex


class MarketCalendarPort(Protocol):
    def trading_day_for_daily_reset(self, dt: datetime.datetime) -> datetime.date: ...

    def is_trading_session(
        self,
        dt: datetime.datetime,
        session_start: datetime.time,
        session_end: datetime.time,
    ) -> bool: ...

    def is_at_or_after(
        self,
        dt: datetime.datetime,
        cutoff: datetime.time,
        *,
        session_start: datetime.time | None = None,
        session_end: datetime.time | None = None,
    ) -> bool: ...

    def is_opening_session_window(self, dt: datetime.datetime) -> bool: ...


class TaifexMarketCalendar:
    """Default TAIFEX day-session calendar (Taiwan local time)."""

    def trading_day_for_daily_reset(self, dt: datetime.datetime) -> datetime.date:
        return taifex.trading_day_for_daily_reset(dt)

    def is_trading_session(
        self,
        dt: datetime.datetime,
        session_start: datetime.time,
        session_end: datetime.time,
    ) -> bool:
        return taifex.is_trading_session(dt, session_start, session_end)

    def is_at_or_after(
        self,
        dt: datetime.datetime,
        cutoff: datetime.time,
        *,
        session_start: datetime.time | None = None,
        session_end: datetime.time | None = None,
    ) -> bool:
        return taifex.is_at_or_after(
            dt,
            cutoff,
            session_start=session_start,
            session_end=session_end,
        )

    def is_opening_session_window(self, dt: datetime.datetime) -> bool:
        return taifex.is_opening_session_window(dt)


__all__ = ["MarketCalendarPort", "TaifexMarketCalendar"]
