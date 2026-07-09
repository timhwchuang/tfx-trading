"""Multi-day 15m timeline with point-in-time 4h/1h/5m context (no lookahead)."""

from __future__ import annotations

import bisect
import datetime
from pathlib import Path
from typing import Any, Literal

from storage.cache_paths import DEFAULT_TICK_CACHE_DIR
from storage.kbar_loader import KBarRecord, iter_kbars_in_range
from storage.session_bar_cache import DAY_ANCHOR, yuanta_resample, sma

H4_LOOKBACK = 10
M5_TAIL = 6
_MA_HISTORY_START = datetime.date(2026, 1, 1)
_SCOPE = {"5m": "day", "1h": "both", "4h": "both", "15m": "both"}


def _bar_dict(b: KBarRecord) -> dict[str, Any]:
    return {
        "ts": b.ts.isoformat(),
        "O": round(float(b.Open), 1),
        "H": round(float(b.High), 1),
        "L": round(float(b.Low), 1),
        "C": round(float(b.Close), 1),
    }


def _mas_at(closes: list[float], periods: tuple[int, ...] = (20, 60)) -> dict[str, float | None]:
    return {f"ma{p}": (round(v, 1) if (v := sma(closes, p)) is not None else None) for p in periods}


def _ma_pad_start(start: datetime.datetime) -> datetime.date:
    return min(_MA_HISTORY_START, start.date() - datetime.timedelta(days=14))


def _resample_tf_range(
    code: str,
    start: datetime.datetime,
    end: datetime.datetime,
    minutes: int,
    scope: Literal["day", "night", "both"],
    *,
    cache_dir: Path,
    history_start: datetime.date | None = None,
) -> list[KBarRecord]:
    """Resample closed bars from disk 1m (avoids SessionBarCache TF trim)."""
    pad = history_start or _ma_pad_start(start)
    bars_1m = iter_kbars_in_range(code, pad, end.date(), cache_dir=cache_dir)
    bars_1m = [b for b in bars_1m if b.ts <= end]
    closed, _ = yuanta_resample(bars_1m, minutes, scope, end)
    return closed


def build_15m_timeline(
    *,
    start: datetime.datetime,
    end: datetime.datetime,
    code: str,
    cache_dir: Path = DEFAULT_TICK_CACHE_DIR,
    h4_lookback: int = H4_LOOKBACK,
    m5_tail: int = M5_TAIL,
) -> dict[str, Any]:
    """Each 15m bar in [start, end] with bisect-sliced HTF + recent 5m at bar close."""
    history_start = _ma_pad_start(start)
    series_15m = _resample_tf_range(
        code, start, end, 15, "both", cache_dir=cache_dir, history_start=history_start
    )
    series_15m = [b for b in series_15m if start <= b.ts <= end]

    h1_full = _resample_tf_range(
        code, start, end, 60, "both", cache_dir=cache_dir, history_start=history_start
    )
    h4_full = _resample_tf_range(
        code, start, end, 240, "both", cache_dir=cache_dir, history_start=history_start
    )
    m5_full = _resample_tf_range(
        code, start, end, 5, "day", cache_dir=cache_dir, history_start=history_start
    )

    h1_ts = [b.ts for b in h1_full]
    h4_ts = [b.ts for b in h4_full]
    m5_ts = [b.ts for b in m5_full]

    rows: list[dict[str, Any]] = []
    for bar in series_15m:
        t = bar.ts
        h1_end = bisect.bisect_right(h1_ts, t)
        h1_closes = [float(b.Close) for b in h1_full[:h1_end]]
        h4_end = bisect.bisect_right(h4_ts, t)
        h4_closes = [float(b.Close) for b in h4_full[:h4_end]]
        h4_slice = h4_full[max(0, h4_end - h4_lookback) : h4_end]
        m5_end = bisect.bisect_right(m5_ts, t)
        m5_same_day = [b for b in m5_full[:m5_end] if b.ts.date() == t.date()]
        m5_slice = m5_same_day[-m5_tail:]
        close = float(bar.Close)
        h1_m = _mas_at(h1_closes)
        h4_m = _mas_at(h4_closes)
        rows.append(
            {
                "m15": _bar_dict(bar),
                "m5_last": [_bar_dict(b) for b in m5_slice],
                "h1": h1_m,
                "h1_bars": h1_end,
                "h4": h4_m,
                "h4_bars": h4_end,
                "h4_last": [_bar_dict(b) for b in h4_slice],
                "price_vs_ma": _price_vs_ma(close, h1_m, h4_m),
            }
        )

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "ma_history_from": history_start.isoformat(),
        "n_15m": len(rows),
        "rows": rows,
    }


def _price_vs_ma(
    price: float,
    h1: dict[str, float | None],
    h4: dict[str, float | None],
) -> dict[str, str | None]:
    def _pos(p: float, ma: float | None) -> str | None:
        if ma is None:
            return None
        if p > ma:
            return "above"
        if p < ma:
            return "below"
        return "at"

    return {
        "h1_ma20": _pos(price, h1.get("ma20")),
        "h1_ma60": _pos(price, h1.get("ma60")),
        "h4_ma20": _pos(price, h4.get("ma20")),
        "h4_ma60": _pos(price, h4.get("ma60")),
    }