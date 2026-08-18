from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from tfx_trading.bar_store import SessionKind, is_session_complete, session_key, session_kind
from tfx_trading.kbar import KBar

LOOKBACK = 2
MIN_POINTS = 20.0
SwingSide = Literal["high", "low"]
LevelKind = Literal[
    "pdh",
    "pdl",
    "prev_night_high",
    "prev_night_low",
    "session_high",
    "session_low",
]


@dataclass(frozen=True)
class Swing:
    timestamp: datetime
    confirmed_at: datetime
    side: SwingSide
    price: float
    significant: bool
    session: SessionKind


@dataclass(frozen=True)
class SessionLevel:
    kind: LevelKind
    price: float
    source_ts: datetime
    developing: bool


@dataclass(frozen=True)
class SmcLevels:
    swings: list[Swing]
    pdh: SessionLevel | None
    pdl: SessionLevel | None
    prev_night_high: SessionLevel | None
    prev_night_low: SessionLevel | None
    session_high: SessionLevel | None
    session_low: SessionLevel | None


@dataclass(frozen=True)
class _Segment:
    kind: SessionKind
    bars: list[KBar]


def compute(bars: list[KBar], min_points: float = MIN_POINTS) -> SmcLevels:
    """
    對已收 5 分 K 算 confirmed swings 與 session 流動性。
    as_of = bars[-1].timestamp；缺前一段則該欄位為 None。
    """
    if not bars:
        return SmcLevels([], None, None, None, None, None, None)

    bars = [b for b in bars if session_kind(b.timestamp) is not None]
    segments = _split_sessions(bars)
    swings = _detect_swings(bars, min_points)
    return _with_liquidity(segments, swings)


def _split_sessions(bars: list[KBar]) -> list[_Segment]:
    """換盤（session_key）才換段；盤中缺 5 分仍留在同一盤。"""
    segments: list[_Segment] = []
    current_bars: list[KBar] = []
    current_key: tuple[date, SessionKind] | None = None

    for bar in bars:
        key = session_key(bar.timestamp)
        if key is None:
            continue
        if current_bars and key != current_key:
            assert current_key is not None
            segments.append(_Segment(current_key[1], current_bars))
            current_bars = [bar]
            current_key = key
        else:
            current_bars.append(bar)
            current_key = key

    if current_bars and current_key is not None:
        segments.append(_Segment(current_key[1], current_bars))
    return segments


def _detect_swings(bars: list[KBar], min_points: float) -> list[Swing]:
    """L=2 對整條 5 分序列（K 序號，與 Pine 相同），不依 session 切開。"""
    n = len(bars)
    raw: list[tuple[int, SwingSide, float]] = []
    for i in range(LOOKBACK, n - LOOKBACK):
        high = bars[i].high
        low = bars[i].low
        neighbors = list(range(i - LOOKBACK, i)) + list(range(i + 1, i + LOOKBACK + 1))
        is_high = all(high > bars[j].high for j in neighbors)
        is_low = all(low < bars[j].low for j in neighbors)
        if is_high and is_low:
            continue
        if is_high:
            raw.append((i, "high", high))
        elif is_low:
            raw.append((i, "low", low))

    collapsed: list[tuple[int, SwingSide, float]] = []
    for item in raw:
        if collapsed and collapsed[-1][1] == item[1]:
            _, side, prev_price = collapsed[-1]
            price = item[2]
            more_extreme = price >= prev_price if side == "high" else price <= prev_price
            if more_extreme:
                collapsed[-1] = item
        else:
            collapsed.append(item)

    out: list[Swing] = []
    for k, (i, side, price) in enumerate(collapsed):
        kind = session_kind(bars[i].timestamp)
        if kind is None:
            continue
        if k == 0:
            significant = False
        else:
            significant = abs(price - collapsed[k - 1][2]) >= min_points
        out.append(
            Swing(
                timestamp=bars[i].timestamp,
                confirmed_at=bars[i + LOOKBACK].timestamp,
                side=side,
                price=price,
                significant=significant,
                session=kind,
            )
        )
    return out


def _with_liquidity(segments: list[_Segment], swings: list[Swing]) -> SmcLevels:
    if not segments:
        return SmcLevels(swings, None, None, None, None, None, None)

    current = segments[-1]
    prior = segments[:-1]
    last_day = _last_complete(prior, "day")
    last_night = _last_complete(prior, "night")
    developing = not is_session_complete(current.kind, current.bars[-1].timestamp)
    high_bar = max(current.bars, key=lambda b: b.high)
    low_bar = min(current.bars, key=lambda b: b.low)

    return SmcLevels(
        swings=swings,
        pdh=_level_from_segment(last_day, "pdh", "high"),
        pdl=_level_from_segment(last_day, "pdl", "low"),
        prev_night_high=_level_from_segment(last_night, "prev_night_high", "high"),
        prev_night_low=_level_from_segment(last_night, "prev_night_low", "low"),
        session_high=SessionLevel("session_high", high_bar.high, high_bar.timestamp, developing),
        session_low=SessionLevel("session_low", low_bar.low, low_bar.timestamp, developing),
    )


def _last_complete(segments: list[_Segment], kind: SessionKind) -> _Segment | None:
    for segment in reversed(segments):
        if segment.kind == kind and is_session_complete(kind, segment.bars[-1].timestamp):
            return segment
    return None


def _level_from_segment(
    segment: _Segment | None,
    kind: LevelKind,
    extreme: Literal["high", "low"],
) -> SessionLevel | None:
    if segment is None:
        return None
    bar = (
        max(segment.bars, key=lambda b: b.high)
        if extreme == "high"
        else min(segment.bars, key=lambda b: b.low)
    )
    price = bar.high if extreme == "high" else bar.low
    return SessionLevel(kind, price, bar.timestamp, developing=False)
