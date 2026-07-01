"""GudtRouteAStrategy replay cursor — must not rewind on engine reset()."""

from __future__ import annotations

import datetime
import unittest
from unittest import mock

from trading_engine.core.types import MarketSnapshot, PositionSnapshot, RiskGate

from strategy_gudt_route_a.params import GudtRouteAParams
from strategy_gudt_route_a.strategy import GudtRouteAStrategy
from strategy_gudt_route_a.types import DayReplayPlan, TradeEvent


def _market(ts: int, price: float = 22000.0) -> MarketSnapshot:
    dt = datetime.datetime.fromtimestamp(ts)
    return MarketSnapshot(
        ts=ts,
        price=price,
        dt=dt,
        vwap=price,
        vol_1s=100,
        buy_vol_1s=80,
        sell_vol_1s=20,
        current_atr=50.0,
        trend_dir="Up",
        trend_strength=1.0,
    )


def _flat() -> PositionSnapshot:
    return PositionSnapshot(
        position_dir="Flat",
        has_position=False,
        entry_price=0.0,
        trailing_peak=0.0,
        entry_exchange_ts=0,
        ticks_since_entry=0,
    )


def _long(entry: float = 22000.0) -> PositionSnapshot:
    return PositionSnapshot(
        position_dir="Long",
        has_position=True,
        entry_price=entry,
        trailing_peak=entry,
        entry_exchange_ts=900,
        ticks_since_entry=10,
    )


def _risk() -> RiskGate:
    return RiskGate(
        api_connected=True,
        is_pending=False,
        exit_pending=False,
        cooldown_active=False,
        in_trading_session=True,
        block_new_entry=False,
        consecutive_loss=0,
        daily_pnl=0.0,
        after_flatten_time=False,
        force_flatten=False,
    )


class TestGudtReplayCursor(unittest.TestCase):
    def _strategy_with_plan(self) -> GudtRouteAStrategy:
        entry_ts = 1780278300
        exit_ts = 1780280837
        plan = DayReplayPlan(
            day="2026-06-01",
            path="p0+sealed",
            events=[
                TradeEvent(ts=entry_ts, action="Buy", price=46050.0, leg="long_entry", reason="p0"),
                TradeEvent(
                    ts=exit_ts,
                    action="Sell",
                    price=46289.0,
                    leg="long_exit",
                    reason="trail_stop",
                ),
            ],
        )
        params = GudtRouteAParams(_cfg=mock.Mock())
        strat = GudtRouteAStrategy(params=params, day_plans={"2026-06-01": plan})
        strat._ensure_day(_market(entry_ts))
        return strat

    def test_reset_is_noop_for_replay_cursor(self) -> None:
        strat = self._strategy_with_plan()
        strat._event_idx = 1
        strat.reset()
        self.assertEqual(strat._current_day, "2026-06-01")
        self.assertEqual(strat._event_idx, 1)
        self.assertEqual(len(strat._pending_events), 2)

    def test_entry_advances_cursor_then_reset_keeps_exit_next(self) -> None:
        strat = self._strategy_with_plan()
        entry_ts = strat._pending_events[0].ts
        exit_ts = strat._pending_events[1].ts
        signal, _ = strat.evaluate(
            _market(entry_ts),
            _flat(),
            _risk(),
            (100.0, 0.8, 0.78),
            session_force_flatten_time=datetime.time(13, 44),
            max_daily_loss_points=120.0,
        )
        self.assertIsNotNone(signal)
        self.assertEqual(signal.action, "Buy")
        self.assertEqual(strat._event_idx, 1)

        strat.reset()  # engine after entry fill

        signal2, _ = strat.evaluate(
            _market(exit_ts),
            _long(46050.0),
            _risk(),
            (100.0, 0.8, 0.78),
            session_force_flatten_time=datetime.time(13, 44),
            max_daily_loss_points=120.0,
        )
        self.assertIsNotNone(signal2)
        self.assertEqual(signal2.action, "Sell")
        self.assertEqual(strat._event_idx, 2)

    def test_after_flatten_does_not_reenter_same_day(self) -> None:
        strat = self._strategy_with_plan()
        entry_ts = strat._pending_events[0].ts
        strat.evaluate(
            _market(entry_ts),
            _flat(),
            _risk(),
            (100.0, 0.8, 0.78),
            session_force_flatten_time=datetime.time(13, 44),
            max_daily_loss_points=120.0,
        )
        strat.reset()

        # Planned exit missed; kernel flattened flat before exit event.
        signal, _ = strat.evaluate(
            _market(entry_ts + 3600),
            _flat(),
            _risk(),
            (100.0, 0.8, 0.78),
            session_force_flatten_time=datetime.time(13, 44),
            max_daily_loss_points=120.0,
        )
        self.assertIsNone(signal)
        self.assertEqual(strat._event_idx, 1)


if __name__ == "__main__":
    unittest.main()
