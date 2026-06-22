"""Backfill orchestration — login, contract resolve, cache layout, rate pacing."""

from __future__ import annotations

import datetime
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Sequence

from storage.cache_paths import DEFAULT_KBAR_CACHE_DIR, DEFAULT_TICK_CACHE_DIR
from storage.kbar_loader import (
    download_and_cache_kbars,
    kbar_cache_satisfies_request,
)
from storage.tick_loader import (
    DEFAULT_TICK_RANGE_END,
    DEFAULT_TICK_RANGE_START,
    date_range,
    download_and_cache,
    tick_cache_satisfies_request,
)

logger = logging.getLogger(__name__)

# Shioaji quote queries: 50 req / 5 sec → stay under ~8 req/sec.
_REQUEST_PACE_SEC = 0.15
# Shioaji intraday query caps (per broker docs); backfill is post-close safe guard.
_MAX_TICK_DAYS_PER_RUN = 10
_MAX_KBAR_DAYS_PER_RUN = 270

TAIWAN_TZ = datetime.timezone(datetime.timedelta(hours=8))


class BackfillError(RuntimeError):
    """User-facing backfill failure (missing creds, invalid dates, etc.)."""


@dataclass
class BackfillResult:
    ticks: List[Path] = field(default_factory=list)
    kbars: List[Path] = field(default_factory=list)
    missing_tick_dates: List[datetime.date] = field(default_factory=list)
    missing_kbar_dates: List[datetime.date] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing_tick_dates and not self.missing_kbar_dates


def taipei_today() -> datetime.date:
    return datetime.datetime.now(TAIWAN_TZ).date()


def taipei_now() -> datetime.datetime:
    return datetime.datetime.now(TAIWAN_TZ)


def _day_session_close_dt(day: datetime.date) -> datetime.datetime:
    return datetime.datetime.combine(day, DEFAULT_TICK_RANGE_END, TAIWAN_TZ)


def validate_past_dates(
    dates: Sequence[datetime.date],
    *,
    today: datetime.date | None = None,
    now: datetime.datetime | None = None,
) -> None:
    """Reject future dates; allow today only after day session close (13:45 Taipei)."""
    ref_now = now if now is not None else taipei_now()
    if ref_now.tzinfo is None:
        ref_now = ref_now.replace(tzinfo=TAIWAN_TZ)
    ref_today = today if today is not None else ref_now.date()
    close_dt = _day_session_close_dt(ref_today)
    for d in dates:
        if d > ref_today:
            raise BackfillError(
                f"{d.isoformat()} 不可 backfill（不可晚於今日台北={ref_today.isoformat()}）"
            )
        if d == ref_today and ref_now < close_dt:
            raise BackfillError(
                f"{d.isoformat()} 日盤尚未收盤（{DEFAULT_TICK_RANGE_END.strftime('%H:%M')} "
                f"台北時間後方可 backfill；現在台北={ref_now.strftime('%H:%M:%S')}）"
            )


def parse_date_args(date_tokens: Sequence[str]) -> List[datetime.date]:
    """Parse one date or an inclusive ``start end`` range."""
    if not date_tokens:
        raise BackfillError("至少需提供一個日期 (YYYY-MM-DD)")
    if len(date_tokens) == 1:
        return [datetime.date.fromisoformat(date_tokens[0])]
    if len(date_tokens) == 2:
        start = datetime.date.fromisoformat(date_tokens[0])
        end = datetime.date.fromisoformat(date_tokens[1])
        if end < start:
            raise BackfillError(f"結束日 {end} 早於開始日 {start}")
        return date_range(start, end)
    raise BackfillError("date 子命令最多接受兩個日期 (start end)")


def validate_tick_day_count(dates: Sequence[datetime.date]) -> None:
    if len(dates) > _MAX_TICK_DAYS_PER_RUN:
        raise BackfillError(
            f"單次 tick backfill 最多 {_MAX_TICK_DAYS_PER_RUN} 個交易日"
            f"（Shioaji 盤中 ticks 查詢上限）；請分批執行，目前={len(dates)}"
        )


def validate_kbar_day_count(dates: Sequence[datetime.date]) -> None:
    if len(dates) > _MAX_KBAR_DAYS_PER_RUN:
        raise BackfillError(
            f"單次 kbar backfill 最多 {_MAX_KBAR_DAYS_PER_RUN} 個交易日"
            f"（Shioaji 盤中 kbars 查詢上限）；請分批執行，目前={len(dates)}"
        )


def resolve_contract(api: Any, code: str) -> Any:
    """Resolve continuous futures code (e.g. TMFR1) like TradingEngine session."""
    category = code[:3]
    cat = getattr(api.Contracts.Futures, category, None)
    if cat is not None and hasattr(cat, code):
        return getattr(cat, code)
    return api.Contracts.Futures[code]


def _require_env_credentials() -> tuple[str, str]:
    api_key = os.environ.get("SJ_API_KEY", "").strip()
    secret_key = os.environ.get("SJ_SEC_KEY", "").strip()
    if not api_key or not secret_key:
        raise BackfillError("需要環境變數 SJ_API_KEY 與 SJ_SEC_KEY（僅行情，不需 CA）")
    return api_key, secret_key


def create_and_login_api(*, simulation: bool) -> Any:
    import shioaji as sj

    api_key, secret_key = _require_env_credentials()
    api = sj.Shioaji(simulation=simulation)
    api.login(api_key, secret_key)
    return api


def _missing_tick_dates(
    code: str,
    dates: Sequence[datetime.date],
    *,
    cache_dir: Path,
    time_start: datetime.time | None,
    time_end: datetime.time | None,
    simulation: bool,
) -> List[datetime.date]:
    return [
        d
        for d in dates
        if not tick_cache_satisfies_request(
            cache_dir,
            code,
            d,
            time_start=time_start,
            time_end=time_end,
            simulation=simulation,
        )
    ]


def _missing_kbar_dates(
    code: str,
    dates: Sequence[datetime.date],
    *,
    cache_dir: Path,
    time_start: datetime.time | None,
    time_end: datetime.time | None,
) -> List[datetime.date]:
    return [
        d
        for d in dates
        if not kbar_cache_satisfies_request(
            cache_dir,
            code,
            d,
            time_start=time_start,
            time_end=time_end,
        )
    ]


def backfill_dates(
    dates: Sequence[datetime.date],
    *,
    code: str,
    simulation: bool,
    fetch_ticks: bool = True,
    fetch_kbars: bool = True,
    tick_cache_dir: Path = DEFAULT_TICK_CACHE_DIR,
    kbar_cache_dir: Path = DEFAULT_KBAR_CACHE_DIR,
    mirror_kbars_to_tick_cache: bool = True,
    overwrite: bool = False,
    tick_time_start: datetime.time | None = DEFAULT_TICK_RANGE_START,
    tick_time_end: datetime.time | None = DEFAULT_TICK_RANGE_END,
    api: Any | None = None,
    today: datetime.date | None = None,
) -> BackfillResult:
    """Backfill ticks and/or kbars for ``dates``."""
    validate_past_dates(dates, today=today)
    if fetch_ticks:
        validate_tick_day_count(dates)
    if fetch_kbars:
        validate_kbar_day_count(dates)

    owns_api = api is None
    if owns_api:
        api = create_and_login_api(simulation=simulation)
    assert api is not None

    result = BackfillResult()
    resolved_code = code
    try:
        contract = resolve_contract(api, code)
        resolved_code = getattr(contract, "code", code)

        if fetch_ticks:
            result.ticks = download_and_cache(
                api,
                contract,
                dates,
                cache_dir=tick_cache_dir,
                overwrite=overwrite,
                time_start=tick_time_start,
                time_end=tick_time_end,
                simulation=simulation,
            )
            time.sleep(_REQUEST_PACE_SEC)

        if fetch_kbars:
            result.kbars = download_and_cache_kbars(
                api,
                contract,
                dates,
                cache_dir=kbar_cache_dir,
                overwrite=overwrite,
                simulation=simulation,
                mirror_cache_dir=tick_cache_dir if mirror_kbars_to_tick_cache else None,
                pace_sec=_REQUEST_PACE_SEC,
                time_start=tick_time_start,
                time_end=tick_time_end,
            )
    finally:
        if owns_api:
            try:
                api.logout()
            except Exception as e:
                logger.warning("api.logout 失敗: %s", e)

    if fetch_ticks:
        result.missing_tick_dates = _missing_tick_dates(
            resolved_code,
            dates,
            cache_dir=tick_cache_dir,
            time_start=tick_time_start,
            time_end=tick_time_end,
            simulation=simulation,
        )
    if fetch_kbars:
        result.missing_kbar_dates = _missing_kbar_dates(
            resolved_code,
            dates,
            cache_dir=kbar_cache_dir,
            time_start=tick_time_start,
            time_end=tick_time_end,
        )
    return result
