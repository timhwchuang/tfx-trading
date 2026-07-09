"""Backfill orchestration — login, contract resolve, cache layout, rate pacing."""

from __future__ import annotations

import calendar
import datetime
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Sequence

from backfilldata.errors import BackfillError
from storage.cache_paths import DEFAULT_TICK_CACHE_DIR
from storage.kbar_loader import download_and_cache_kbars
from storage.tick_loader import (
    DEFAULT_TICK_RANGE_END,
    date_range,
    download_and_cache,
)
from backfilldata.tick_rollover import merge_rollover_afternoon_batch

logger = logging.getLogger(__name__)

# Shioaji quote queries: 50 req / 5 sec → stay under ~8 req/sec.
_REQUEST_PACE_SEC = 0.15
# Shioaji intraday query caps (per broker docs); backfill is post-close safe guard.
_MAX_TICK_DAYS_PER_RUN = 10
_MAX_KBAR_DAYS_PER_RUN = 270

TAIWAN_TZ = datetime.timezone(datetime.timedelta(hours=8))


@dataclass
class BackfillResult:
    ticks: List[Path] = field(default_factory=list)
    kbars: List[Path] = field(default_factory=list)
    failed_dates: List[datetime.date] = field(default_factory=list)
    # Kept for callers/tests; empty days are not treated as missing.
    missing_tick_dates: List[datetime.date] = field(default_factory=list)
    missing_kbar_dates: List[datetime.date] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed_dates


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


def calendar_days_in_month(year: int, month: int) -> list[datetime.date]:
    """Every calendar day in ``year``-``month`` (1 .. last day)."""
    last = calendar.monthrange(year, month)[1]
    return [datetime.date(year, month, day) for day in range(1, last + 1)]


def month_bounds(year: int, month: int) -> tuple[datetime.date, datetime.date]:
    days = calendar_days_in_month(year, month)
    return days[0], days[-1]


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


def _merge_backfill_results(target: BackfillResult, batch: BackfillResult) -> None:
    target.ticks.extend(batch.ticks)
    target.kbars.extend(batch.kbars)
    target.failed_dates.extend(batch.failed_dates)
    target.missing_tick_dates.extend(batch.missing_tick_dates)
    target.missing_kbar_dates.extend(batch.missing_kbar_dates)


def filter_backfill_eligible_dates(
    dates: Sequence[datetime.date],
    *,
    today: datetime.date | None = None,
    now: datetime.datetime | None = None,
) -> tuple[list[datetime.date], list[datetime.date]]:
    """Drop future dates and today before day-session close (per-day validate)."""
    eligible: list[datetime.date] = []
    skipped: list[datetime.date] = []
    for d in dates:
        try:
            validate_past_dates([d], today=today, now=now)
        except BackfillError:
            skipped.append(d)
            continue
        eligible.append(d)
    return eligible, skipped


def backfill_dates_batched(
    dates: Sequence[datetime.date],
    *,
    range_start: datetime.date | None = None,
    range_end: datetime.date | None = None,
    today: datetime.date | None = None,
    now: datetime.datetime | None = None,
    **kwargs: Any,
) -> tuple[BackfillResult, list[BackfillResult]]:
    """Backfill ``dates`` in API-sized chunks (single login when ``api`` omitted)."""
    del range_start, range_end, now  # calendar span unused; AllDay uses same day list
    tick_dates = list(dates)
    fetch_ticks = kwargs.get("fetch_ticks", True)
    fetch_kbars = kwargs.get("fetch_kbars", True)
    kbar_dates = list(tick_dates) if fetch_kbars else []

    if not tick_dates and not kbar_dates:
        return BackfillResult(), []

    merged = BackfillResult()
    batches: list[BackfillResult] = []
    api = kwargs.pop("api", None)
    owns_api = api is None
    if owns_api:
        api = create_and_login_api(simulation=kwargs["simulation"])
    try:
        if fetch_ticks and tick_dates:
            tick_chunk = _MAX_TICK_DAYS_PER_RUN
            for offset in range(0, len(tick_dates), tick_chunk):
                chunk = tick_dates[offset : offset + tick_chunk]
                tick_kwargs = {**kwargs, "fetch_ticks": True, "fetch_kbars": False}
                batch = backfill_dates(
                    chunk,
                    api=api,
                    today=today,
                    **tick_kwargs,
                )
                batches.append(batch)
                _merge_backfill_results(merged, batch)

        if fetch_kbars and kbar_dates:
            kbar_chunk = _MAX_KBAR_DAYS_PER_RUN
            for offset in range(0, len(kbar_dates), kbar_chunk):
                chunk = kbar_dates[offset : offset + kbar_chunk]
                kbar_kwargs = {**kwargs, "fetch_ticks": False, "fetch_kbars": True}
                batch = backfill_dates(
                    [],
                    kbar_dates=chunk,
                    api=api,
                    today=today,
                    **kbar_kwargs,
                )
                batches.append(batch)
                _merge_backfill_results(merged, batch)
    finally:
        if owns_api and api is not None:
            try:
                api.logout()
            except Exception as e:
                logger.warning("api.logout 失敗: %s", e)

    return merged, batches


def backfill_month(
    year: int,
    month: int,
    *,
    today: datetime.date | None = None,
    now: datetime.datetime | None = None,
    **kwargs: Any,
) -> tuple[BackfillResult, dict[str, Any]]:
    """Backfill every calendar day in a month (batched for API limits)."""
    calendar_days = calendar_days_in_month(year, month)
    eligible, skipped_future = filter_backfill_eligible_dates(
        calendar_days,
        today=today,
        now=now,
    )
    month_start, month_end = month_bounds(year, month)
    merged, batches = backfill_dates_batched(
        eligible,
        range_start=month_start,
        range_end=month_end,
        today=today,
        now=now,
        **kwargs,
    )
    meta = {
        "calendar_days": calendar_days,
        "eligible_days": eligible,
        "kbar_days": list(eligible) if kwargs.get("fetch_kbars", True) else [],
        "skipped_future": skipped_future,
        "batches": batches,
    }
    return merged, meta


def backfill_dates(
    dates: Sequence[datetime.date],
    *,
    kbar_dates: Sequence[datetime.date] | None = None,
    code: str,
    simulation: bool,
    fetch_ticks: bool = True,
    fetch_kbars: bool = True,
    cache_dir: Path = DEFAULT_TICK_CACHE_DIR,
    overwrite: bool = False,
    tick_time_start: datetime.time | None = None,
    tick_time_end: datetime.time | None = None,
    merge_rollover: bool = True,
    api: Any | None = None,
    today: datetime.date | None = None,
) -> BackfillResult:
    """Backfill AllDay ticks/kbars. Empty successful skips are OK (not failures)."""
    tick_dates = list(dates) if fetch_ticks else []
    kbar_days = list(kbar_dates if kbar_dates is not None else dates) if fetch_kbars else []

    if fetch_ticks and tick_dates:
        validate_past_dates(tick_dates, today=today)
        validate_tick_day_count(tick_dates)
    if fetch_kbars and kbar_days:
        validate_past_dates(kbar_days, today=today)
        validate_kbar_day_count(kbar_days)
    if not tick_dates and not kbar_days:
        return BackfillResult()

    owns_api = api is None
    if owns_api:
        api = create_and_login_api(simulation=simulation)
    assert api is not None

    result = BackfillResult()
    resolved_code = code
    try:
        contract = resolve_contract(api, code)
        resolved_code = getattr(contract, "code", code)

        if fetch_ticks and tick_dates:
            try:
                result.ticks = download_and_cache(
                    api,
                    contract,
                    tick_dates,
                    cache_dir=cache_dir,
                    overwrite=overwrite,
                    time_start=tick_time_start,
                    time_end=tick_time_end,
                    simulation=simulation,
                )
            except Exception as e:
                logger.warning("tick backfill batch failed: %s", e)
                result.failed_dates.extend(tick_dates)
            time.sleep(_REQUEST_PACE_SEC)

            if merge_rollover and not result.failed_dates:
                rollover_days = merge_rollover_afternoon_batch(
                    api,
                    resolved_code,
                    tick_dates,
                    cache_dir=cache_dir,
                    simulation=simulation,
                    resolve_contract=resolve_contract,
                )
                if rollover_days:
                    logger.info(
                        "跨月 tick 合併完成 %d 天: %s",
                        len(rollover_days),
                        ", ".join(d.isoformat() for d in rollover_days),
                    )

        if fetch_kbars and kbar_days:
            try:
                result.kbars = download_and_cache_kbars(
                    api,
                    contract,
                    kbar_days,
                    cache_dir=cache_dir,
                    overwrite=overwrite,
                    pace_sec=_REQUEST_PACE_SEC,
                    time_start=tick_time_start,
                    time_end=tick_time_end,
                )
            except Exception as e:
                logger.warning("kbar backfill batch failed: %s", e)
                for d in kbar_days:
                    if d not in result.failed_dates:
                        result.failed_dates.append(d)
    finally:
        if owns_api:
            try:
                api.logout()
            except Exception as e:
                logger.warning("api.logout 失敗: %s", e)

    return result
