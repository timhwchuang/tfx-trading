from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from tfx_trading.kbar import KBar

WINDOWS = (5, 20, 60)


@dataclass(frozen=True)
class SMASnapshot:
    timestamp: datetime
    close: float
    ma5: float | None
    ma20: float | None
    ma60: float | None


def compute(bars: list[KBar]) -> list[SMASnapshot]:
    """
    對已收 K 的 close 做 rolling SMA，輸出與 bars 對齊。
    窗長不足時該均線為 None。
    """
    sums = {window: 0.0 for window in WINDOWS}
    closes: list[float] = []
    out: list[SMASnapshot] = []

    for bar in bars:
        closes.append(bar.close)
        i = len(closes) - 1
        values: dict[int, float | None] = {}
        for window in WINDOWS:
            sums[window] += bar.close
            if i >= window:
                sums[window] -= closes[i - window]
            values[window] = sums[window] / window if i >= window - 1 else None
        out.append(
            SMASnapshot(
                timestamp=bar.timestamp,
                close=bar.close,
                ma5=values[5],
                ma20=values[20],
                ma60=values[60],
            )
        )

    return out
