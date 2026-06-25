"""K-bar cache I/O for backtest ATR warmup."""

from __future__ import annotations

import csv
import datetime
import logging
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence

from storage.tick_loader import (
    DEFAULT_CACHE_DIR,
    DEFAULT_TICK_RANGE_END,
    DEFAULT_TICK_RANGE_START,
    _log_usage,
    _open_tick_csv_reader,
    date_range,
    shioaji_ts_from_ns,
)

logger = logging.getLogger(__name__)

_KBARS_API_TIMEOUT_MS = 30_000
_KBARS_CSV_FIELDS = ["ts", "Open", "High", "Low", "Close", "Volume"]
_WINDOW_EDGE_TOLERANCE_MIN = 1
_KBAR_MAX_GAP_MIN = 10


@dataclass
class KBarRecord:
    ts: datetime.datetime
    Open: float
    High: float
    Low: float
    Close: float
    Volume: int


def kbar_ts_from_ns(ts_ns: int, *, simulation: bool) -> datetime.datetime:
    """Convert Shioaji ``kbars.ts`` (nanoseconds) to naive exchange-local time."""
    return shioaji_ts_from_ns(ts_ns, simulation=simulation)


def _filter_bars_by_time(
    bars: List[KBarRecord],
    time_start: datetime.time | None,
    time_end: datetime.time | None,
) -> List[KBarRecord]:
    """Keep bars whose ``ts.time()`` falls in the inclusive session window."""
    if time_start is None and time_end is None:
        return bars
    filtered: List[KBarRecord] = []
    for bar in bars:
        t = bar.ts.time()
        if time_start is not None and t < time_start:
            continue
        if time_end is not None and t > time_end:
            continue
        filtered.append(bar)
    return filtered


def _bar_in_window(
    bar: KBarRecord,
    time_start: datetime.time | None,
    time_end: datetime.time | None,
) -> bool:
    if time_start is None and time_end is None:
        return True
    t = bar.ts.time()
    if time_start is not None and t < time_start:
        return False
    if time_end is not None and t > time_end:
        return False
    return True


def _kbar_window_needs_fetch(
    bars: Sequence[KBarRecord],
    time_start: datetime.time | None,
    time_end: datetime.time | None,
) -> bool:
    if time_start is None and time_end is None:
        return False
    in_window = [b for b in bars if _bar_in_window(b, time_start, time_end)]
    if not in_window:
        return True
    earliest = min(b.ts.time() for b in in_window)
    latest = max(b.ts.time() for b in in_window)
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
    ordered = sorted(in_window, key=lambda b: b.ts)
    for prev, cur in zip(ordered, ordered[1:]):
        if cur.ts - prev.ts > datetime.timedelta(minutes=_KBAR_MAX_GAP_MIN):
            return True
    return False


def _all_day_kbar_needs_fetch(bars: Sequence[KBarRecord]) -> bool:
    """True when cache is empty, day session incomplete, or only session-filtered rows."""
    if not bars:
        return True
    if _kbar_window_needs_fetch(bars, DEFAULT_TICK_RANGE_START, DEFAULT_TICK_RANGE_END):
        return True
    return all(
        _bar_in_window(b, DEFAULT_TICK_RANGE_START, DEFAULT_TICK_RANGE_END)
        for b in bars
    )


def kbar_cache_satisfies_request(
    cache_dir: Path,
    code: str,
    date: datetime.date,
    *,
    time_start: datetime.time | None,
    time_end: datetime.time | None,
) -> bool:
    """Whether on-disk kbar cache meets the requested backfill window."""
    path = resolve_kbars_cache_path(cache_dir, code, date)
    if path is None:
        return False
    bars = load_kbars_csv(path)
    if time_start is None and time_end is None:
        return not _all_day_kbar_needs_fetch(bars)
    return not _kbar_window_needs_fetch(bars, time_start, time_end)


def merge_kbars(
    existing: Iterable[KBarRecord],
    fetched: Iterable[KBarRecord],
    *,
    time_start: datetime.time | None,
    time_end: datetime.time | None,
    replace_window: bool,
) -> List[KBarRecord]:
    if replace_window and time_start is None and time_end is None:
        return sorted(fetched, key=lambda b: b.ts)

    by_ts: dict[datetime.datetime, KBarRecord] = {}
    for bar in existing:
        if replace_window and _bar_in_window(bar, time_start, time_end):
            continue
        by_ts[bar.ts] = bar
    for bar in fetched:
        by_ts[bar.ts] = bar
    return sorted(by_ts.values(), key=lambda b: b.ts)


def _default_simulation_mode() -> bool:
    try:
        import config as app_config

        return bool(app_config.SIMULATION)
    except Exception:
        return False


def kbars_cache_path(cache_dir: Path, code: str, date: datetime.date) -> Path:
    return Path(cache_dir) / f"{code}_kbars_{date.isoformat()}.csv"


def kbars_cache_gz_path(cache_dir: Path, code: str, date: datetime.date) -> Path:
    return Path(cache_dir) / f"{code}_kbars_{date.isoformat()}.csv.gz"


def resolve_kbars_cache_path(
    cache_dir: Path, code: str, date: datetime.date
) -> Path | None:
    """Return on-disk kbar cache (plain preferred over gzip mirror)."""
    plain = kbars_cache_path(cache_dir, code, date)
    gz = kbars_cache_gz_path(cache_dir, code, date)
    if plain.is_file():
        return plain
    if gz.is_file():
        return gz
    return None


def mirror_kbar_cache_file(
    *,
    code: str,
    date: datetime.date,
    source_dir: Path,
    dest_dir: Path,
    overwrite: bool,
) -> Path | None:
    """Copy ``{code}_kbars_{date}.csv`` from source_dir to dest_dir if present."""
    src = kbars_cache_path(source_dir, code, date)
    if not src.is_file():
        return None
    dest = kbars_cache_path(dest_dir, code, date)
    if dest.is_file() and not overwrite:
        logger.info("K 線 mirror 已存在，跳過 %s", dest.name)
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    logger.info("K 線 mirror %s → %s", src.name, dest.name)
    return dest


def save_kbars_csv(bars: Iterable[KBarRecord], path: Path) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    count = 0
    try:
        with tmp.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_KBARS_CSV_FIELDS)
            writer.writeheader()
            for bar in bars:
                writer.writerow(
                    {
                        "ts": bar.ts.isoformat(),
                        "Open": bar.Open,
                        "High": bar.High,
                        "Low": bar.Low,
                        "Close": bar.Close,
                        "Volume": bar.Volume,
                    }
                )
                count += 1
        tmp.replace(path)
    except Exception:
        if tmp.is_file():
            tmp.unlink(missing_ok=True)
        raise
    return count


def load_kbars_csv(path: Path) -> List[KBarRecord]:
    bars: List[KBarRecord] = []
    with _open_tick_csv_reader(Path(path)) as f:
        for row in csv.DictReader(f):
            bars.append(
                KBarRecord(
                    ts=datetime.datetime.fromisoformat(row["ts"]),
                    Open=float(row["Open"]),
                    High=float(row["High"]),
                    Low=float(row["Low"]),
                    Close=float(row["Close"]),
                    Volume=int(row["Volume"]),
                )
            )
    return dedupe_kbars(bars)


def dedupe_kbars(bars: Iterable[KBarRecord]) -> List[KBarRecord]:
    """Collapse duplicate ``ts`` rows (last wins)."""
    by_ts: dict[datetime.datetime, KBarRecord] = {}
    for bar in bars:
        by_ts[bar.ts] = bar
    return sorted(by_ts.values(), key=lambda b: b.ts)


def kbars_raw_to_records(
    raw: Any, *, simulation: bool | None = None
) -> List[KBarRecord]:
    sim = _default_simulation_mode() if simulation is None else simulation
    ts_list = list(raw.ts)
    opens = list(raw.Open)
    highs = list(raw.High)
    lows = list(raw.Low)
    closes = list(raw.Close)
    volumes = list(getattr(raw, "Volume", []) or [])
    bars: List[KBarRecord] = []
    for i in range(len(ts_list)):
        bars.append(
            KBarRecord(
                ts=kbar_ts_from_ns(int(ts_list[i]), simulation=sim),
                Open=float(opens[i]),
                High=float(highs[i]),
                Low=float(lows[i]),
                Close=float(closes[i]),
                Volume=int(volumes[i]) if i < len(volumes) else 0,
            )
        )
    bars.sort(key=lambda b: b.ts)
    return bars


def fetch_kbars_for_date(
    api: Any, contract: Any, date: datetime.date, *, simulation: bool | None = None
) -> List[KBarRecord]:
    """呼叫 api.kbars 取單日 1 分 K，回傳依時間排序的 KBarRecord。"""
    raw = api.kbars(
        contract=contract,
        start=date.isoformat(),
        end=date.isoformat(),
        timeout=_KBARS_API_TIMEOUT_MS,
    )
    return kbars_raw_to_records(raw, simulation=simulation)


def download_and_cache_kbars(
    api: Any,
    contract: Any,
    dates: Iterable[datetime.date],
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    overwrite: bool = False,
    preload_dates: Optional[Iterable[datetime.date]] = None,
    simulation: bool | None = None,
    mirror_cache_dir: Path | None = None,
    pace_sec: float = 0.0,
    time_start: datetime.time | None = None,
    time_end: datetime.time | None = None,
) -> List[Path]:
    """逐日抓取 K 線並落地快取；preload_dates 供 ATR 熱身（6.5）預載前日/夜盤。

    ``mirror_cache_dir``：主快取寫入 ``cache_dir`` 後，可選複製到第二目錄（如 tick_cache）。
    ``simulation``：覆寫 kbar ``ts`` 解碼（預設讀 ``config.SIMULATION``）。
    ``time_start`` / ``time_end``：API 仍取整日，落地前依交易所時間裁切（backfill 對齊 tick 視窗）。
    """
    code = getattr(contract, "code", str(contract))
    all_dates: list[datetime.date] = []
    seen: set[datetime.date] = set()
    for group in (dates, preload_dates or ()):
        for date in group:
            if date not in seen:
                seen.add(date)
                all_dates.append(date)
    written: List[Path] = []
    all_day = time_start is None and time_end is None
    _log_usage(api, "kbars_download_start")
    for date in all_dates:
        path = kbars_cache_path(cache_dir, code, date)
        cached_path = resolve_kbars_cache_path(cache_dir, code, date)
        existing_bars: List[KBarRecord] = (
            load_kbars_csv(cached_path) if cached_path is not None else []
        )
        needs_fetch = (
            cached_path is None
            or overwrite
            or (
                _all_day_kbar_needs_fetch(existing_bars)
                if all_day
                else _kbar_window_needs_fetch(existing_bars, time_start, time_end)
            )
        )
        if cached_path is not None and not needs_fetch:
            logger.info("K 線視窗已覆蓋，跳過 %s", cached_path.name)
            written.append(cached_path)
            if mirror_cache_dir is not None:
                mirrored = mirror_kbar_cache_file(
                    code=code,
                    date=date,
                    source_dir=cache_dir,
                    dest_dir=mirror_cache_dir,
                    overwrite=overwrite,
                )
                if mirrored is not None:
                    written.append(mirrored)
            continue
        try:
            bars = fetch_kbars_for_date(api, contract, date, simulation=simulation)
            bars = _filter_bars_by_time(bars, time_start, time_end)
        except Exception as e:
            logger.warning("抓取 K 線 %s %s 失敗: %s", code, date, e)
            continue

        if existing_bars and (not all_day or not overwrite):
            bars = merge_kbars(
                existing_bars,
                bars,
                time_start=time_start,
                time_end=time_end,
                replace_window=overwrite,
            )
            logger.info(
                "K 線合併 %s | existing=%d fetched→merged=%d bars",
                date.isoformat(),
                len(existing_bars),
                len(bars),
            )

        n = save_kbars_csv(bars, path)
        logger.info("已快取 K 線 %s | %d bars → %s", date.isoformat(), n, path.name)
        written.append(path)
        if mirror_cache_dir is not None:
            mirrored = mirror_kbar_cache_file(
                code=code,
                date=date,
                source_dir=cache_dir,
                dest_dir=mirror_cache_dir,
                overwrite=overwrite,
            )
            if mirrored is not None:
                written.append(mirrored)
        if pace_sec > 0:
            time.sleep(pace_sec)
    _log_usage(api, "kbars_download_end")
    return written


def iter_kbars_in_range(
    code: str,
    start: datetime.date,
    end: datetime.date,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> List[KBarRecord]:
    """讀取 [start, end] 日曆日範圍內所有已快取 K 線（缺檔略過）。"""
    bars: List[KBarRecord] = []
    for date in date_range(start, end):
        path = resolve_kbars_cache_path(cache_dir, code, date)
        if path is None:
            continue
        bars.extend(load_kbars_csv(path))
    bars.sort(key=lambda b: b.ts)
    return bars
