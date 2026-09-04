from __future__ import annotations

from datetime import datetime

from tfx_trading.backtest.census import census_5m_tape
from tfx_trading.calendar import TradeCalendar
from tfx_trading.kbar import KBar


def _k(ts: datetime, high: float, low: float, close: float) -> KBar:
    return KBar(
        timestamp=ts,
        open=close,
        high=high,
        low=low,
        close=close,
        volume=1,
        amount=close,
    )


def _ts(day: int, hour: int, minute: int) -> datetime:
    return datetime(2026, 8, day, hour, minute)


def _prior_day_pdh_101() -> list[KBar]:
    return [
        _k(_ts(14, 13, 40), 100, 90, 95),
        _k(_ts(14, 13, 45), 101, 91, 96),
    ]


def test_pdh_wick_counts_one_sweep_onset_then_taken() -> None:
    bars = _prior_day_pdh_101() + [
        _k(_ts(17, 8, 50), 102, 90, 100),
        _k(_ts(17, 9, 15), 102, 90, 100),
        _k(_ts(17, 9, 20), 110, 90, 105),
    ]
    totals = census_5m_tape(bars, TradeCalendar())
    assert totals.sweep_onset["pdh"] == 1
    assert totals.taken_onset["pdh"] == 1
    assert totals.live_swept_bars["pdh"] >= 1
    assert totals.live_taken_bars["pdh"] >= 1


def test_untouched_pdh_has_zero_sweep_onset() -> None:
    bars = _prior_day_pdh_101() + [
        _k(_ts(17, 8, 50), 100, 90, 95),
        _k(_ts(17, 9, 15), 99, 91, 96),
    ]
    totals = census_5m_tape(bars, TradeCalendar())
    assert totals.sweep_onset["pdh"] == 0
    assert totals.taken_onset["pdh"] == 0
    assert totals.arm_window["short_swept"] == 0
    assert totals.arm_window["long_swept"] == 0


def test_census_does_not_count_off_session_bars() -> None:
    bars = [
        _k(datetime(2026, 8, 17, 7, 0), 100, 90, 95),
        *_prior_day_pdh_101(),
    ]
    totals = census_5m_tape(bars, TradeCalendar())
    assert totals.n_5m == 2
    assert totals.n_day_5m == 2
