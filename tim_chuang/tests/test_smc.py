from __future__ import annotations

from datetime import datetime

from tfx_trading.indicators.smc import Swing, _structure_event, compute
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
    assert levels.last_bar is None
    assert levels.dealing_range is None
    assert levels.events == []


def test_last_bar_is_filtered_session_tail() -> None:
    bars = [
        _k(_ts(17, 13, 40), 200, 150, close=160),
        _k(_ts(17, 13, 45), 201, 149, close=170),
    ]
    last = compute(bars).last_bar
    assert last is not None
    assert last.timestamp == _ts(17, 13, 45)
    assert last.close == 170


def test_last_bar_skips_non_session_tail() -> None:
    bars = [
        _k(_ts(17, 13, 45), 201, 149, close=170),
        _k(_ts(17, 14, 0), 300, 290, close=999),
    ]
    last = compute(bars).last_bar
    assert last is not None
    assert last.timestamp == _ts(17, 13, 45)
    assert last.close == 170


def test_last_bar_none_when_only_non_session() -> None:
    levels = compute([_k(_ts(17, 14, 0), 300, 290, close=999)])
    assert levels.last_bar is None
    assert levels.swings == []


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


def _prior_day_pdh_101() -> list[KBar]:
    return [
        _k(_ts(14, 13, 40), 100, 90, close=95),
        _k(_ts(14, 13, 45), 101, 91, close=96),
    ]


def test_pdh_swept_by_wick() -> None:
    levels = compute(
        _prior_day_pdh_101()
        + [_k(_ts(17, 8, 50), 102, 90, close=100), _k(_ts(17, 8, 55), 100, 90, close=99)]
    )
    assert levels.pdh is not None
    assert levels.pdh.interact == "swept"
    assert levels.pdh.interact_ts == _ts(17, 8, 50)


def test_pdh_taken_on_close_through() -> None:
    levels = compute(
        _prior_day_pdh_101()
        + [
            _k(_ts(17, 8, 50), 110, 90, close=102),
            _k(_ts(17, 9, 0), 120, 90, close=115),
        ]
    )
    assert levels.pdh is not None
    assert levels.pdh.interact == "taken"
    assert levels.pdh.interact_ts == _ts(17, 8, 50)


def test_pdh_untouched_when_current_stays_below() -> None:
    levels = compute(
        _prior_day_pdh_101()
        + [_k(_ts(17, 8, 50), 100, 90, close=95), _k(_ts(17, 8, 55), 99, 91, close=96)]
    )
    assert levels.pdh is not None
    assert levels.pdh.interact == "untouched"
    assert levels.pdh.interact_ts is None


def test_pdh_swept_then_taken_uses_close_through_ts() -> None:
    levels = compute(
        _prior_day_pdh_101()
        + [
            _k(_ts(17, 8, 50), 102, 90, close=100),
            _k(_ts(17, 8, 55), 110, 90, close=105),
        ]
    )
    assert levels.pdh is not None
    assert levels.pdh.interact == "taken"
    assert levels.pdh.interact_ts == _ts(17, 8, 55)


def test_pdh_equal_high_is_untouched() -> None:
    levels = compute(
        _prior_day_pdh_101()
        + [_k(_ts(17, 8, 50), 101, 90, close=100), _k(_ts(17, 8, 55), 100, 90, close=99)]
    )
    assert levels.pdh is not None
    assert levels.pdh.interact == "untouched"
    assert levels.pdh.interact_ts is None


def test_session_high_and_low_interact_none() -> None:
    levels = compute(
        _prior_day_pdh_101()
        + [_k(_ts(17, 13, 40), 200, 150, close=160), _k(_ts(17, 13, 45), 201, 149, close=170)]
    )
    assert levels.session_high is not None
    assert levels.session_high.interact is None
    assert levels.session_low is not None
    assert levels.session_low.interact is None


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


def _range_series(close: float) -> list[KBar]:
    """Non-sig SH 30, sig SL 5, sig SH 40. eq = 22.5. Last bar is not a 9:40 neighbor."""
    last_high, last_low = (24.0, 18.0) if 18 <= close <= 24 else (max(24.0, close), min(18.0, close))
    return [
        _k(_ts(17, 9, 0), 20, 19, close=20),
        _k(_ts(17, 9, 5), 21, 19, close=21),
        _k(_ts(17, 9, 10), 30, 19, close=30),
        _k(_ts(17, 9, 15), 22, 18, close=22),
        _k(_ts(17, 9, 20), 21, 18, close=21),
        _k(_ts(17, 9, 25), 22, 5, close=10),
        _k(_ts(17, 9, 30), 23, 18, close=20),
        _k(_ts(17, 9, 35), 24, 18, close=20),
        _k(_ts(17, 9, 40), 40, 19, close=30),
        _k(_ts(17, 9, 45), 25, 18, close=22),
        _k(_ts(17, 9, 50), 24, 18, close=22),
        _k(_ts(17, 9, 55), 24, 18, close=22),
        _k(_ts(17, 10, 0), 24, 18, close=22),
        _k(_ts(17, 10, 5), last_high, last_low, close=close),
    ]


def test_dealing_range_discount_inside() -> None:
    rng = compute(_range_series(10), min_points=20).dealing_range
    assert rng is not None
    assert rng.high == 40
    assert rng.high_ts == _ts(17, 9, 40)
    assert rng.low == 5
    assert rng.low_ts == _ts(17, 9, 25)
    assert rng.eq == 22.5
    assert rng.position == "discount"


def test_dealing_range_premium_inside() -> None:
    rng = compute(_range_series(30), min_points=20).dealing_range
    assert rng is not None
    assert rng.eq == 22.5
    assert rng.position == "premium"


def test_dealing_range_equilibrium() -> None:
    rng = compute(_range_series(22.5), min_points=20).dealing_range
    assert rng is not None
    assert rng.eq == 22.5
    assert rng.position == "equilibrium"


def test_dealing_range_outside_below() -> None:
    rng = compute(_range_series(4), min_points=20).dealing_range
    assert rng is not None
    assert rng.position == "outside"


def test_dealing_range_outside_above() -> None:
    rng = compute(_range_series(41), min_points=20).dealing_range
    assert rng is not None
    assert rng.position == "outside"


def test_dealing_range_none_when_only_one_significant_side() -> None:
    bars = [
        _k(_ts(17, 9, 0), 20, 19, close=20),
        _k(_ts(17, 9, 5), 21, 19, close=21),
        _k(_ts(17, 9, 10), 30, 19, close=30),
        _k(_ts(17, 9, 15), 22, 18, close=22),
        _k(_ts(17, 9, 20), 21, 18, close=21),
        _k(_ts(17, 9, 25), 22, 5, close=10),
        _k(_ts(17, 9, 30), 23, 18, close=20),
        _k(_ts(17, 9, 35), 24, 18, close=20),
    ]
    levels = compute(bars, min_points=20)
    assert levels.dealing_range is None


def test_structure_first_close_through_high_is_choch() -> None:
    levels = compute(_range_series(45), min_points=20)
    assert len(levels.events) == 1
    ev = levels.events[0]
    assert ev.kind == "choch"
    assert ev.direction == "bullish"
    assert ev.ts == _ts(17, 10, 5)
    assert ev.broken_price == 40
    assert ev.broken_swing_ts == _ts(17, 9, 40)
    assert ev.scope == "internal"


def test_structure_wick_through_high_is_not_event() -> None:
    bars = _range_series(22)[:-1] + [_k(_ts(17, 10, 5), 45, 18, close=39)]
    assert compute(bars, min_points=20).events == []


def test_structure_ignores_non_significant_high() -> None:
    bars = [
        _k(_ts(17, 9, 0), 20, 19, close=20),
        _k(_ts(17, 9, 5), 21, 19, close=21),
        _k(_ts(17, 9, 10), 30, 19, close=30),
        _k(_ts(17, 9, 15), 22, 18, close=22),
        _k(_ts(17, 9, 20), 21, 18, close=21),
        _k(_ts(17, 9, 25), 22, 5, close=10),
        _k(_ts(17, 9, 30), 35, 18, close=35),
        _k(_ts(17, 9, 35), 24, 18, close=20),
    ]
    assert compute(bars, min_points=20).events == []


def test_structure_second_close_through_high_is_bos() -> None:
    bars = _range_series(22)[:-1] + [
        _k(_ts(17, 10, 5), 45, 18, close=45),
        _k(_ts(17, 10, 10), 45, 18, close=22),
        _k(_ts(17, 10, 15), 45, 18, close=22),
        _k(_ts(17, 10, 20), 24, 10, close=14),
        _k(_ts(17, 10, 25), 24, 18, close=20),
        _k(_ts(17, 10, 30), 24, 18, close=20),
        _k(_ts(17, 10, 35), 60, 19, close=50),
        _k(_ts(17, 10, 40), 30, 18, close=24),
        _k(_ts(17, 10, 45), 28, 18, close=24),
        _k(_ts(17, 10, 50), 28, 18, close=65),
    ]
    events = compute(bars, min_points=20).events
    assert [e.kind for e in events] == ["choch", "bos"]
    assert events[0].direction == "bullish"
    assert events[0].broken_price == 40
    assert events[0].ts == _ts(17, 10, 5)
    assert events[1].direction == "bullish"
    assert events[1].broken_price == 60
    assert events[1].ts == _ts(17, 10, 50)


def test_structure_close_through_low_after_bullish_is_choch() -> None:
    bars = _range_series(22)[:-1] + [
        _k(_ts(17, 10, 5), 45, 18, close=45),
        _k(_ts(17, 10, 10), 45, 18, close=22),
        _k(_ts(17, 10, 15), 45, 1, close=4),
    ]
    events = compute(bars, min_points=20).events
    assert events[0].kind == "choch"
    assert events[0].direction == "bullish"
    assert events[0].broken_price == 40
    assert events[-1].kind == "choch"
    assert events[-1].direction == "bearish"
    assert events[-1].broken_price == 5
    assert events[-1].ts == _ts(17, 10, 15)


def test_structure_external_when_broken_equals_session_high() -> None:
    swing = Swing(
        timestamp=_ts(17, 9, 40),
        confirmed_at=_ts(17, 9, 50),
        side="high",
        price=40,
        significant=True,
        session="day",
    )
    ev = _structure_event("bullish", _ts(17, 10, 5), swing, None, 40, 5)
    assert ev.scope == "external"
