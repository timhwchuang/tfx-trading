"""Bar-path exit simulation for OSF long entries."""

from __future__ import annotations

import datetime
from typing import Any, Literal, Sequence

from reporting.volatility_baseline import atr_series_from_bars
from storage.kbar_loader import KBarRecord

ExitReason = Literal[
    "fvg_invalidate_15m",
    "sweep_invalidate_15m",
    "hard_stop_5m",
    "time_decay",
    "tp_session_high",
    "session_flatten",
]

DEFAULT_MIN_ATR = 25.0
ATR_PERIOD = 14
TIME_DECAY_BARS_5M = 12
SESSION_FLATTEN = datetime.time(13, 20)


def _atr_5m(bars_5m: Sequence[KBarRecord], idx: int) -> float:
    tuples = [
        (b.High, b.Low, b.Close, b.High - b.Low, float(b.Volume))
        for b in bars_5m[: idx + 1]
    ]
    series = atr_series_from_bars(tuples, period=ATR_PERIOD)
    if not series:
        return DEFAULT_MIN_ATR
    return max(float(series[-1]), DEFAULT_MIN_ATR)


def simulate_bar_structure_exit_long(
    *,
    entry_price: float,
    entry_ts: datetime.datetime,
    sweep_low: float,
    fvg_low: float,
    session_high: float,
    bars_5m: Sequence[KBarRecord],
    bars_15m: Sequence[KBarRecord],
    k_sl: float = 1.0,
) -> dict[str, Any]:
    """Walk 5m bars after entry; 15m invalidation checked on 15m closes."""
    after_5m = [b for b in bars_5m if b.ts > entry_ts]
    after_15m = [b for b in bars_15m if b.ts > entry_ts]
    if not after_5m:
        return {
            "gross_pnl": 0.0,
            "mfe": 0.0,
            "mae": 0.0,
            "hold_bars_5m": 0,
            "exit_reason": "session_flatten",
            "exit_price": entry_price,
            "exit_ts": int(entry_ts.timestamp()),
        }

    entry_idx = next(i for i, b in enumerate(bars_5m) if b.ts == entry_ts)
    mfe = 0.0
    mae = 0.0
    atr = _atr_5m(bars_5m, entry_idx)
    stop = entry_price - k_sl * atr
    idx_15m = 0
    for i, bar in enumerate(after_5m):
        mfe = max(mfe, float(bar.High) - entry_price)
        mae = max(mae, entry_price - float(bar.Low))
        while idx_15m < len(after_15m) and after_15m[idx_15m].ts <= bar.ts:
            b15 = after_15m[idx_15m]
            if float(b15.Close) < fvg_low:
                return _pack(
                    entry_price,
                    float(b15.Close),
                    b15.ts,
                    mfe,
                    mae,
                    i + 1,
                    "fvg_invalidate_15m",
                )
            if float(b15.Close) < sweep_low:
                return _pack(
                    entry_price,
                    float(b15.Close),
                    b15.ts,
                    mfe,
                    mae,
                    i + 1,
                    "sweep_invalidate_15m",
                )
            idx_15m += 1
        if float(bar.Close) < stop:
            return _pack(
                entry_price,
                float(bar.Close),
                bar.ts,
                mfe,
                mae,
                i + 1,
                "hard_stop_5m",
            )
        if float(bar.High) >= session_high:
            return _pack(
                entry_price,
                session_high,
                bar.ts,
                mfe,
                mae,
                i + 1,
                "tp_session_high",
            )
        if i + 1 >= TIME_DECAY_BARS_5M and mfe < 0.5 * atr:
            return _pack(
                entry_price,
                float(bar.Close),
                bar.ts,
                mfe,
                mae,
                i + 1,
                "time_decay",
            )
        if bar.ts.time() >= SESSION_FLATTEN:
            return _pack(
                entry_price,
                float(bar.Close),
                bar.ts,
                mfe,
                mae,
                i + 1,
                "session_flatten",
            )

    last = after_5m[-1]
    return _pack(
        entry_price,
        float(last.Close),
        last.ts,
        mfe,
        mae,
        len(after_5m),
        "session_flatten",
    )


def _pack(
    entry: float,
    exit_price: float,
    exit_ts: datetime.datetime,
    mfe: float,
    mae: float,
    hold: int,
    reason: ExitReason,
) -> dict[str, Any]:
    return {
        "gross_pnl": round(exit_price - entry, 2),
        "mfe": round(mfe, 2),
        "mae": round(mae, 2),
        "hold_bars_5m": hold,
        "exit_reason": reason,
        "exit_price": round(exit_price, 1),
        "exit_ts": int(exit_ts.timestamp()),
    }