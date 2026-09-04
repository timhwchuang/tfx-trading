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


class FvgTracker:
    """Incremental FVG detect + mitigation. Snapshot at bar k equals compute(bars[:k])."""

    def __init__(self, min_points: float = 0.0) -> None:
        self._min_points = min_points
        self._prev2: KBar | None = None
        self._prev1: KBar | None = None
        self._fvgs: list[Fvg] = []
        self._live: list[int] = []

    def push(self, bar: KBar) -> None:
        if session_kind(bar.timestamp) is None:
            return
        still_live: list[int] = []
        for idx in self._live:
            updated = _advance(self._fvgs[idx], bar)
            self._fvgs[idx] = updated
            if updated.state != "filled":
                still_live.append(idx)
        self._live = still_live
        formed = _triple(self._prev2, self._prev1, bar, self._min_points)
        if formed is not None:
            self._live.append(len(self._fvgs))
            self._fvgs.append(formed)
        self._prev2 = self._prev1
        self._prev1 = bar

    def extend(self, bars: list[KBar]) -> None:
        for bar in bars:
            self.push(bar)

    def snapshot(self) -> list[Fvg]:
        return list(self._fvgs)


def compute(bars: list[KBar], min_points: float = 0.0) -> list[Fvg]:
    """
    對已收 K 偵測 FVG，並以最後一根為 as_of 標註 mitigation。
    先過濾非盤中 K；形成須同盤三根相鄰；狀態可跨盤更新。
    """
    tracker = FvgTracker(min_points)
    tracker.extend(bars)
    return tracker.snapshot()


def _triple(
    a: KBar | None,
    b: KBar | None,
    c: KBar,
    min_points: float,
) -> Fvg | None:
    if a is None or b is None:
        return None
    key_a = session_key(a.timestamp)
    if key_a is None:
        return None
    if session_key(b.timestamp) != key_a or session_key(c.timestamp) != key_a:
        return None
    kind = session_kind(c.timestamp)
    if kind is None:
        return None
    if a.high < c.low:
        direction: FvgDirection = "bullish"
        bottom, top = a.high, c.low
    elif a.low > c.high:
        direction = "bearish"
        bottom, top = c.high, a.low
    else:
        return None
    size = top - bottom
    if size < min_points:
        return None
    return Fvg(
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


def _detect(bars: list[KBar], min_points: float) -> list[Fvg]:
    out: list[Fvg] = []
    for i in range(len(bars) - 2):
        formed = _triple(bars[i], bars[i + 1], bars[i + 2], min_points)
        if formed is not None:
            out.append(formed)
    return out


def _advance(fvg: Fvg, bar: KBar) -> Fvg:
    if bar.timestamp <= fvg.formed_at:
        return fvg
    if _is_filled(fvg, bar):
        ts = bar.timestamp
        mitigated_ts = fvg.mitigated_ts if fvg.mitigated_ts is not None else ts
        return replace(fvg, state="filled", mitigated_ts=mitigated_ts, filled_ts=ts)
    if fvg.state == "untouched" and _is_mitigated(fvg, bar):
        return replace(fvg, state="mitigated", mitigated_ts=bar.timestamp)
    return fvg


def _annotate(fvg: Fvg, bars: list[KBar]) -> Fvg:
    for bar in bars:
        fvg = _advance(fvg, bar)
        if fvg.state == "filled":
            return fvg
    return fvg


def _is_filled(fvg: Fvg, bar: KBar) -> bool:
    if fvg.direction == "bullish":
        return bar.low <= fvg.bottom
    return bar.high >= fvg.top


def _is_mitigated(fvg: Fvg, bar: KBar) -> bool:
    if fvg.direction == "bullish":
        return bar.low < fvg.top
    return bar.high > fvg.bottom


def compute_from_scratch(bars: list[KBar], min_points: float = 0.0) -> list[Fvg]:
    """Prefix-wide detect + annotate. Oracle for incremental equivalence."""
    session_bars = [b for b in bars if session_kind(b.timestamp) is not None]
    return [_annotate(fvg, session_bars) for fvg in _detect(session_bars, min_points)]
