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
import gzip
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, IO, Iterable, Iterator, List, Optional, Sequence

logger = logging.getLogger(__name__)

from storage.cache_paths import DEFAULT_CACHE_DIR, DEFAULT_TICK_CACHE_DIR

TAIWAN_TZ = datetime.timezone(datetime.timedelta(hours=8))
UTC = datetime.timezone.utc
DEFAULT_TICK_RANGE_START = datetime.time(8, 45, 0)
DEFAULT_TICK_RANGE_END = datetime.time(13, 45, 0)
_WINDOW_EDGE_TOLERANCE_MIN = 1
_TICK_MAX_GAP_MIN = 30

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


def _ns_to_taipei_naive(ts_ns: int) -> datetime.datetime:
    """Shioaji ts 為奈秒 epoch；轉成台北 naive local（與線上 tick.datetime 同構）。"""
    aware = datetime.datetime.fromtimestamp(ts_ns / 1_000_000_000, TAIWAN_TZ)
    return aware.replace(tzinfo=None)


def shioaji_ts_from_ns(ts_ns: int, *, simulation: bool) -> datetime.datetime:
    """Convert Shioaji ``ts`` nanoseconds to naive exchange wall clock.

    Simulation API (ticks + kbars): wall clock encoded as UTC epoch (no +8).
    Production API: true UTC epoch → Taipei naive via ``_ns_to_taipei_naive``.
    """
    if simulation:
        return datetime.datetime.fromtimestamp(
            ts_ns / 1_000_000_000, UTC
        ).replace(tzinfo=None)
    return _ns_to_taipei_naive(ts_ns)


def _is_transient_tick_fetch_error(exc: BaseException) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    msg = str(exc)
    return "Timeout" in msg or "timeout" in msg


def fetch_ticks_for_date(
    api: Any,
    contract: Any,
    date: datetime.date,
    *,
    time_start: datetime.time | None = DEFAULT_TICK_RANGE_START,
    time_end: datetime.time | None = DEFAULT_TICK_RANGE_END,
    simulation: bool = False,
) -> List[ReplayTick]:
    """呼叫 api.ticks 取單日 tick，回傳依時間排序的 ReplayTick。"""
    import shioaji as sj

    query_type = (
        sj.TicksQueryType.RangeTime
        if time_start is not None or time_end is not None
        else sj.TicksQueryType.AllDay
    )
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
            raw = api.ticks(**kwargs)
            break
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
    else:
        assert last_exc is not None
        raise last_exc
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
                datetime=shioaji_ts_from_ns(int(ts[i]), simulation=simulation),
                close=str(close[i]),
                volume=int(volume[i]),
                tick_type=int(tick_type[i]) if i < len(tick_type) else 0,
                bid_price=float(bid[i]) if i < len(bid) else 0.0,
                ask_price=float(ask[i]) if i < len(ask) else 0.0,
            )
        )
    ticks.sort(key=lambda t: t.datetime)
    return ticks


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


def _add_hours_to_time(t: datetime.time, hours: int) -> datetime.time:
    combined = datetime.datetime.combine(datetime.date.min, t) + datetime.timedelta(
        hours=hours
    )
    return combined.time()


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


def _all_day_needs_fetch(ticks: Sequence[ReplayTick]) -> bool:
    """True when cache is empty, day session incomplete, or only session-filtered rows."""
    if not ticks:
        return True
    if _window_needs_fetch(ticks, DEFAULT_TICK_RANGE_START, DEFAULT_TICK_RANGE_END):
        return True
    return all(
        _tick_in_window(t, DEFAULT_TICK_RANGE_START, DEFAULT_TICK_RANGE_END)
        for t in ticks
    )


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
    if simulation and (time_start is not None or time_end is not None):
        ticks = _normalize_simulation_ticks_for_window(
            ticks, time_start=time_start, time_end=time_end
        )
    if time_start is None and time_end is None:
        return not _all_day_needs_fetch(ticks)
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


def _purge_stale_tick_gz(cache_dir: Path, code: str, date: datetime.date) -> None:
    gz = cache_gz_path(cache_dir, code, date)
    if gz.is_file():
        gz.unlink()
        logger.info("已移除過期 gzip 快取 %s（改寫 plain CSV）", gz.name)


def _purge_stale_tick_gz_with_retry(
    cache_dir: Path, code: str, date: datetime.date
) -> None:
    for attempt in range(1, 3):
        try:
            _purge_stale_tick_gz(cache_dir, code, date)
            return
        except OSError as e:
            if attempt >= 2:
                logger.warning(
                    "移除過期 gzip 失敗（plain CSV 已落地）%s: %s",
                    cache_gz_path(cache_dir, code, date).name,
                    e,
                )
                return
            logger.warning("移除 gzip 重試 (%d/2): %s", attempt, e)


def _tick_at_datetime(
    ticks: Sequence[ReplayTick], dt: datetime.datetime
) -> bool:
    return any(tick.datetime == dt for tick in ticks)


def _is_legacy_plus8h_tick_candidate(
    tick: ReplayTick,
    *,
    time_start: datetime.time | None,
    time_end: datetime.time | None,
    all_ticks: Sequence[ReplayTick],
) -> bool:
    """Detect misplaced day-session rows stored with the old +8h simulation offset."""
    if time_start is None or time_end is None:
        return False
    if _tick_in_window(tick, time_start, time_end):
        return False
    minus_8h_dt = tick.datetime - datetime.timedelta(hours=8)
    shifted_probe = ReplayTick(
        datetime=minus_8h_dt,
        close=tick.close,
        volume=tick.volume,
        tick_type=tick.tick_type,
        bid_price=tick.bid_price,
        ask_price=tick.ask_price,
    )
    if not _tick_in_window(shifted_probe, time_start, time_end):
        return False

    legacy_band_start = _add_hours_to_time(time_start, 8)
    legacy_band_end = _add_hours_to_time(time_end, 8)
    tick_time = tick.datetime.time()
    if not (legacy_band_start <= tick_time <= legacy_band_end):
        return False

    day_ticks = [t for t in all_ticks if _tick_in_window(t, time_start, time_end)]
    if not day_ticks:
        return True

    ambiguous_cutoff = datetime.time(18, 0)
    if tick_time < ambiguous_cutoff:
        return False

    if _tick_at_datetime(day_ticks, minus_8h_dt):
        return False
    return True


def _normalize_simulation_ticks_for_window(
    ticks: Iterable[ReplayTick],
    *,
    time_start: datetime.time | None,
    time_end: datetime.time | None,
) -> List[ReplayTick]:
    """Shift legacy (+8h) simulation rows back when they clearly belong to the day window."""
    if time_start is None and time_end is None:
        return list(ticks)
    tick_list = list(ticks)
    shifted: List[ReplayTick] = []
    for t in tick_list:
        minus_8h_dt = t.datetime - datetime.timedelta(hours=8)
        if _is_legacy_plus8h_tick_candidate(
            t,
            time_start=time_start,
            time_end=time_end,
            all_ticks=tick_list,
        ):
            shifted.append(
                ReplayTick(
                    datetime=minus_8h_dt,
                    close=t.close,
                    volume=t.volume,
                    tick_type=t.tick_type,
                    bid_price=t.bid_price,
                    ask_price=t.ask_price,
                )
            )
            logger.info(
                "simulation 舊 tick 時間校正 %s -> %s",
                t.datetime.isoformat(),
                minus_8h_dt.isoformat(),
            )
        else:
            shifted.append(t)
    return shifted


def cache_path(cache_dir: Path, code: str, date: datetime.date) -> Path:
    return Path(cache_dir) / f"{code}_{date.isoformat()}.csv"


def cache_gz_path(cache_dir: Path, code: str, date: datetime.date) -> Path:
    return Path(cache_dir) / f"{code}_{date.isoformat()}.csv.gz"


def resolve_tick_cache_path(
    cache_dir: Path, code: str, date: datetime.date
) -> Optional[Path]:
    """Return canonical on-disk tick cache path when any variant exists.

    When both plain CSV and gzip exist, plain is preferred (backfill write target).
    Callers needing full content should use ``load_merged_tick_cache``.
    """
    plain = cache_path(cache_dir, code, date)
    gz = cache_gz_path(cache_dir, code, date)
    if plain.is_file():
        return plain
    if gz.is_file():
        return gz
    return None


def tick_cache_files_exist(cache_dir: Path, code: str, date: datetime.date) -> bool:
    plain = cache_path(cache_dir, code, date)
    gz = cache_gz_path(cache_dir, code, date)
    return plain.is_file() or gz.is_file()


def load_merged_tick_cache(
    cache_dir: Path, code: str, date: datetime.date
) -> List[ReplayTick]:
    """Load ticks from plain CSV and/or gzip, unioning both when present."""
    plain = cache_path(cache_dir, code, date)
    gz = cache_gz_path(cache_dir, code, date)
    plain_ticks = load_ticks_csv(plain) if plain.is_file() else []
    gz_ticks = load_ticks_csv(gz) if gz.is_file() else []
    if plain_ticks and gz_ticks:
        return merge_ticks(
            gz_ticks,
            plain_ticks,
            time_start=None,
            time_end=None,
            replace_window=False,
        )
    return plain_ticks or gz_ticks


def _open_tick_csv_reader(path: Path) -> IO[str]:
    path = Path(path)
    if path.suffix == ".gz" or path.name.endswith(".csv.gz"):
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return path.open("r", encoding="utf-8", newline="")


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
    """Atomically write plain CSV, then remove stale gzip for the same day."""
    path = cache_path(cache_dir, code, date)
    n = save_ticks_csv(ticks, path)
    _purge_stale_tick_gz_with_retry(cache_dir, code, date)
    return path, n


def load_ticks_csv(path: Path) -> List[ReplayTick]:
    ticks: List[ReplayTick] = []
    with _open_tick_csv_reader(Path(path)) as f:
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
    """逐日抓取並落地快取；支援 RangeTime 缺口合併與 gzip 失效處理。"""
    code = getattr(contract, "code", str(contract))
    written: List[Path] = []
    all_day = time_start is None and time_end is None
    _log_usage(api, "download_start")
    for date in dates:
        path = cache_path(cache_dir, code, date)
        cache_exists = tick_cache_files_exist(cache_dir, code, date)
        raw_existing_ticks: List[ReplayTick] = (
            load_merged_tick_cache(cache_dir, code, date) if cache_exists else []
        )
        existing_ticks = raw_existing_ticks
        if (
            simulation
            and existing_ticks
            and (time_start is not None or time_end is not None)
        ):
            existing_ticks = _normalize_simulation_ticks_for_window(
                existing_ticks,
                time_start=time_start,
                time_end=time_end,
            )

        needs_fetch = (
            not cache_exists
            or overwrite
            or (
                _all_day_needs_fetch(existing_ticks)
                if all_day
                else _window_needs_fetch(existing_ticks, time_start, time_end)
            )
        )

        if cache_exists and not needs_fetch:
            if existing_ticks != raw_existing_ticks:
                out_path, n = commit_ticks_cache(
                    cache_dir, code, date, existing_ticks
                )
                logger.info(
                    "simulation 舊 tick 時間已校正落地 %s | %d ticks",
                    out_path.name,
                    n,
                )
                written.append(out_path)
            else:
                existing_path = resolve_tick_cache_path(cache_dir, code, date)
                logger.info(
                    "視窗已覆蓋，跳過 %s",
                    existing_path.name if existing_path is not None else path.name,
                )
                written.append(existing_path or path)
            continue

        try:
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
