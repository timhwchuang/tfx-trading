from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Literal

from tfx_trading.bar_store import SessionKind, is_session_complete, session_key, session_kind
from tfx_trading.kbar import KBar

LOOKBACK = 2
MIN_POINTS = 20.0
SwingSide = Literal["high", "low"]
InteractKind = Literal["untouched", "swept", "taken"]
Position = Literal["premium", "discount", "equilibrium", "outside"]
EventKind = Literal["bos", "choch"]
EventDirection = Literal["bullish", "bearish"]
EventScope = Literal["internal", "external"]
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
    interact: InteractKind | None
    interact_ts: datetime | None


@dataclass(frozen=True)
class DealingRange:
    high: float
    high_ts: datetime
    low: float
    low_ts: datetime
    eq: float
    position: Position


@dataclass(frozen=True)
class StructureEvent:
    kind: EventKind
    direction: EventDirection
    ts: datetime
    broken_price: float
    broken_swing_ts: datetime
    scope: EventScope


@dataclass(frozen=True)
class SmcLevels:
    swings: list[Swing]
    pdh: SessionLevel | None
    pdl: SessionLevel | None
    prev_night_high: SessionLevel | None
    prev_night_low: SessionLevel | None
    session_high: SessionLevel | None
    session_low: SessionLevel | None
    last_bar: KBar | None
    dealing_range: DealingRange | None
    events: list[StructureEvent]


@dataclass(frozen=True)
class _Segment:
    kind: SessionKind
    bars: list[KBar]


def compute(bars: list[KBar], min_points: float = MIN_POINTS) -> SmcLevels:
    """
    對已收 5 分 K 算 confirmed swings 與 session 流動性。
    as_of = last_bar.timestamp（有 K 時）；缺前一段則該流動性欄位為 None。
    """
    bars = [b for b in bars if session_kind(b.timestamp) is not None]
    last = bars[-1] if bars else None
    segments = _split_sessions(bars)
    swings = _detect_swings(bars, min_points)
    return _with_liquidity(segments, swings, last)


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


def _with_liquidity(
    segments: list[_Segment],
    swings: list[Swing],
    last_bar: KBar | None,
) -> SmcLevels:
    if not segments:
        return SmcLevels(
            swings=swings,
            pdh=None,
            pdl=None,
            prev_night_high=None,
            prev_night_low=None,
            session_high=None,
            session_low=None,
            last_bar=last_bar,
            dealing_range=None,
            events=[],
        )

    current = segments[-1]
    prior = segments[:-1]
    last_day = _last_complete(prior, "day")
    last_night = _last_complete(prior, "night")
    developing = not is_session_complete(current.kind, current.bars[-1].timestamp)
    high_bar = max(current.bars, key=lambda b: b.high)
    low_bar = min(current.bars, key=lambda b: b.low)

    return SmcLevels(
        swings=swings,
        pdh=_annotate_interact(_level_from_segment(last_day, "pdh", "high"), current.bars, "high"),
        pdl=_annotate_interact(_level_from_segment(last_day, "pdl", "low"), current.bars, "low"),
        prev_night_high=_annotate_interact(
            _level_from_segment(last_night, "prev_night_high", "high"),
            current.bars,
            "high",
        ),
        prev_night_low=_annotate_interact(
            _level_from_segment(last_night, "prev_night_low", "low"),
            current.bars,
            "low",
        ),
        session_high=SessionLevel(
            kind="session_high",
            price=high_bar.high,
            source_ts=high_bar.timestamp,
            developing=developing,
            interact=None,
            interact_ts=None,
        ),
        session_low=SessionLevel(
            kind="session_low",
            price=low_bar.low,
            source_ts=low_bar.timestamp,
            developing=developing,
            interact=None,
            interact_ts=None,
        ),
        last_bar=last_bar,
        dealing_range=_dealing_range(swings, current, last_bar),
        events=_structure_events(swings, current, high_bar.high, low_bar.low),
    )


def _dealing_range(
    swings: list[Swing],
    current: _Segment,
    last_bar: KBar | None,
) -> DealingRange | None:
    if last_bar is None:
        return None
    start = current.bars[0].timestamp
    end = current.bars[-1].timestamp
    sig = [s for s in swings if s.significant and start <= s.timestamp <= end]
    last_high = next((s for s in reversed(sig) if s.side == "high"), None)
    last_low = next((s for s in reversed(sig) if s.side == "low"), None)
    if last_high is None or last_low is None:
        return None
    eq = (last_high.price + last_low.price) / 2
    close = last_bar.close
    if close < last_low.price or close > last_high.price:
        position: Position = "outside"
    elif close > eq:
        position = "premium"
    elif close < eq:
        position = "discount"
    else:
        position = "equilibrium"
    return DealingRange(
        high=last_high.price,
        high_ts=last_high.timestamp,
        low=last_low.price,
        low_ts=last_low.timestamp,
        eq=eq,
        position=position,
    )


def _structure_events(
    swings: list[Swing],
    current: _Segment,
    session_high: float,
    session_low: float,
) -> list[StructureEvent]:
    start = current.bars[0].timestamp
    end = current.bars[-1].timestamp
    sig = [s for s in swings if s.significant and start <= s.timestamp <= end]
    broken: set[datetime] = set()
    bias: EventDirection | None = None
    events: list[StructureEvent] = []
    for bar in current.bars:
        last_high = next(
            (s for s in reversed(sig) if s.side == "high" and s.confirmed_at <= bar.timestamp),
            None,
        )
        last_low = next(
            (s for s in reversed(sig) if s.side == "low" and s.confirmed_at <= bar.timestamp),
            None,
        )
        if (
            last_high is not None
            and last_high.timestamp not in broken
            and bar.close > last_high.price
        ):
            events.append(
                _structure_event(
                    "bullish", bar.timestamp, last_high, bias, session_high, session_low
                )
            )
            broken.add(last_high.timestamp)
            bias = "bullish"
        elif (
            last_low is not None and last_low.timestamp not in broken and bar.close < last_low.price
        ):
            events.append(
                _structure_event(
                    "bearish", bar.timestamp, last_low, bias, session_high, session_low
                )
            )
            broken.add(last_low.timestamp)
            bias = "bearish"
    return events


def _structure_event(
    direction: EventDirection,
    ts: datetime,
    swing: Swing,
    bias: EventDirection | None,
    session_high: float,
    session_low: float,
) -> StructureEvent:
    kind: EventKind = "bos" if bias == direction else "choch"
    scope: EventScope = (
        "external" if swing.price == session_high or swing.price == session_low else "internal"
    )
    return StructureEvent(
        kind=kind,
        direction=direction,
        ts=ts,
        broken_price=swing.price,
        broken_swing_ts=swing.timestamp,
        scope=scope,
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
    return SessionLevel(
        kind=kind,
        price=price,
        source_ts=bar.timestamp,
        developing=False,
        interact=None,
        interact_ts=None,
    )


def _annotate_interact(
    level: SessionLevel | None,
    bars: list[KBar],
    extreme: Literal["high", "low"],
) -> SessionLevel | None:
    if level is None:
        return None
    interact: InteractKind = "untouched"
    interact_ts: datetime | None = None
    for bar in bars:
        if bar.timestamp <= level.source_ts:
            continue
        hit = _bar_interact(bar, level.price, extreme)
        if hit is None:
            continue
        if hit == "taken":
            return replace(level, interact="taken", interact_ts=bar.timestamp)
        if interact == "untouched":
            interact = "swept"
            interact_ts = bar.timestamp
    return replace(level, interact=interact, interact_ts=interact_ts)


def _bar_interact(
    bar: KBar,
    price: float,
    extreme: Literal["high", "low"],
) -> InteractKind | None:
    if extreme == "high":
        if bar.close > price:
            return "taken"
        if bar.high > price:
            return "swept"
        return None
    if bar.close < price:
        return "taken"
    if bar.low < price:
        return "swept"
    return None
