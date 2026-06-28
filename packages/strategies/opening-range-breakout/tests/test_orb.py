"""Unit tests for opening-range-breakout strategy."""

from __future__ import annotations

import datetime
import unittest

from trading_engine.core.types import MarketSnapshot, PositionSnapshot, RiskGate
from trading_engine.testing.defaults import default_runtime_config

from strategy_opening_range_breakout import OpeningRangeBreakoutStrategy, OrbParams
from strategy_opening_range_breakout.atr_utils import atr_at_bar_index, atr_series_from_bars
from strategy_opening_range_breakout.orb_logic import (
    MinuteBar,
    OrbDayState,
    finalize_range,
    on_bar_closed,
    reset_day_state,
)
from strategy_opening_range_breakout.session_atr import SessionAtrTracker


class _ObsSpy:
    def __init__(self) -> None:
        self.triggers = 0
        self.entries = 0

    def record_momentum_trigger(self) -> None:
        self.triggers += 1

    def record_momentum_entry(self) -> None:
        self.entries += 1


def _mk_market(
    *,
    hour: int,
    minute: int,
    price: float = 18000.0,
    atr: float = 30.0,
    day: int = 1,
) -> MarketSnapshot:
    ts = int(datetime.datetime(2026, 4, day, hour, minute, 30).timestamp())
    return MarketSnapshot(
        ts=ts,
        price=price,
        dt=datetime.datetime(2026, 4, day, hour, minute, 30),
        vwap=17990.0,
        vol_1s=10,
        buy_vol_1s=5,
        sell_vol_1s=5,
        current_atr=atr,
        trend_dir="Flat",
        trend_strength=0.0,
    )


def _flat_risk(**kwargs) -> RiskGate:
    base = dict(
        api_connected=True,
        in_trading_session=True,
        is_pending=False,
        exit_pending=False,
        cooldown_active=False,
        block_new_entry=False,
        after_flatten_time=False,
        force_flatten=False,
        daily_pnl=0.0,
        consecutive_loss=0,
        reconnect_warmup_active=False,
        atr_stale=False,
        settling=False,
        position_unconfirmed=False,
    )
    base.update(kwargs)
    return RiskGate(**base)


def _flat_position() -> PositionSnapshot:
    return PositionSnapshot(
        has_position=False,
        position_dir="Flat",
        qty=0,
        entry_price=0.0,
        entry_exchange_ts=0,
        trailing_peak=0.0,
        ticks_since_entry=0,
    )


class TestOrbLogic(unittest.TestCase):
    def test_short_break_after_range(self) -> None:
        state = OrbDayState()
        reset_day_state(state, datetime.date(2026, 4, 1))
        session_start = datetime.time(8, 45)
        for m in range(15):
            on_bar_closed(
                state,
                MinuteBar(
                    bar_time=datetime.time(8, 45 + m),
                    open=100,
                    high=102,
                    low=100,
                    close=101,
                ),
                session_start=session_start,
                range_minutes=15,
                buffer_atr_k=0.0,
                min_range_atr_k=0.01,
                atr=30.0,
                min_atr_floor=25.0,
            )
        direction = on_bar_closed(
            state,
            MinuteBar(
                bar_time=datetime.time(9, 0),
                open=99,
                high=99,
                low=97,
                close=97,
                atr=30.0,
            ),
            session_start=session_start,
            range_minutes=15,
            buffer_atr_k=0.0,
            min_range_atr_k=0.01,
            atr=30.0,
            min_atr_floor=25.0,
        )
        self.assertEqual(direction, "Short")

    def test_reset_clears_range_atr(self) -> None:
        state = OrbDayState(range_atr=42.0)
        reset_day_state(state, datetime.date(2026, 4, 2))
        self.assertEqual(state.range_atr, 0.0)

    def test_finalize_range_uses_atr_floor(self) -> None:
        state = OrbDayState(
            range_high=110.0,
            range_low=100.0,
            range_bars=15,
            range_atr=10.0,
        )
        finalize_range(
            state,
            min_range_atr_k=0.5,
            range_minutes=15,
            min_atr_floor=25.0,
        )
        self.assertTrue(state.range_skipped)

    def test_atr_series_sma_tr(self) -> None:
        bars = [(10.0, 8.0, 9.0), (11.0, 9.0, 10.0), (12.0, 10.0, 11.0)]
        atrs = atr_series_from_bars(bars, period=2)
        self.assertEqual(len(atrs), 1)
        self.assertAlmostEqual(atrs[0], 2.0)

    def test_atr_at_bar_index_floors(self) -> None:
        bars = [(10.0, 9.0, 9.5)]
        self.assertEqual(atr_at_bar_index(bars, 0, period=20, min_atr_floor=25.0), 25.0)

    def test_session_atr_tracker(self) -> None:
        tracker = SessionAtrTracker(atr_period=2, min_atr_floor=1.0)
        tracker.on_bar_closed(MinuteBar(datetime.time(8, 45), 10, 11, 9, 10))
        tracker.on_bar_closed(MinuteBar(datetime.time(8, 46), 10, 12, 10, 11))
        atr2 = tracker.on_bar_closed(
            MinuteBar(datetime.time(8, 47), 11, 13, 10, 12)
        )
        self.assertAlmostEqual(atr2, 2.5)


class TestOrbStrategyEntry(unittest.TestCase):
    def test_emits_entry_on_breakout_bar(self) -> None:
        cfg = default_runtime_config()
        obs = _ObsSpy()
        strat = OpeningRangeBreakoutStrategy(params=OrbParams.from_runtime_config(cfg), obs=obs)

        # Build 30m range 08:45–09:14 with width >= 15 pts
        for m in range(30):
            total = 45 + m
            hour = 8 + total // 60
            minute = total % 60
            price = 18020.0 if m % 2 == 0 else 18000.0
            strat.evaluate(
                _mk_market(hour=hour, minute=minute, price=price),
                _flat_position(),
                _flat_risk(),
                (0, 0, 0),
                session_force_flatten_time=datetime.time(13, 44),
                max_daily_loss_points=120,
            )

        # First post-range bar breaks down
        signal, _ = strat.evaluate(
            _mk_market(hour=9, minute=15, price=17970.0),
            _flat_position(),
            _flat_risk(),
            (0, 0, 0),
            session_force_flatten_time=datetime.time(13, 44),
            max_daily_loss_points=120,
        )
        # Need minute rollover to close 9:15 bar — feed 9:16 tick
        self.assertIsNone(signal)
        signal2, _ = strat.evaluate(
            _mk_market(hour=9, minute=16, price=17970.0),
            _flat_position(),
            _flat_risk(),
            (0, 0, 0),
            session_force_flatten_time=datetime.time(13, 44),
            max_daily_loss_points=120,
        )
        self.assertIsNotNone(signal2)
        assert signal2 is not None
        self.assertEqual(signal2.action, "Sell")
        self.assertEqual(obs.entries, 1)


if __name__ == "__main__":
    unittest.main()
