"""Unit tests for momentum-continuation strategy."""

from __future__ import annotations

import datetime
import unittest

from trading_engine.core.types import MarketSnapshot, PositionSnapshot, RiskGate
from trading_engine.testing.defaults import default_runtime_config

from strategy_momentum_continuation import ContinuationParams, MomentumContinuationStrategy


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
    price: float = 18000.0,
    vol_1s: int = 200,
    buy_vol_1s: int = 170,
    sell_vol_1s: int = 30,
    atr: float = 25.0,
    ts: int = 1_700_000_000,
) -> MarketSnapshot:
    return MarketSnapshot(
        ts=ts,
        price=price,
        dt=datetime.datetime.fromtimestamp(ts, tz=datetime.UTC),
        vwap=price - 2.0,
        vol_1s=vol_1s,
        buy_vol_1s=buy_vol_1s,
        sell_vol_1s=sell_vol_1s,
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


class TestContinuationEntry(unittest.TestCase):
    def setUp(self) -> None:
        cfg = default_runtime_config()
        self.strategy = MomentumContinuationStrategy(
            params=ContinuationParams.from_runtime_config(cfg)
        )

    def test_vol_spike_emits_continuation_entry(self) -> None:
        mkt = _mk_market(vol_1s=200, buy_vol_1s=170)
        sig, _ = self.strategy.evaluate(
            mkt,
            _flat_position(),
            _flat_risk(),
            vol_threshold=(150.0, 1.0, 150.0),
            session_force_flatten_time=datetime.time(13, 44),
            max_daily_loss_points=120.0,
        )
        self.assertIsNotNone(sig)
        assert sig is not None
        self.assertEqual(sig.action, "Buy")
        self.assertEqual(sig.audit.reason, "continuation")

    def test_low_vol_no_entry(self) -> None:
        mkt = _mk_market(vol_1s=10, buy_vol_1s=9)
        sig, _ = self.strategy.evaluate(
            mkt,
            _flat_position(),
            _flat_risk(),
            vol_threshold=(150.0, 1.0, 150.0),
            session_force_flatten_time=datetime.time(13, 44),
            max_daily_loss_points=120.0,
        )
        self.assertIsNone(sig)

    def test_continuation_records_momentum_observability(self) -> None:
        obs = _ObsSpy()
        cfg = default_runtime_config()
        strategy = MomentumContinuationStrategy(
            params=ContinuationParams.from_runtime_config(cfg),
            obs=obs,
        )
        mkt = _mk_market(vol_1s=200, buy_vol_1s=170)
        sig, _ = strategy.evaluate(
            mkt,
            _flat_position(),
            _flat_risk(),
            vol_threshold=(150.0, 1.0, 150.0),
            session_force_flatten_time=datetime.time(13, 44),
            max_daily_loss_points=120.0,
        )
        self.assertIsNotNone(sig)
        self.assertEqual(obs.triggers, 1)
        self.assertEqual(obs.entries, 1)


class TestAtrExits(unittest.TestCase):
    def setUp(self) -> None:
        cfg = default_runtime_config()
        self.strategy = MomentumContinuationStrategy(
            params=ContinuationParams.from_runtime_config(cfg)
        )

    def test_hard_stop_atr_long(self) -> None:
        atr = 20.0
        hard = 0.75 * atr  # 15
        pos = PositionSnapshot(
            has_position=True,
            position_dir="Long",
            qty=1,
            entry_price=18000.0,
            entry_exchange_ts=1000,
            trailing_peak=18010.0,
            ticks_since_entry=100,
        )
        mkt = _mk_market(price=18000.0 - hard - 0.5, atr=atr, ts=2000)
        sig, _ = self.strategy.manage_exit(mkt, pos)
        self.assertIsNotNone(sig)
        assert sig is not None
        self.assertEqual(sig.audit.reason, "stop_loss")

    def test_take_profit_atr_long(self) -> None:
        atr = 20.0
        tp = 2.0 * atr
        pos = PositionSnapshot(
            has_position=True,
            position_dir="Long",
            qty=1,
            entry_price=18000.0,
            entry_exchange_ts=1000,
            trailing_peak=18000.0 + tp,
            ticks_since_entry=100,
        )
        mkt = _mk_market(price=18000.0 + tp + 0.5, atr=atr, ts=2000)
        sig, _ = self.strategy.manage_exit(mkt, pos)
        self.assertIsNotNone(sig)
        assert sig is not None
        self.assertEqual(sig.audit.reason, "take_profit")


if __name__ == "__main__":
    unittest.main()
