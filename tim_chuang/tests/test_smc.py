from __future__ import annotations

from datetime import datetime

from tfx_trading.indicators.smc import compute
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


def test_empty_bars() -> None:
    levels = compute([])
    assert levels.swings == []
    assert levels.pdh is None


def test_open_bars_are_not_swings_earliest_is_0900() -> None:
    bars = [
        _k(_ts(17, 8, 50), 10, 9),
        _k(_ts(17, 8, 55), 11, 9),
        _k(_ts(17, 9, 0), 20, 10),
        _k(_ts(17, 9, 5), 12, 9),
        _k(_ts(17, 9, 10), 11, 9),
    ]
    levels = compute(bars)
    assert all(s.timestamp != _ts(17, 8, 50) for s in levels.swings)
    assert all(s.timestamp != _ts(17, 8, 55) for s in levels.swings)
    assert len(levels.swings) == 1
    swing = levels.swings[0]
    assert swing.timestamp == _ts(17, 9, 0)
    assert swing.confirmed_at == _ts(17, 9, 10)
    assert swing.side == "high"
    assert swing.price == 20
    assert swing.significant is False


def test_equal_high_is_not_swing() -> None:
    bars = [
        _k(_ts(17, 9, 0), 10, 8),
        _k(_ts(17, 9, 5), 11, 8),
        _k(_ts(17, 9, 10), 20, 9),
        _k(_ts(17, 9, 15), 20, 9),
        _k(_ts(17, 9, 20), 11, 8),
        _k(_ts(17, 9, 25), 10, 8),
        _k(_ts(17, 9, 30), 10, 8),
    ]
    highs = [s for s in compute(bars).swings if s.side == "high"]
    assert highs == []


def test_same_side_collapse_keeps_more_extreme() -> None:
    bars = [
        _k(_ts(17, 9, 0), 10, 8),
        _k(_ts(17, 9, 5), 11, 8),
        _k(_ts(17, 9, 10), 25, 9),
        _k(_ts(17, 9, 15), 12, 8),
        _k(_ts(17, 9, 20), 13, 8),
        _k(_ts(17, 9, 25), 30, 9),
        _k(_ts(17, 9, 30), 14, 8),
        _k(_ts(17, 9, 35), 13, 8),
    ]
    highs = [s for s in compute(bars).swings if s.side == "high"]
    assert len(highs) == 1
    assert highs[0].timestamp == _ts(17, 9, 25)
    assert highs[0].price == 30


def test_dual_high_and_low_is_skipped() -> None:
    bars = [
        _k(_ts(17, 9, 0), 10, 9),
        _k(_ts(17, 9, 5), 11, 8),
        _k(_ts(17, 9, 10), 50, 2),
        _k(_ts(17, 9, 15), 12, 7),
        _k(_ts(17, 9, 20), 11, 8),
    ]
    assert compute(bars).swings == []


def test_seam_can_be_tv_pivot() -> None:
    bars = [
        _k(_ts(17, 13, 25), 10, 9),
        _k(_ts(17, 13, 30), 11, 9),
        _k(_ts(17, 13, 35), 12, 9),
        _k(_ts(17, 13, 40), 13, 9),
        _k(_ts(17, 13, 45), 40, 9),
        _k(_ts(17, 15, 5), 14, 9),
        _k(_ts(17, 15, 10), 13, 9),
        _k(_ts(17, 15, 15), 12, 9),
        _k(_ts(17, 15, 20), 11, 9),
        _k(_ts(17, 15, 25), 10, 9),
    ]
    highs = [s for s in compute(bars).swings if s.timestamp == _ts(17, 13, 45)]
    assert len(highs) == 1
    assert highs[0].side == "high"
    assert highs[0].price == 40
    assert highs[0].confirmed_at == _ts(17, 15, 10)


def test_open_can_be_tv_pivot_using_overnight() -> None:
    bars = [
        _k(_ts(15, 4, 50), 10, 8),
        _k(_ts(15, 4, 55), 11, 8),
        _k(_ts(15, 5, 0), 12, 8),
        _k(_ts(17, 8, 50), 20, 9),
        _k(_ts(17, 8, 55), 13, 9),
        _k(_ts(17, 9, 0), 12, 9),
    ]
    highs = [s for s in compute(bars).swings if s.timestamp == _ts(17, 8, 50)]
    assert len(highs) == 1
    assert highs[0].side == "high"
    assert highs[0].price == 20
    assert highs[0].confirmed_at == _ts(17, 9, 0)


def test_missing_5m_is_still_index_neighbor() -> None:
    bars = [
        _k(_ts(17, 8, 50), 10, 9),
        _k(_ts(17, 8, 55), 11, 9),
        _k(_ts(17, 9, 0), 30, 10),
        _k(_ts(17, 9, 15), 12, 9),
        _k(_ts(17, 9, 20), 13, 9),
    ]
    highs = [s for s in compute(bars).swings if s.timestamp == _ts(17, 9, 0)]
    assert len(highs) == 1
    assert highs[0].confirmed_at == _ts(17, 9, 20)


def test_prev_night_uses_full_session_across_hole() -> None:
    bars = [
        _k(_ts(13, 22, 45), 46568, 45000),
        _k(_ts(14, 3, 0), 100, 90),
        _k(_ts(14, 3, 5), 46463, 91),
        _k(_ts(14, 4, 55), 80, 70),
        _k(_ts(14, 5, 0), 81, 71),
        _k(_ts(14, 8, 50), 200, 190),
        _k(_ts(14, 8, 55), 201, 189),
    ]
    levels = compute(bars)
    assert levels.prev_night_high is not None
    assert levels.prev_night_high.price == 46568
    assert levels.prev_night_high.source_ts == _ts(13, 22, 45)
    assert levels.prev_night_low is not None
    assert levels.prev_night_low.price == 70
    assert levels.session_high is not None
    assert levels.session_high.developing is True


def test_pdh_none_without_prior_day() -> None:
    bars = [
        _k(_ts(17, 13, 40), 200, 150),
        _k(_ts(17, 13, 45), 201, 149),
    ]
    levels = compute(bars)
    assert levels.pdh is None
    assert levels.pdl is None
    assert levels.prev_night_high is None
    assert levels.session_high is not None
    assert levels.session_high.developing is False
    assert levels.session_high.price == 201


def test_pdh_from_last_completed_day_in_input() -> None:
    bars = [
        _k(_ts(14, 13, 40), 100, 90),
        _k(_ts(14, 13, 45), 101, 91),
        _k(_ts(15, 4, 55), 80, 70),
        _k(_ts(15, 5, 0), 81, 71),
        _k(_ts(17, 13, 40), 200, 150),
        _k(_ts(17, 13, 45), 201, 149),
    ]
    levels = compute(bars)
    assert levels.pdh is not None
    assert levels.pdh.price == 101
    assert levels.pdh.source_ts == _ts(14, 13, 45)
    assert levels.pdh.developing is False
    assert levels.pdl is not None
    assert levels.pdl.price == 90
    assert levels.prev_night_high is not None
    assert levels.prev_night_high.price == 81
    assert levels.prev_night_low is not None
    assert levels.prev_night_low.price == 70
    assert levels.session_high is not None
    assert levels.session_high.price == 201
    assert levels.session_high.developing is False
    assert levels.session_low is not None
    assert levels.session_low.price == 149
    assert levels.session_low.developing is False


def test_developing_true_before_session_close() -> None:
    bars = [
        _k(_ts(14, 13, 40), 100, 90),
        _k(_ts(14, 13, 45), 101, 91),
        _k(_ts(17, 8, 50), 200, 190),
        _k(_ts(17, 8, 55), 201, 189),
    ]
    levels = compute(bars)
    assert levels.pdh is not None
    assert levels.pdh.price == 101
    assert levels.session_high is not None
    assert levels.session_high.developing is True
    assert levels.session_low is not None
    assert levels.session_low.developing is True


def test_second_swing_significant_by_min_points() -> None:
    bars = [
        _k(_ts(17, 9, 0), 10, 9),
        _k(_ts(17, 9, 5), 11, 9),
        _k(_ts(17, 9, 10), 12, 9),
        _k(_ts(17, 9, 15), 11, 8),
        _k(_ts(17, 9, 20), 10, 5),
        _k(_ts(17, 9, 25), 11, 8),
        _k(_ts(17, 9, 30), 40, 9),
        _k(_ts(17, 9, 35), 11, 8),
        _k(_ts(17, 9, 40), 10, 8),
    ]
    highs = [s for s in compute(bars, min_points=20).swings if s.side == "high"]
    assert highs[0].significant is False
    assert highs[0].price == 12
    assert len(highs) == 2
    assert highs[1].significant is True
    assert highs[1].price == 40
