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


def test_resample_4h_full_bucket() -> None:
    bars_1m = [_bar(i, 100 + i, 120 - i, 80 + i, 110 + i, volume=i + 1) for i in range(240)]
    out = BarStore(bars_1m).resample_4h()
    assert len(out) == 1
    bar = out[0]
    assert bar.timestamp == datetime(2026, 8, 17, 12, 45)
    assert bar.open == 100.0
    assert bar.high == 120.0
    assert bar.low == 80.0
    assert bar.close == 349.0
    assert bar.volume == 28920
    assert bar.amount == 28920.0


def test_resample_4h_drops_incomplete_bucket() -> None:
    bars_1m = [_bar(i, 100.0, 101.0, 99.0, 100.0) for i in range(240) if i != 5]
    assert BarStore(bars_1m).resample_4h() == []


def test_resample_4h_817_day_session() -> None:
    bars = [b for b in _load_817().resample_4h() if b.timestamp <= _DAY_END]
    assert len(bars) == 1
    assert bars[0].timestamp == datetime(2026, 8, 17, 12, 45)


def test_resample_4h_817_night_calendar_file() -> None:
    night = [b for b in _load_817().resample_4h() if b.timestamp > _DAY_END]
    assert len(night) == 2
    assert [b.timestamp for b in night] == [
        datetime(2026, 8, 17, 19, 0),
        datetime(2026, 8, 17, 23, 0),
    ]
    assert datetime(2026, 8, 18, 3, 0) not in {b.timestamp for b in night}


def test_resample_4h_overnight_needs_next_file() -> None:
    kbars = BarReader(_KBARS).load(date(2026, 8, 17), date(2026, 8, 18))
    bars = BarStore(kbars).resample_4h()
    assert any(b.timestamp == datetime(2026, 8, 18, 3, 0) for b in bars)


def _clock_mins(ts: datetime) -> int:
    return ts.hour * 60 + ts.minute


def test_resample_1d_full_day_session() -> None:
    bars_1m = [_bar(i, 100 + i, 120 - i, 80 + i, 110 + i, volume=i + 1) for i in range(300)]
    out = BarStore(bars_1m).resample_1d()
    assert len(out) == 1
    bar = out[0]
    assert bar.timestamp == datetime(2026, 8, 17, 13, 45)
    assert bar.open == 100.0
    assert bar.high == 120.0
    assert bar.low == 80.0
    assert bar.close == 409.0
    assert bar.volume == 45150
    assert bar.amount == 45150.0


def test_resample_1d_drops_incomplete_day() -> None:
    bars_1m = [_bar(i, 100.0, 101.0, 99.0, 100.0) for i in range(300) if i != 5]
    assert BarStore(bars_1m).resample_1d() == []


def test_resample_1d_weekend_leftover_is_not_a_day() -> None:
    kbars = BarReader(_KBARS).load(date(2026, 8, 15), date(2026, 8, 15))
    assert BarStore(kbars).resample_1d() == []


def test_resample_1d_817_day_only() -> None:
    out = _load_817().resample_1d()
    assert len(out) == 1
    bar = out[0]
    assert bar.timestamp == datetime(2026, 8, 17, 13, 45)
    minutes = _load_817().resample_1m()
    first = next(b for b in minutes if b.timestamp == datetime(2026, 8, 17, 8, 46))
    last = next(b for b in minutes if b.timestamp == datetime(2026, 8, 17, 13, 45))
    day = [
        b
        for b in _load_817().resample_1m()
        if b.timestamp.date() == date(2026, 8, 17)
        and 8 * 60 + 45 < _clock_mins(b.timestamp) <= 13 * 60 + 46
    ]
    assert bar.open == first.open
    assert bar.close == last.close
    assert bar.high == max(b.high for b in day)
    assert bar.low == min(b.low for b in day)


def test_resample_1d_817_stitches_friday_night() -> None:
    kbars = BarReader(_KBARS).load(date(2026, 8, 14), date(2026, 8, 17))
    out = [b for b in BarStore(kbars).resample_1d() if b.timestamp == datetime(2026, 8, 17, 13, 45)]
    assert len(out) == 1
    bar = out[0]
    night = [
        b
        for b in kbars
        if (b.timestamp.date() == date(2026, 8, 14) and _clock_mins(b.timestamp) > 15 * 60)
        or (b.timestamp.date() == date(2026, 8, 15) and _clock_mins(b.timestamp) <= 5 * 60 + 1)
    ]
    day = [
        b
        for b in kbars
        if b.timestamp.date() == date(2026, 8, 17)
        and 8 * 60 + 45 < _clock_mins(b.timestamp) <= 13 * 60 + 46
    ]
    chunk = night + day
    assert bar.open == chunk[0].open
    assert bar.close == chunk[-1].close
    assert bar.high == max(b.high for b in chunk)
    assert bar.low == min(b.low for b in chunk)
    assert bar.volume == sum(b.volume for b in chunk)


def test_resample_1d_uses_1346_close() -> None:
    bars_1m = [_bar(i, 100 + i, 120 - i, 80 + i, 110 + i, volume=i + 1) for i in range(300)]
    tail = KBar(
        timestamp=datetime(2026, 8, 17, 13, 46),
        open=409.0,
        high=410.0,
        low=408.0,
        close=407.0,
        volume=4,
        amount=4.0,
    )
    out = BarStore(bars_1m + [tail]).resample_1d()
    assert len(out) == 1
    bar = out[0]
    assert bar.timestamp == datetime(2026, 8, 17, 13, 45)
    assert bar.close == 407.0
    assert bar.high == 410.0
    assert bar.low == 80.0
    assert bar.volume == 45154


def test_resample_1d_includes_0501_night_tail() -> None:
    night = [
        _bar(i, 50.0, 55.0, 45.0, 50.0, start=datetime(2026, 8, 16, 15, 1)) for i in range(599)
    ]
    dawn_tail = KBar(
        timestamp=datetime(2026, 8, 17, 5, 1),
        open=50.0,
        high=200.0,
        low=40.0,
        close=50.0,
        volume=3,
        amount=3.0,
    )
    day = [_bar(i, 100 + i, 120 - i, 80 + i, 110 + i, volume=i + 1) for i in range(300)]
    out = BarStore(night + [dawn_tail] + day).resample_1d()
    assert len(out) == 1
    bar = out[0]
    assert bar.timestamp == datetime(2026, 8, 17, 13, 45)
    assert bar.open == 50.0
    assert bar.high == 200.0
    assert bar.low == 40.0
    assert bar.close == 409.0
    assert bar.volume == 45150 + 599 + 3


def test_resample_1d_827_close_uses_1346() -> None:
    kbars = BarReader(_KBARS).load(date(2026, 8, 26), date(2026, 8, 27))
    out = [b for b in BarStore(kbars).resample_1d() if b.timestamp == datetime(2026, 8, 27, 13, 45)]
    assert len(out) == 1
    assert out[0].close == 46075.0
