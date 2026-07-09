"""Unit tests for strategy_simple (UAT flip)."""

from __future__ import annotations

import datetime
import unittest

from strategy_simple import SimpleParams, SimpleStrategy
from trading_engine.core.types import (
    MarketSnapshot,
    PositionSnapshot,
    RiskGate,
)


def _dt(hour: int, minute: int = 0, second: int = 0, day: int = 9) -> datetime.datetime:
    return datetime.datetime(2026, 7, day, hour, minute, second)


def _market(dt: datetime.datetime, price: float = 18000.0, ts: int | None = None) -> MarketSnapshot:
    return MarketSnapshot(
        ts=int(dt.timestamp()) if ts is None else ts,
        price=price,
        dt=dt,
    )


def _flat() -> PositionSnapshot:
    return PositionSnapshot(
        has_position=False,
        position_dir="None",
        entry_price=0.0,
        trailing_peak=0.0,
        entry_exchange_ts=0,
        ticks_since_entry=0,
        qty=0,
    )


def _long(entry: float = 18000.0, entry_ts: int = 1_000) -> PositionSnapshot:
    return PositionSnapshot(
        has_position=True,
        position_dir="Long",
        entry_price=entry,
        trailing_peak=entry,
        entry_exchange_ts=entry_ts,
        ticks_since_entry=10,
        qty=1,
    )


def _open_risk(**overrides) -> RiskGate:
    base = dict(
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
        reconnect_warmup_active=False,
        settling=False,
        position_unconfirmed=False,
    )
    base.update(overrides)
    return RiskGate(**base)


def _eval(strategy: SimpleStrategy, market: MarketSnapshot, position: PositionSnapshot, **risk_kw):
    return strategy.evaluate(
        market,
        position,
        _open_risk(**risk_kw),
    )


class TestSimpleStrategy(unittest.TestCase):
    def setUp(self) -> None:
        self.params = SimpleParams(flip_interval_sec=300)
        self.strategy = SimpleStrategy(self.params)

    def test_flat_no_prior_fill_buys(self) -> None:
        signal, _ = _eval(self.strategy, _market(_dt(9, 0), ts=1_000), _flat())
        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.action, "Buy")
        self.assertEqual(signal.intent, "entry")
        self.assertEqual(signal.audit.reason, "uat_flip_entry")

    def test_rearm_after_entry_miss(self) -> None:
        first, _ = _eval(self.strategy, _market(_dt(9, 0), ts=1_000), _flat())
        self.assertIsNotNone(first)
        second, _ = _eval(self.strategy, _market(_dt(9, 0, 1), ts=1_001), _flat())
        self.assertIsNotNone(second)

    def test_no_sell_before_interval(self) -> None:
        signal, _ = _eval(
            self.strategy,
            _market(_dt(9, 1), ts=1_100),
            _long(entry_ts=1_000),
        )
        self.assertIsNone(signal)

    def test_sell_after_interval(self) -> None:
        signal, _ = _eval(
            self.strategy,
            _market(_dt(9, 5), ts=1_300),
            _long(entry_ts=1_000),
        )
        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.action, "Sell")
        self.assertEqual(signal.intent, "exit")
        self.assertEqual(signal.audit.reason, "uat_flip_exit")

    def test_resync_long_unknown_entry_ts_waits_interval(self) -> None:
        """After restart/resync, entry_exchange_ts may be 0; must not flip-exit on first tick."""
        long_unknown = _long(entry_ts=0)
        first, _ = _eval(
            self.strategy,
            _market(_dt(9, 0), ts=1_000),
            long_unknown,
        )
        self.assertIsNone(first)
        self.assertEqual(self.strategy._last_fill_ts, 1_000)

        still_waiting, _ = _eval(
            self.strategy,
            _market(_dt(9, 4), ts=1_299),
            long_unknown,
        )
        self.assertIsNone(still_waiting)

        after_interval, _ = _eval(
            self.strategy,
            _market(_dt(9, 5), ts=1_300),
            long_unknown,
        )
        self.assertIsNotNone(after_interval)
        assert after_interval is not None
        self.assertEqual(after_interval.action, "Sell")
        self.assertEqual(after_interval.intent, "exit")

    def test_no_buy_immediately_after_exit_fill(self) -> None:
        # Establish long so transition can be detected.
        _eval(self.strategy, _market(_dt(9, 0), ts=1_000), _long(entry_ts=1_000))
        # Flat again at exit fill time — must wait interval.
        signal, _ = _eval(self.strategy, _market(_dt(9, 5), ts=1_300), _flat())
        self.assertIsNone(signal)

    def test_buy_after_exit_interval(self) -> None:
        _eval(self.strategy, _market(_dt(9, 0), ts=1_000), _long(entry_ts=1_000))
        # Transition tick stamps last_fill at 1300
        _eval(self.strategy, _market(_dt(9, 5), ts=1_300), _flat())
        signal, _ = _eval(self.strategy, _market(_dt(9, 10), ts=1_600), _flat())
        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.action, "Buy")

    def test_force_flatten_returns_none(self) -> None:
        signal, _ = self.strategy.session_force_flatten_signal(
            _market(_dt(13, 44), ts=9_999),
            _long(entry_ts=1_000),
            datetime.time(13, 44),
        )
        self.assertIsNone(signal)

    def test_block_new_entry_blocks_buy_only(self) -> None:
        buy, _ = _eval(
            self.strategy,
            _market(_dt(9, 0), ts=1_000),
            _flat(),
            block_new_entry=True,
        )
        self.assertIsNone(buy)
        sell, _ = _eval(
            self.strategy,
            _market(_dt(9, 5), ts=1_300),
            _long(entry_ts=1_000),
            block_new_entry=True,
        )
        self.assertIsNotNone(sell)

    def test_not_in_session_no_signal(self) -> None:
        signal, _ = _eval(
            self.strategy,
            _market(_dt(9, 0), ts=1_000),
            _flat(),
            in_trading_session=False,
        )
        self.assertIsNone(signal)

    def test_manage_exit_noop(self) -> None:
        signal, _ = self.strategy.manage_exit(
            _market(_dt(9, 0), ts=1_000),
            _long(entry_ts=1_000),
        )
        self.assertIsNone(signal)


if __name__ == "__main__":
    unittest.main()
