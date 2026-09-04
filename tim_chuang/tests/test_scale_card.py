from __future__ import annotations

from datetime import datetime

from tfx_trading.backtest.scale_card import _pct, _session_clock, percentile
from tfx_trading.kbar import KBar


def test_percentile_p50_p90() -> None:
    xs = [float(i) for i in range(1, 11)]
    assert percentile(xs, 0.5) == 5.5
    assert abs(percentile(xs, 0.9) - 9.1) < 1e-9


def test_pct_share_ge() -> None:
    bars = [
        KBar(datetime(2026, 8, 17, 10, i), 10, 10 + r, 10, 10, 1, 10)
        for i, r in enumerate((3.0, 5.0, 10.0, 21.0))
    ]
    sample = _pct([bar.high - bar.low for bar in bars])
    assert sample.n == 4
    assert sample.share_ge_3 == 1.0
    assert sample.share_ge_5 == 0.75
    assert sample.share_ge_10 == 0.5
    assert sample.share_ge_15 == 0.25


def test_session_clock_splits_open_and_night() -> None:
    bars = [
        KBar(datetime(2026, 8, 17, 8, 50), 10, 30, 10, 20, 1, 20),
        KBar(datetime(2026, 8, 17, 11, 0), 10, 18, 10, 12, 1, 12),
        KBar(datetime(2026, 8, 17, 15, 5), 10, 16, 10, 11, 1, 11),
    ]
    clock = _session_clock(bars)
    assert clock["open_0850_0915"].p50 == 20.0
    assert clock["mid_1100_1300"].p50 == 8.0
    assert clock["night"].p50 == 6.0
