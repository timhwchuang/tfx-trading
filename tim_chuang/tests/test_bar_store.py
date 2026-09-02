from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from tfx_trading.bar_reader import BarReader
from tfx_trading.bar_store import BarStore
from tfx_trading.kbar import KBar

_KBARS = Path(__file__).resolve().parent.parent / "tfx_trading" / "kbars_data"
_DAY_END = datetime(2026, 8, 17, 13, 45)


def _bar(
    offset: int,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: int = 1,
    start: datetime | None = None,
) -> KBar:
    ts = (start or datetime(2026, 8, 17, 8, 46)) + timedelta(minutes=offset)
    return KBar(
        timestamp=ts,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        amount=float(volume),
    )


def _load_817() -> BarStore:
    return BarStore(BarReader(_KBARS).load(date(2026, 8, 17), date(2026, 8, 17)))


def test_resample_15m_full_bucket() -> None:
    bars_1m = [_bar(i, 100 + i, 120 - i, 80 + i, 110 + i, volume=i + 1) for i in range(15)]
    out = BarStore(bars_1m).resample_15m()
    assert len(out) == 1
    bar = out[0]
    assert bar.timestamp == datetime(2026, 8, 17, 9, 0)
    assert bar.open == 100.0
    assert bar.high == 120.0
    assert bar.low == 80.0
    assert bar.close == 124.0
    assert bar.volume == 120
    assert bar.amount == 120.0


def test_resample_15m_drops_incomplete_bucket() -> None:
    bars_1m = [_bar(i, 100.0, 101.0, 99.0, 100.0) for i in range(15) if i != 5]
    assert BarStore(bars_1m).resample_15m() == []


def test_resample_15m_817_day_session() -> None:
    bars = [b for b in _load_817().resample_15m() if b.timestamp <= _DAY_END]
    assert len(bars) == 20
    assert bars[0].timestamp == datetime(2026, 8, 17, 9, 0)
    assert bars[-1].timestamp == datetime(2026, 8, 17, 13, 45)


def test_resample_15m_817_night_calendar_file() -> None:
    night = [b for b in _load_817().resample_15m() if b.timestamp > _DAY_END]
    assert night[0].timestamp == datetime(2026, 8, 17, 15, 15)
    assert night[-1].timestamp == datetime(2026, 8, 17, 23, 45)


def test_resample_5m_817_day_first_bar() -> None:
    bars = [b for b in _load_817().resample_5m() if b.timestamp <= _DAY_END]
    assert bars[0].timestamp == datetime(2026, 8, 17, 8, 50)


def test_resample_30m_full_bucket() -> None:
    bars_1m = [_bar(i, 100 + i, 120 - i, 80 + i, 110 + i, volume=i + 1) for i in range(30)]
    out = BarStore(bars_1m).resample_30m()
    assert len(out) == 1
    bar = out[0]
    assert bar.timestamp == datetime(2026, 8, 17, 9, 15)
    assert bar.open == 100.0
    assert bar.high == 120.0
    assert bar.low == 80.0
    assert bar.close == 139.0
    assert bar.volume == 465
    assert bar.amount == 465.0


def test_resample_30m_drops_incomplete_bucket() -> None:
    bars_1m = [_bar(i, 100.0, 101.0, 99.0, 100.0) for i in range(30) if i != 5]
    assert BarStore(bars_1m).resample_30m() == []


def test_resample_30m_817_day_session() -> None:
    bars = [b for b in _load_817().resample_30m() if b.timestamp <= _DAY_END]
    assert len(bars) == 10
    assert bars[0].timestamp == datetime(2026, 8, 17, 9, 15)
    assert bars[-1].timestamp == datetime(2026, 8, 17, 13, 45)


def test_resample_30m_817_night_calendar_file() -> None:
    night = [b for b in _load_817().resample_30m() if b.timestamp > _DAY_END]
    assert night[0].timestamp == datetime(2026, 8, 17, 15, 30)
    assert night[-1].timestamp == datetime(2026, 8, 17, 23, 30)


def test_resample_60m_full_bucket() -> None:
    bars_1m = [_bar(i, 100 + i, 120 - i, 80 + i, 110 + i, volume=i + 1) for i in range(60)]
    out = BarStore(bars_1m).resample_60m()
    assert len(out) == 1
    bar = out[0]
    assert bar.timestamp == datetime(2026, 8, 17, 9, 45)
    assert bar.open == 100.0
    assert bar.high == 120.0
    assert bar.low == 80.0
    assert bar.close == 169.0
    assert bar.volume == 1830
    assert bar.amount == 1830.0


def test_resample_60m_drops_incomplete_bucket() -> None:
    bars_1m = [_bar(i, 100.0, 101.0, 99.0, 100.0) for i in range(60) if i != 5]
    assert BarStore(bars_1m).resample_60m() == []


def test_resample_60m_817_day_session() -> None:
    bars = [b for b in _load_817().resample_60m() if b.timestamp <= _DAY_END]
    assert len(bars) == 5
    assert bars[0].timestamp == datetime(2026, 8, 17, 9, 45)
    assert bars[-1].timestamp == datetime(2026, 8, 17, 13, 45)


def test_resample_60m_817_night_calendar_file() -> None:
    night = [b for b in _load_817().resample_60m() if b.timestamp > _DAY_END]
    assert night[0].timestamp == datetime(2026, 8, 17, 16, 0)
    assert night[-1].timestamp == datetime(2026, 8, 17, 23, 0)
    assert _load_817().resample_1h() == _load_817().resample_60m()
