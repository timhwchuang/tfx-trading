"""Taiwan calendar API (pin-yi) → trading-day filter for backfill month."""

from __future__ import annotations

import datetime
import json
import logging
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Sequence

from storage.cache_paths import DEFAULT_TRADE_DAYS_DIR
from storage.tick_loader import date_range

from backfilldata.core import BackfillError

logger = logging.getLogger(__name__)

PIN_YI_CALENDAR_URL_TEMPLATE = "https://api.pin-yi.me/taiwan-calendar/{year}"
_MIN_REQUEST_INTERVAL_SEC = 0.5
_last_fetch_monotonic: float = 0.0


def parse_month_arg(month_token: str) -> tuple[int, int]:
    """Parse ``YYYY-MM`` (month 1–12)."""
    raw = month_token.strip()
    if len(raw) != 7 or raw[4] != "-":
        raise BackfillError(f"無效月份: {month_token!r}（需 YYYY-MM）")
    try:
        year = int(raw[:4])
        month = int(raw[5:7])
    except ValueError as exc:
        raise BackfillError(f"無效月份: {month_token!r}（需 YYYY-MM）") from exc
    if not 1 <= month <= 12:
        raise BackfillError(f"無效月份: {month_token!r}（月份需 01–12）")
    return year, month


def month_bounds(year: int, month: int) -> tuple[datetime.date, datetime.date]:
    start = datetime.date(year, month, 1)
    if month == 12:
        end = datetime.date(year + 1, 1, 1) - datetime.timedelta(days=1)
    else:
        end = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)
    return start, end


def yyyymmdd_to_date(value: str) -> datetime.date:
    raw = str(value).strip()
    if len(raw) != 8 or not raw.isdigit():
        raise ValueError(f"invalid YYYYMMDD date: {value!r}")
    return datetime.date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))


def _calendar_cache_path(year: int, calendar_dir: Path) -> Path:
    return calendar_dir / f"{year}.json"


def _pace_calendar_request() -> None:
    global _last_fetch_monotonic
    now = time.monotonic()
    elapsed = now - _last_fetch_monotonic
    if elapsed < _MIN_REQUEST_INTERVAL_SEC:
        time.sleep(_MIN_REQUEST_INTERVAL_SEC - elapsed)
    _last_fetch_monotonic = time.monotonic()


def _parse_calendar_payload(data: Any, *, source: str) -> list[dict[str, Any]]:
    if not isinstance(data, list):
        raise BackfillError(f"Taiwan 行事曆 {source} 格式異常（預期 JSON array）")
    if not data:
        raise BackfillError(f"Taiwan 行事曆 {source} 無資料（year 可能不支援或 API 異常）")
    return data


def load_taiwan_calendar_year(
    year: int,
    *,
    calendar_dir: Path = DEFAULT_TRADE_DAYS_DIR,
) -> list[dict[str, Any]]:
    """Load a cached yearly calendar from ``trade_days/{year}.json``."""
    path = _calendar_cache_path(year, calendar_dir)
    if not path.is_file():
        raise FileNotFoundError(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BackfillError(f"Taiwan 行事曆快取 {path.name} 非 JSON") from exc
    return _parse_calendar_payload(data, source=path.name)


def _save_calendar_cache(
    year: int,
    data: list[dict[str, Any]],
    calendar_dir: Path,
) -> Path:
    calendar_dir.mkdir(parents=True, exist_ok=True)
    path = _calendar_cache_path(year, calendar_dir)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    logger.info("已快取 Taiwan 行事曆: %s", path)
    return path


def fetch_taiwan_calendar_year(
    year: int,
    *,
    timeout_sec: float = 30.0,
    calendar_dir: Path = DEFAULT_TRADE_DAYS_DIR,
    save_cache: bool = True,
) -> list[dict[str, Any]]:
    """Download pin-yi Taiwan calendar JSON for a Gregorian year."""
    url = PIN_YI_CALENDAR_URL_TEMPLATE.format(year=year)
    _pace_calendar_request()
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "tfx-trading-backfilldata/1.0",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            payload = resp.read()
    except urllib.error.URLError as exc:
        raise BackfillError(f"Taiwan 行事曆 API 無法連線: {exc}") from exc
    try:
        data = json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise BackfillError("Taiwan 行事曆 API 回傳非 JSON") from exc
    parsed = _parse_calendar_payload(data, source="API")
    if save_cache:
        _save_calendar_cache(year, parsed, calendar_dir)
    return parsed


def get_taiwan_calendar_year(
    year: int,
    *,
    calendar_dir: Path = DEFAULT_TRADE_DAYS_DIR,
    timeout_sec: float = 30.0,
) -> list[dict[str, Any]]:
    """Prefer ``trade_days/{year}.json``; download and persist on cache miss or invalid cache."""
    path = _calendar_cache_path(year, calendar_dir)
    if path.is_file():
        try:
            return load_taiwan_calendar_year(year, calendar_dir=calendar_dir)
        except BackfillError as exc:
            logger.warning("行事曆快取無效，改從 API 重新下載: %s (%s)", path, exc)
    else:
        logger.debug("行事曆快取不存在，改從 API 下載: %s", path)
    return fetch_taiwan_calendar_year(
        year,
        timeout_sec=timeout_sec,
        calendar_dir=calendar_dir,
    )


def _is_holiday_entry(entry: dict[str, Any]) -> bool:
    return bool(entry.get("isHoliday"))


def resolve_month_trading_days(
    year: int,
    month: int,
    *,
    use_holiday_calendar: bool = True,
    calendar_year: Sequence[dict[str, Any]] | None = None,
    calendar_dir: Path = DEFAULT_TRADE_DAYS_DIR,
) -> tuple[list[datetime.date], dict[str, list[datetime.date]]]:
    """Return sorted trading days in month and skip buckets for logging."""
    start, end = month_bounds(year, month)
    month_days = date_range(start, end)

    if not use_holiday_calendar:
        weekdays = [d for d in month_days if d.weekday() < 5]
        return weekdays, {
            "weekend": [d for d in month_days if d.weekday() >= 5],
            "holiday": [],
        }

    entries = (
        list(calendar_year)
        if calendar_year is not None
        else get_taiwan_calendar_year(year, calendar_dir=calendar_dir)
    )
    _parse_calendar_payload(entries, source=f"{year}")

    by_date: dict[datetime.date, dict[str, Any]] = {}
    for entry in entries:
        try:
            day = yyyymmdd_to_date(str(entry.get("date", "")))
        except ValueError:
            logger.warning("略過無效行事曆日期: %s", entry.get("date"))
            continue
        if start <= day <= end:
            by_date[day] = entry

    trading_days: list[datetime.date] = []
    skipped_weekend: list[datetime.date] = []
    skipped_holiday: list[datetime.date] = []
    skipped_missing: list[datetime.date] = []

    for day in month_days:
        entry = by_date.get(day)
        if entry is None:
            if day.weekday() >= 5:
                skipped_weekend.append(day)
            else:
                skipped_missing.append(day)
            continue
        if _is_holiday_entry(entry):
            if day.weekday() >= 5:
                skipped_weekend.append(day)
            else:
                skipped_holiday.append(day)
        else:
            trading_days.append(day)

    if calendar_year is None and skipped_missing:
        sample = ", ".join(d.isoformat() for d in skipped_missing[:3])
        raise BackfillError(
            f"Taiwan 行事曆 {year} 不完整，缺少 {len(skipped_missing)} 個平日（例: {sample}）"
        )

    return trading_days, {
        "weekend": skipped_weekend,
        "holiday": skipped_holiday,
        "missing_calendar": skipped_missing,
    }


def resolve_month_trading_days_with_fallback(
    year: int,
    month: int,
    *,
    use_holiday_calendar: bool = True,
    calendar_year: Sequence[dict[str, Any]] | None = None,
    calendar_dir: Path = DEFAULT_TRADE_DAYS_DIR,
) -> tuple[list[datetime.date], dict[str, list[datetime.date]]]:
    """Resolve trading days; on calendar failure fall back to weekdays-only."""
    try:
        return resolve_month_trading_days(
            year,
            month,
            use_holiday_calendar=use_holiday_calendar,
            calendar_year=calendar_year,
            calendar_dir=calendar_dir,
        )
    except BackfillError as exc:
        if use_holiday_calendar and "行事曆" in str(exc):
            logger.warning("%s；改為僅跳過週末", exc)
            return resolve_month_trading_days(
                year,
                month,
                use_holiday_calendar=False,
                calendar_year=calendar_year,
                calendar_dir=calendar_dir,
            )
        raise
