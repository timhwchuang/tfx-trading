from __future__ import annotations

from datetime import datetime, timedelta

from tfx_trading.bar_store import BarStore
from tfx_trading.indicators.sma import compute
from tfx_trading.kbar import KBar


def _bar(i: int, close: float, start: datetime | None = None) -> KBar:
    ts = (start or datetime(2026, 6, 15, 9, 0)) + timedelta(minutes=i)
    return KBar(
        timestamp=ts,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1,
        amount=close,
    )


def test_empty_bars() -> None:
    assert compute([]) == []


def test_warmup_none_until_window() -> None:
    bars = [_bar(i, float(i + 1)) for i in range(4)]
    snaps = compute(bars)
    assert len(snaps) == 4
    assert all(s.ma5 is None and s.ma20 is None for s in snaps)


def test_ma5_includes_current_and_rolls() -> None:
    closes = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    bars = [_bar(i, c) for i, c in enumerate(closes)]
    snaps = compute(bars)

    assert snaps[3].ma5 is None
    assert snaps[4].ma5 == 3.0  # (1+2+3+4+5) / 5
    assert snaps[5].ma5 == 4.0  # (2+3+4+5+6) / 5
    assert snaps[5].timestamp == bars[5].timestamp
    assert snaps[5].close == 6.0


def test_longer_windows_need_more_bars() -> None:
    bars = [_bar(i, 10.0) for i in range(60)]
    snaps = compute(bars)

    assert snaps[19].ma20 == 10.0
    assert snaps[18].ma20 is None
    assert snaps[59].ma60 == 10.0
    assert snaps[58].ma60 is None
    assert snaps[59].ma5 == 10.0


def test_compute_on_resampled_5m() -> None:
    start = datetime(2026, 6, 15, 8, 46)
    bars_1m = [_bar(i, float(10 + i), start=start) for i in range(25)]
    store = BarStore(bars_1m)
    bars_5m = store.resample_5m()
    assert len(bars_5m) == 5

    snaps = compute(bars_5m)
    assert snaps[-1].ma5 is not None
    assert snaps[-1].ma20 is None
    expected = sum(b.close for b in bars_5m) / 5
    assert snaps[-1].ma5 == expected
