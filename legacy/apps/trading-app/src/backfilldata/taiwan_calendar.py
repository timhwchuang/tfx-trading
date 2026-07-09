"""Backfill-facing Taiwan calendar API.

Implementation lives in ``storage.taiwan_calendar`` so storage/bar-cache does not
depend on the backfill package. This module re-exports the public surface for
CLI and existing ``backfilldata.taiwan_calendar`` import paths.
"""

from __future__ import annotations

from storage.taiwan_calendar import (
    DEFAULT_TRADE_DAYS_DIR,
    PIN_YI_CALENDAR_URL_TEMPLATE,
    CalendarError,
    fetch_taiwan_calendar_year,
    get_taiwan_calendar_year,
    load_taiwan_calendar_year,
    month_bounds,
    parse_month_arg,
    resolve_month_trading_days,
    resolve_month_trading_days_with_fallback,
    resolve_trading_days_in_range,
    resolve_trading_days_in_range_with_fallback,
    yyyymmdd_to_date,
)

__all__ = [
    "CalendarError",
    "DEFAULT_TRADE_DAYS_DIR",
    "PIN_YI_CALENDAR_URL_TEMPLATE",
    "fetch_taiwan_calendar_year",
    "get_taiwan_calendar_year",
    "load_taiwan_calendar_year",
    "month_bounds",
    "parse_month_arg",
    "resolve_month_trading_days",
    "resolve_month_trading_days_with_fallback",
    "resolve_trading_days_in_range",
    "resolve_trading_days_in_range_with_fallback",
    "yyyymmdd_to_date",
]
