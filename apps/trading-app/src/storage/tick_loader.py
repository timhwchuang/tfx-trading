"""Phase 0: Shioaji historical tick loader + local cache for backtesting.

職責：
* 透過 ``api.ticks(contract, date, query_type=RangeTime|AllDay)`` 抓取歷史 tick。
* 落地成本地 CSV 快取（純 stdlib，不依賴 pandas/pyarrow），回測一律讀快取。
* 配額感知：抓取前後記錄 ``api.usage()``，剩餘 < 10% 告警。
* 提供 ``ReplayTick`` 與線上 ``TickFOPv1`` 同構的屬性（datetime/close/volume/tick_type），
  讓回測重放可直接餵進 ``TradingEngine.on_tick``。

Shioaji 歷史資料限制（務必知悉）：
* 只有「最佳一檔」買賣價，沒有歷史 order book 深度，無排隊位置。
* 只能抓過去日期，且受 ``usage().limit_bytes`` 流量配額限制。
* 歷史 ``Ticks`` 無 ``simtrade`` 旗標（試搓單過濾僅適用即時串流）。
"""

from __future__ import annotations

import csv
import datetime
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, List, Optional, Sequence

logger = logging.getLogger(__name__)

from storage.cache_paths import DEFAULT_CACHE_DIR, DEFAULT_TICK_CACHE_DIR
from trading_engine.calendar.shioaji_ts import shioaji_historical_ts_from_ns

DEFAULT_TICK_RANGE_START = datetime.time(8, 45, 0)
DEFAULT_TICK_RANGE_END = datetime.time(13, 45, 0)
_WINDOW_EDGE_TOLERANCE_MIN = 1
_TICK_MAX_GAP_MIN = 30
TAIWAN_TZ = datetime.timezone(datetime.timedelta(hours=8))

# Full-day AllDay ticks routinely exceed Shioaji's default 5s API timeout.
_TICKS_API_TIMEOUT_MS = 30_000
_TICK_FETCH_MAX_ATTEMPTS = 3
_TICK_FETCH_RETRY_SLEEP_SEC = 2.0

TICK_CSV_FIELDS = [
    "datetime",
    "close",
    "volume",
    "bid_price",
    "ask_price",
    "tick_type",
]
_CSV_FIELDS = TICK_CSV_FIELDS


@dataclass
class ReplayTick:
    """與 TickFOPv1 同構的最小重放單元（策略只用 datetime/close/volume/tick_type）。"""

    datetime: datetime.datetime
    close: str
    volume: int
    tick_type: int
    bid_price: float = 0.0
    ask_price: float = 0.0


def _taipei_today() -> datetime.date:
    return datetime.datetime.now(TAIWAN_TZ).date()


def _is_transient_tick_fetch_error(exc: BaseException) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    msg = str(exc)
    return "Timeout" in msg or "timeout" in msg


def _raw_ticks_to_replay(raw: Any) -> List[ReplayTick]:
    ts = list(raw.ts)
    close = list(raw.close)
    volume = list(raw.volume)
    bid = list(getattr(raw, "bid_price", []) or [])
    ask = list(getattr(raw, "ask_price", []) or [])
    tick_type = list(getattr(raw, "tick_type", []) or [])

    ticks: List[ReplayTick] = []
    for i in range(len(ts)):
        ticks.append(
            ReplayTick(
                datetime=shioaji_historical_ts_from_ns(int(ts[i])),
                close=str(close[i]),
                volume=int(volume[i]),
                tick_type=int(tick_type[i]) if i < len(tick_type) else 0,
                bid_price=float(bid[i]) if i < len(bid) else 0.0,
                ask_price=float(ask[i]) if i < len(ask) else 0.0,
            )
        )
    ticks.sort(key=lambda t: t.datetime)
    return ticks


def _call_ticks_api(
    api: Any,
    contract: Any,
    date: datetime.date,
    *,
    query_type: Any,
    time_start: datetime.time | None = None,
    time_end: datetime.time | None = None,
) -> Any:
    last_exc: BaseException | None = None
    for attempt in range(1, _TICK_FETCH_MAX_ATTEMPTS + 1):
        try:
            kwargs: dict[str, Any] = dict(
                contract=contract,
                date=date.isoformat(),
                query_type=query_type,
                timeout=_TICKS_API_TIMEOUT_MS,
            )
            if time_start is not None:
                kwargs["time_start"] = time_start.isoformat()
            if time_end is not None:
                kwargs["time_end"] = time_end.isoformat()
            return api.ticks(**kwargs)
        except Exception as e:
            last_exc = e
            if attempt >= _TICK_FETCH_MAX_ATTEMPTS or not _is_transient_tick_fetch_error(e):
                raise
            logger.warning(
                "抓取 %s %s 逾時 (attempt %d/%d)，%ss 後重試: %s",
                getattr(contract, "code", contract),
                date,
                attempt,
                _TICK_FETCH_MAX_ATTEMPTS,
                _TICK_FETCH_RETRY_SLEEP_SEC,
                e,
            )
            time.sleep(_TICK_FETCH_RETRY_SLEEP_SEC)
    assert last_exc is not None
    raise last_exc


def fetch_calendar_day_ticks(
    api: Any,
    contract: Any,
    date: datetime.date,
    *,
    simulation: bool = False,
) -> List[ReplayTick]:
    """Fetch AllDay for ``date`` and ``date+1``, keep only ``tick.date == date``.

    Shioaji AllDay(D) includes prior-evening ticks (excluded here). Same-day night
    ticks (15:00+) appear in AllDay(D+1); fetch D+1 only when that query date is
    not in the future relative to Taipei today.
    """
    del simulation  # historical ticks decode identically; kept for call-site parity
    import shioaji as sj

    query_type = sj.TicksQueryType.AllDay
    by_dt: dict[datetime.datetime, ReplayTick] = {}
    for query_date in (date, date + datetime.timedelta(days=1)):
        if query_date > _taipei_today():
            continue
        raw = _call_ticks_api(api, contract, query_date, query_type=query_type)
        for tick in _raw_ticks_to_replay(raw):
            if tick.datetime.date() == date:
                by_dt[tick.datetime] = tick
    return sorted(by_dt.values(), key=lambda t: t.datetime)


def fetch_ticks_for_date(
    api: Any,
    contract: Any,
    date: datetime.date,
    *,
    time_start: datetime.time | None = DEFAULT_TICK_RANGE_START,
    time_end: datetime.time | None = DEFAULT_TICK_RANGE_END,
    simulation: bool = False,
) -> List[ReplayTick]:
    """呼叫 api.ticks 取單日 tick，回傳依時間排序的 ReplayTick。

    AllDay（``time_start``/``time_end`` 皆 None）時改走 ``fetch_calendar_day_ticks``：
    檔案 ``{code}_{D}.csv`` 只含曆日 D 的 ticks（不含前一晚夜盤）。
    """
    if time_start is None and time_end is None:
        return fetch_calendar_day_ticks(
            api, contract, date, simulation=simulation
        )

    import shioaji as sj

    query_type = sj.TicksQueryType.RangeTime
    raw = _call_ticks_api(
        api,
        contract,
        date,
        query_type=query_type,
        time_start=time_start,
        time_end=time_end,
    )
    ticks = _raw_ticks_to_replay(raw)
    return [t for t in ticks if t.datetime.date() == date]


def _tick_in_window(
    tick: ReplayTick,
    time_start: datetime.time | None,
    time_end: datetime.time | None,
) -> bool:
    if time_start is None and time_end is None:
        return True
    t = tick.datetime.time()
    if time_start is not None and t < time_start:
        return False
    if time_end is not None and t > time_end:
        return False
    return True


def _window_needs_fetch(
    ticks: Sequence[ReplayTick],
    time_start: datetime.time | None,
    time_end: datetime.time | None,
) -> bool:
    """True when cached ticks do not span the requested session window."""
    if time_start is None and time_end is None:
        return False
    in_window = [t for t in ticks if _tick_in_window(t, time_start, time_end)]
    if not in_window:
        return True
    earliest = min(t.datetime.time() for t in in_window)
    latest = max(t.datetime.time() for t in in_window)
    tol = datetime.timedelta(minutes=_WINDOW_EDGE_TOLERANCE_MIN)
    if (
        time_start is not None
        and datetime.datetime.combine(datetime.date.min, earliest)
        > datetime.datetime.combine(datetime.date.min, time_start) + tol
    ):
        return True
    if (
        time_end is not None
        and datetime.datetime.combine(datetime.date.min, latest)
        < datetime.datetime.combine(datetime.date.min, time_end) - tol
    ):
        return True
    ordered = sorted(in_window, key=lambda t: t.datetime)
    for prev, cur in zip(ordered, ordered[1:]):
        if cur.datetime - prev.datetime > datetime.timedelta(minutes=_TICK_MAX_GAP_MIN):
            return True
    return False


def _all_day_needs_fetch(ticks: Sequence[ReplayTick], date: datetime.date) -> bool:
    """True when cache has no ticks for calendar day *date* (empty/missing → fetch)."""
    del date
    return not ticks


def tick_cache_satisfies_request(
    cache_dir: Path,
    code: str,
    date: datetime.date,
    *,
    time_start: datetime.time | None,
    time_end: datetime.time | None,
    simulation: bool = False,
) -> bool:
    """Whether on-disk tick cache meets the requested backfill window."""
    if not tick_cache_files_exist(cache_dir, code, date):
        return False
    ticks = load_merged_tick_cache(cache_dir, code, date)
    if time_start is None and time_end is None:
        return not _all_day_needs_fetch(ticks, date)
    return not _window_needs_fetch(ticks, time_start, time_end)


def merge_ticks(
    existing: Iterable[ReplayTick],
    fetched: Iterable[ReplayTick],
    *,
    time_start: datetime.time | None,
    time_end: datetime.time | None,
    replace_window: bool,
) -> List[ReplayTick]:
    """Combine cache with a new fetch. ``fetched`` wins on duplicate ``datetime``."""
    if replace_window and time_start is None and time_end is None:
        return sorted(fetched, key=lambda t: t.datetime)

    by_dt: dict[datetime.datetime, ReplayTick] = {}
    for tick in existing:
        if replace_window and _tick_in_window(tick, time_start, time_end):
            continue
        by_dt[tick.datetime] = tick
    for tick in fetched:
        by_dt[tick.datetime] = tick
    return sorted(by_dt.values(), key=lambda t: t.datetime)


def cache_path(cache_dir: Path, code: str, date: datetime.date) -> Path:
    return Path(cache_dir) / f"{code}_{date.isoformat()}.csv"


def resolve_tick_cache_path(
    cache_dir: Path, code: str, date: datetime.date
) -> Optional[Path]:
    """Return on-disk tick cache path when plain CSV exists."""
    plain = cache_path(cache_dir, code, date)
    if plain.is_file():
        return plain
    return None


def tick_cache_files_exist(cache_dir: Path, code: str, date: datetime.date) -> bool:
    return cache_path(cache_dir, code, date).is_file()


def load_merged_tick_cache(
    cache_dir: Path, code: str, date: datetime.date
) -> List[ReplayTick]:
    """Load ticks from plain CSV when present."""
    plain = cache_path(cache_dir, code, date)
    if plain.is_file():
        return load_ticks_csv(plain)
    return []


def save_ticks_csv(ticks: Iterable[ReplayTick], path: Path) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    count = 0
    try:
        with tmp.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
            writer.writeheader()
            for t in ticks:
                writer.writerow(
                    {
                        "datetime": t.datetime.isoformat(),
                        "close": t.close,
                        "volume": t.volume,
                        "bid_price": t.bid_price,
                        "ask_price": t.ask_price,
                        "tick_type": t.tick_type,
                    }
                )
                count += 1
        tmp.replace(path)
    except Exception:
        if tmp.is_file():
            tmp.unlink(missing_ok=True)
        raise
    return count


def commit_ticks_cache(
    cache_dir: Path,
    code: str,
    date: datetime.date,
    ticks: Iterable[ReplayTick],
) -> tuple[Path, int]:
    """Atomically write plain CSV for the trade day."""
    path = cache_path(cache_dir, code, date)
    n = save_ticks_csv(ticks, path)
    return path, n


def load_ticks_csv(path: Path) -> List[ReplayTick]:
    ticks: List[ReplayTick] = []
    with Path(path).open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            ticks.append(
                ReplayTick(
                    datetime=datetime.datetime.fromisoformat(row["datetime"]),
                    close=row["close"],
                    volume=int(row["volume"]),
                    tick_type=int(row["tick_type"]),
                    bid_price=float(row["bid_price"]),
                    ask_price=float(row["ask_price"]),
                )
            )
    return ticks


def _log_usage(api: Any, context: str) -> None:
    try:
        usage = api.usage()
    except Exception as e:
        logger.warning("usage 查詢失敗 (%s): %s", context, e)
        return
    logger.info(
        "API usage [%s] | bytes=%s limit=%s remaining=%s",
        context,
        usage.bytes,
        usage.limit_bytes,
        usage.remaining_bytes,
    )
    if usage.limit_bytes > 0 and usage.remaining_bytes < usage.limit_bytes * 0.1:
        logger.warning(
            "API 流量剩餘 < 10%% | remaining=%s limit=%s 建議暫停抓取",
            usage.remaining_bytes,
            usage.limit_bytes,
        )


def download_and_cache(
    api: Any,
    contract: Any,
    dates: Iterable[datetime.date],
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    overwrite: bool = False,
    time_start: datetime.time | None = DEFAULT_TICK_RANGE_START,
    time_end: datetime.time | None = DEFAULT_TICK_RANGE_END,
    simulation: bool = False,
) -> List[Path]:
    """逐日抓取並落地 plain CSV 快取；支援 RangeTime 缺口合併。"""
    code = getattr(contract, "code", str(contract))
    written: List[Path] = []
    all_day = time_start is None and time_end is None
    _log_usage(api, "download_start")
    for date in dates:
        path = cache_path(cache_dir, code, date)
        cache_exists = tick_cache_files_exist(cache_dir, code, date)
        existing_ticks: List[ReplayTick] = (
            load_merged_tick_cache(cache_dir, code, date) if cache_exists else []
        )

        needs_fetch = (
            not cache_exists
            or overwrite
            or (
                _all_day_needs_fetch(existing_ticks, date)
                if all_day
                else _window_needs_fetch(existing_ticks, time_start, time_end)
            )
        )

        if cache_exists and not needs_fetch:
            existing_path = resolve_tick_cache_path(cache_dir, code, date)
            logger.info(
                "視窗已覆蓋，跳過 %s",
                existing_path.name if existing_path is not None else path.name,
            )
            written.append(existing_path or path)
            continue

        try:
            if all_day:
                fetched = fetch_calendar_day_ticks(
                    api, contract, date, simulation=simulation
                )
            else:
                fetched = fetch_ticks_for_date(
                    api,
                    contract,
                    date,
                    time_start=time_start,
                    time_end=time_end,
                    simulation=simulation,
                )
        except Exception as e:
            logger.warning("抓取 %s %s 失敗: %s", code, date, e)
            continue

        if all_day and not fetched:
            logger.info(
                "skip %s %s: no ticks (non-trading or empty)",
                code,
                date.isoformat(),
            )
            continue

        if existing_ticks and (not all_day or not overwrite):
            merged = merge_ticks(
                existing_ticks,
                fetched,
                time_start=time_start,
                time_end=time_end,
                replace_window=overwrite,
            )
            action = "合併" if not overwrite else "覆寫視窗合併"
            logger.info(
                "%s %s | existing=%d fetched=%d → %d ticks",
                action,
                date.isoformat(),
                len(existing_ticks),
                len(fetched),
                len(merged),
            )
            ticks = merged
        else:
            ticks = fetched

        out_path, n = commit_ticks_cache(cache_dir, code, date, ticks)
        logger.info("已快取 %s | %d ticks → %s", date.isoformat(), n, out_path.name)
        written.append(out_path)
    _log_usage(api, "download_end")
    return written


def iter_replay_ticks(
    code: str,
    dates: Iterable[datetime.date],
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> Iterator[ReplayTick]:
    """依日期序讀取本地快取並逐筆 yield（跨日 tick 連續輸出，驅動 P0-8 跨日重置）。"""
    for date in dates:
        if not tick_cache_files_exist(cache_dir, code, date):
            logger.warning(
                "快取缺檔，略過 %s_%s",
                code,
                date.isoformat(),
            )
            continue
        for tick in load_merged_tick_cache(cache_dir, code, date):
            yield tick


def date_range(start: datetime.date, end: datetime.date) -> List[datetime.date]:
    days = (end - start).days
    return [start + datetime.timedelta(days=i) for i in range(days + 1)]


def _tick_cache_filename_date(name: str, code: str) -> datetime.date | None:
    """Parse trade date from ``{code}_YYYY-MM-DD.csv``; skip kbar mirror files."""
    if "_kbars_" in name:
        return None
    if not name.endswith(".csv") or name.endswith(".csv.gz"):
        return None
    stem = name[: -len(".csv")]
    prefix = f"{code}_"
    if not stem.startswith(prefix):
        return None
    try:
        return datetime.date.fromisoformat(stem[len(prefix) :])
    except ValueError:
        return None


def list_cached_tick_dates(
    code: str,
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
    *,
    start: datetime.date | None = None,
    end: datetime.date | None = None,
) -> List[datetime.date]:
    """Return sorted trade dates with on-disk plain CSV tick cache for *code*."""
    cache_dir = Path(cache_dir)
    if not cache_dir.is_dir():
        return []

    seen: set[datetime.date] = set()
    dates: list[datetime.date] = []
    for path in cache_dir.iterdir():
        if not path.is_file():
            continue
        day = _tick_cache_filename_date(path.name, code)
        if day is None:
            continue
        if start is not None and day < start:
            continue
        if end is not None and day > end:
            continue
        if day not in seen:
            seen.add(day)
            dates.append(day)
    return sorted(dates)


def resolve_tick_cache_dates(
    *,
    explicit: Sequence[str] | None,
    from_cache: bool,
    code: str,
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
    start: datetime.date | None = None,
    end: datetime.date | None = None,
) -> List[datetime.date]:
    """Resolve CLI ``--dates`` or ``--dates-from-cache`` to a sorted date list."""
    if from_cache:
        dates = list_cached_tick_dates(code, cache_dir, start=start, end=end)
        if not dates:
            span = ""
            if start is not None or end is not None:
                span = f", range={start}..{end}"
            raise ValueError(
                f"tick_cache 無 {code} 快取（dir={cache_dir}{span}）"
            )
        return dates
    if not explicit:
        raise ValueError("需要 --dates 或 --dates-from-cache")
    return parse_explicit_iso_dates(explicit)


def parse_explicit_iso_dates(parts: Sequence[str]) -> List[datetime.date]:
    """Parse ``YYYY-MM-DD`` strings; raise ``ValueError`` with a clear CLI message."""
    if not parts:
        raise ValueError("至少需一個日期（YYYY-MM-DD）")
    out: list[datetime.date] = []
    for raw in parts:
        try:
            out.append(datetime.date.fromisoformat(raw))
        except ValueError as exc:
            raise ValueError(f"無效的日期: {raw!r}（需 YYYY-MM-DD）") from exc
    return out


def split_csv_dates(raw: str) -> List[str]:
    """Split comma-separated CLI date tokens (non-empty)."""
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        raise ValueError("至少需一個日期（逗號分隔 YYYY-MM-DD）")
    return parts


def parse_optional_iso_date(value: str, *, label: str) -> datetime.date | None:
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"無效的 {label}: {value!r}（需 YYYY-MM-DD）") from exc


def parse_cli_cache_date_range(
    *,
    from_date: str,
    to_date: str,
    dates_from_cache: bool,
) -> tuple[datetime.date | None, datetime.date | None]:
    """Validate optional ``--from-date`` / ``--to-date`` for cache-driven CLIs."""
    if (from_date or to_date) and not dates_from_cache:
        raise ValueError("--from-date/--to-date 僅能與 --dates-from-cache 併用")
    start = parse_optional_iso_date(from_date, label="--from-date") if from_date else None
    end = parse_optional_iso_date(to_date, label="--to-date") if to_date else None
    if start is not None and end is not None and start > end:
        raise ValueError(f"--from-date ({start}) 不可晚於 --to-date ({end})")
    return start, end


def resolve_cli_tick_cache_dates(
    *,
    explicit: Sequence[str] | None,
    from_cache: bool,
    code: str,
    cache_dir: Path | str = DEFAULT_CACHE_DIR,
    from_date: str = "",
    to_date: str = "",
) -> List[datetime.date]:
    """Parse CLI date flags and resolve tick_cache trade dates."""
    start, end = parse_cli_cache_date_range(
        from_date=from_date,
        to_date=to_date,
        dates_from_cache=from_cache,
    )
    return resolve_tick_cache_dates(
        explicit=explicit,
        from_cache=from_cache,
        code=code,
        cache_dir=cache_dir,
        start=start,
        end=end,
    )
