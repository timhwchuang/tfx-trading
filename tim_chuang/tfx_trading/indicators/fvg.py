from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal

from tfx_trading.bar_store import SessionKind, session_key, session_kind
from tfx_trading.kbar import KBar

FvgState = Literal["untouched", "mitigated", "filled"]
FvgDirection = Literal["bullish", "bearish"]


@dataclass(frozen=True)
class Fvg:
    direction: FvgDirection
    top: float
    bottom: float
    ce: float
    size: float
    gap_start_ts: datetime
    formed_at: datetime
    session: SessionKind
    state: FvgState
    mitigated_ts: datetime | None
    filled_ts: datetime | None


def compute(bars: list[KBar], min_points: float = 0.0) -> list[Fvg]:
    """
    對已收 K 偵測 FVG，並以最後一根為 as_of 標註 mitigation。
    先過濾非盤中 K；形成須同盤三根相鄰；狀態可跨盤更新。
    """
    bars = [b for b in bars if session_kind(b.timestamp) is not None]
    return [_annotate(fvg, bars) for fvg in _detect(bars, min_points)]


def _detect(bars: list[KBar], min_points: float) -> list[Fvg]:
    out: list[Fvg] = []
    for i in range(len(bars) - 2):
        a, b, c = bars[i], bars[i + 1], bars[i + 2]
        key_a = session_key(a.timestamp)
        if key_a is None:
            continue
        if session_key(b.timestamp) != key_a or session_key(c.timestamp) != key_a:
            continue
        kind = session_kind(c.timestamp)
        if kind is None:
            continue
        if a.high < c.low:
            direction: FvgDirection = "bullish"
            bottom, top = a.high, c.low
        elif a.low > c.high:
            direction = "bearish"
            bottom, top = c.high, a.low
        else:
            continue
        size = top - bottom
        if size < min_points:
            continue
        out.append(
            Fvg(
                direction=direction,
                top=top,
                bottom=bottom,
                ce=(top + bottom) / 2,
                size=size,
                gap_start_ts=a.timestamp,
                formed_at=c.timestamp,
                session=kind,
                state="untouched",
                mitigated_ts=None,
                filled_ts=None,
            )
        )
    return out


def _annotate(fvg: Fvg, bars: list[KBar]) -> Fvg:
    for bar in bars:
        if bar.timestamp <= fvg.formed_at:
            continue
        if _is_filled(fvg, bar):
            ts = bar.timestamp
            mitigated_ts = fvg.mitigated_ts if fvg.mitigated_ts is not None else ts
            return replace(fvg, state="filled", mitigated_ts=mitigated_ts, filled_ts=ts)
        if fvg.state == "untouched" and _is_mitigated(fvg, bar):
            fvg = replace(fvg, state="mitigated", mitigated_ts=bar.timestamp)
    return fvg


def _is_filled(fvg: Fvg, bar: KBar) -> bool:
    if fvg.direction == "bullish":
        return bar.low <= fvg.bottom
    return bar.high >= fvg.top


def _is_mitigated(fvg: Fvg, bar: KBar) -> bool:
    if fvg.direction == "bullish":
        return bar.low < fvg.top
    return bar.high > fvg.bottom
