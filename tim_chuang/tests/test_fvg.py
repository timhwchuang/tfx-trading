from __future__ import annotations

from datetime import datetime

from tfx_trading.indicators.fvg import compute
from tfx_trading.kbar import KBar


def _k(
    ts: datetime,
    high: float,
    low: float,
    close: float | None = None,
) -> KBar:
    close_px = high if close is None else close
    return KBar(
        timestamp=ts,
        open=close_px,
        high=high,
        low=low,
        close=close_px,
        volume=1,
        amount=close_px,
    )


def _ts(day: int, hour: int, minute: int, month: int = 8) -> datetime:
    return datetime(2026, month, day, hour, minute)


def _bullish_abc(*, a_high: float = 100.0, c_low: float = 110.0) -> list[KBar]:
    return [
        _k(_ts(17, 9, 0), a_high, 90.0, close=95.0),
        _k(_ts(17, 9, 5), 120.0, 105.0, close=115.0),
        _k(_ts(17, 9, 10), 125.0, c_low, close=120.0),
    ]


def test_empty_bars() -> None:
    assert compute([]) == []


def test_non_session_bars_are_filtered() -> None:
    bars = [
        _k(_ts(17, 14, 0), 100.0, 80.0, close=90.0),
        _k(_ts(17, 14, 5), 130.0, 110.0, close=120.0),
        _k(_ts(17, 14, 10), 140.0, 120.0, close=130.0),
    ]
    assert compute(bars) == []


def test_bullish_forms_on_strict_gap() -> None:
    fvgs = compute(_bullish_abc())
    assert len(fvgs) == 1
    fvg = fvgs[0]
    assert fvg.direction == "bullish"
    assert fvg.bottom == 100.0
    assert fvg.top == 110.0
    assert fvg.size == 10.0
    assert fvg.ce == 105.0
    assert fvg.gap_start_ts == _ts(17, 9, 0)
    assert fvg.formed_at == _ts(17, 9, 10)
    assert fvg.session == "day"
    assert fvg.state == "untouched"
    assert fvg.mitigated_ts is None
    assert fvg.filled_ts is None


def test_bearish_forms_on_strict_gap() -> None:
    bars = [
        _k(_ts(17, 9, 0), 120.0, 110.0, close=115.0),
        _k(_ts(17, 9, 5), 108.0, 95.0, close=100.0),
        _k(_ts(17, 9, 10), 100.0, 90.0, close=92.0),
    ]
    fvgs = compute(bars)
    assert len(fvgs) == 1
    fvg = fvgs[0]
    assert fvg.direction == "bearish"
    assert fvg.bottom == 100.0
    assert fvg.top == 110.0
    assert fvg.size == 10.0
    assert fvg.ce == 105.0
    assert fvg.formed_at == _ts(17, 9, 10)
    assert fvg.state == "untouched"


def test_equal_high_low_does_not_form() -> None:
    assert compute(_bullish_abc(c_low=100.0)) == []


def test_min_points_keeps_equal_size() -> None:
    fvgs = compute(_bullish_abc(), min_points=10.0)
    assert len(fvgs) == 1
    assert fvgs[0].size == 10.0


def test_min_points_drops_smaller() -> None:
    assert compute(_bullish_abc(), min_points=10.1) == []


def test_day_to_night_seam_does_not_form() -> None:
    bars = [
        _k(_ts(17, 13, 35), 100.0, 90.0, close=95.0),
        _k(_ts(17, 13, 40), 120.0, 105.0, close=115.0),
        _k(_ts(17, 13, 45), 125.0, 110.0, close=120.0),
        _k(_ts(17, 15, 5), 140.0, 130.0, close=135.0),
        _k(_ts(17, 15, 10), 150.0, 140.0, close=145.0),
    ]
    fvgs = compute(bars)
    assert len(fvgs) == 1
    fvg = fvgs[0]
    assert fvg.gap_start_ts == _ts(17, 13, 35)
    assert fvg.formed_at == _ts(17, 13, 45)
    assert fvg.session == "day"
    assert fvg.direction == "bullish"
    assert all(f.gap_start_ts not in {_ts(17, 13, 40), _ts(17, 13, 45)} for f in fvgs)
    assert all(f.formed_at not in {_ts(17, 15, 5), _ts(17, 15, 10)} for f in fvgs)


def test_night_to_day_seam_does_not_form() -> None:
    bars = [
        _k(_ts(15, 4, 50), 100.0, 90.0, close=95.0),
        _k(_ts(15, 4, 55), 120.0, 105.0, close=115.0),
        _k(_ts(15, 5, 0), 125.0, 110.0, close=120.0),
        _k(_ts(17, 8, 50), 140.0, 130.0, close=135.0),
        _k(_ts(17, 8, 55), 150.0, 140.0, close=145.0),
    ]
    fvgs = compute(bars)
    assert len(fvgs) == 1
    fvg = fvgs[0]
    assert fvg.gap_start_ts == _ts(15, 4, 50)
    assert fvg.formed_at == _ts(15, 5, 0)
    assert fvg.session == "night"
    assert fvg.direction == "bullish"
    assert all(f.formed_at not in {_ts(17, 8, 50), _ts(17, 8, 55)} for f in fvgs)
    assert all(f.gap_start_ts != _ts(15, 5, 0) for f in fvgs)


def test_lunch_bar_does_not_fill() -> None:
    bars = _bullish_abc() + [_k(_ts(17, 14, 0), 112.0, 99.0, close=108.0)]
    fvgs = compute(bars)
    assert len(fvgs) == 1
    fvg = fvgs[0]
    assert fvg.formed_at == _ts(17, 9, 10)
    assert fvg.state == "untouched"
    assert fvg.mitigated_ts is None
    assert fvg.filled_ts is None


def test_missing_5m_adjacent_triple_still_forms() -> None:
    bars = [
        _k(_ts(17, 9, 0), 100.0, 90.0, close=95.0),
        _k(_ts(17, 9, 5), 120.0, 105.0, close=115.0),
        _k(_ts(17, 9, 15), 125.0, 110.0, close=120.0),
    ]
    fvgs = compute(bars)
    assert len(fvgs) == 1
    assert fvgs[0].formed_at == _ts(17, 9, 15)
    assert fvgs[0].gap_start_ts == _ts(17, 9, 0)
    assert fvgs[0].direction == "bullish"


def test_overlapping_triples_both_returned() -> None:
    bars = [
        _k(_ts(17, 9, 0), 100.0, 90.0, close=95.0),
        _k(_ts(17, 9, 5), 102.0, 95.0, close=100.0),
        _k(_ts(17, 9, 10), 120.0, 110.0, close=115.0),
        _k(_ts(17, 9, 15), 130.0, 115.0, close=125.0),
    ]
    fvgs = compute(bars)
    assert len(fvgs) == 2
    assert fvgs[0].gap_start_ts == _ts(17, 9, 0)
    assert fvgs[0].formed_at == _ts(17, 9, 10)
    assert fvgs[0].bottom == 100.0
    assert fvgs[0].top == 110.0
    assert fvgs[1].gap_start_ts == _ts(17, 9, 5)
    assert fvgs[1].formed_at == _ts(17, 9, 15)
    assert fvgs[1].bottom == 102.0
    assert fvgs[1].top == 115.0


def test_stepwise_untouched_mitigated_filled() -> None:
    bars = _bullish_abc() + [
        _k(_ts(17, 9, 15), 112.0, 105.0, close=108.0),
        _k(_ts(17, 9, 20), 108.0, 100.0, close=102.0),
    ]
    mitigated = compute(bars[:-1])[0]
    assert mitigated.state == "mitigated"
    assert mitigated.mitigated_ts == _ts(17, 9, 15)
    assert mitigated.filled_ts is None

    filled = compute(bars)[0]
    assert filled.state == "filled"
    assert filled.mitigated_ts == _ts(17, 9, 15)
    assert filled.filled_ts == _ts(17, 9, 20)


def test_single_bar_fills_sets_both_timestamps() -> None:
    bars = _bullish_abc() + [_k(_ts(17, 9, 15), 112.0, 99.0, close=108.0)]
    fvg = compute(bars)[0]
    assert fvg.state == "filled"
    assert fvg.mitigated_ts == _ts(17, 9, 15)
    assert fvg.filled_ts == _ts(17, 9, 15)


def test_filled_is_terminal() -> None:
    bars = _bullish_abc() + [
        _k(_ts(17, 9, 15), 112.0, 99.0, close=108.0),
        _k(_ts(17, 9, 20), 130.0, 80.0, close=90.0),
    ]
    fvg = compute(bars)[0]
    assert fvg.state == "filled"
    assert fvg.mitigated_ts == _ts(17, 9, 15)
    assert fvg.filled_ts == _ts(17, 9, 15)


def test_near_end_touch_stays_untouched() -> None:
    bars = _bullish_abc() + [_k(_ts(17, 9, 15), 120.0, 110.0, close=115.0)]
    fvg = compute(bars)[0]
    assert fvg.state == "untouched"
    assert fvg.mitigated_ts is None


def test_far_end_touch_is_filled() -> None:
    bars = _bullish_abc() + [_k(_ts(17, 9, 15), 120.0, 100.0, close=108.0)]
    fvg = compute(bars)[0]
    assert fvg.state == "filled"
    assert fvg.filled_ts == _ts(17, 9, 15)


def test_as_of_at_formed_at_is_untouched() -> None:
    bars = _bullish_abc() + [_k(_ts(17, 9, 15), 112.0, 99.0, close=108.0)]
    at_form = compute(bars[:-1])[0]
    assert at_form.formed_at == _ts(17, 9, 10)
    assert at_form.state == "untouched"
    assert compute(bars)[0].state == "filled"


def test_night_bar_can_fill_day_fvg() -> None:
    bars = [
        _k(_ts(17, 13, 35), 100.0, 90.0, close=95.0),
        _k(_ts(17, 13, 40), 120.0, 105.0, close=115.0),
        _k(_ts(17, 13, 45), 125.0, 110.0, close=120.0),
        _k(_ts(17, 15, 5), 112.0, 99.0, close=108.0),
    ]
    fvgs = compute(bars)
    assert len(fvgs) == 1
    fvg = fvgs[0]
    assert fvg.session == "day"
    assert fvg.formed_at == _ts(17, 13, 45)
    assert fvg.state == "filled"
    assert fvg.filled_ts == _ts(17, 15, 5)
    assert fvg.mitigated_ts == _ts(17, 15, 5)


def test_bearish_near_end_touch_stays_untouched() -> None:
    bars = [
        _k(_ts(17, 9, 0), 120.0, 110.0, close=115.0),
        _k(_ts(17, 9, 5), 108.0, 95.0, close=100.0),
        _k(_ts(17, 9, 10), 100.0, 90.0, close=92.0),
        _k(_ts(17, 9, 15), 100.0, 90.0, close=95.0),
    ]
    fvg = compute(bars)[0]
    assert fvg.direction == "bearish"
    assert fvg.bottom == 100.0
    assert fvg.state == "untouched"


def test_bearish_far_end_touch_is_filled() -> None:
    bars = [
        _k(_ts(17, 9, 0), 120.0, 110.0, close=115.0),
        _k(_ts(17, 9, 5), 108.0, 95.0, close=100.0),
        _k(_ts(17, 9, 10), 100.0, 90.0, close=92.0),
        _k(_ts(17, 9, 15), 110.0, 90.0, close=105.0),
    ]
    fvg = compute(bars)[0]
    assert fvg.state == "filled"
    assert fvg.filled_ts == _ts(17, 9, 15)
