"""Unit tests for vwap-stretch-fade strategy."""

from __future__ import annotations

import datetime
import unittest

from trading_engine.core.types import MarketSnapshot, PositionSnapshot, RiskGate
from trading_engine.testing.defaults import default_runtime_config

from strategy_vwap_stretch_fade import StretchFadeParams, VwapStretchFadeStrategy


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
    price: float = 18060.0,
    vwap: float = 18000.0,
    atr: float = 25.0,
    ts: int = 1_700_000_000,
) -> MarketSnapshot:
    return MarketSnapshot(
        ts=ts,
        price=price,
        dt=datetime.datetime.fromtimestamp(ts, tz=datetime.UTC),
        vwap=vwap,
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


class TestStretchFadeEntry(unittest.TestCase):
    def setUp(self) -> None:
        cfg = default_runtime_config()
        cfg.stretch_k = 2.0
        cfg.reset_z = 0.5
        cfg.cooldown_sec = 60
        self.strategy = VwapStretchFadeStrategy(params=StretchFadeParams.from_runtime_config(cfg))

    def test_fade_short_when_above_vwap(self) -> None:
        # z = (18060-18000)/25 = 2.4 >= 2.0
        mkt = _mk_market(price=18060.0, vwap=18000.0, atr=25.0)
        sig, _ = self.strategy.evaluate(
            mkt,
            _flat_position(),
            _flat_risk(),
            (150.0, 1.0, 150.0),
            session_force_flatten_time=datetime.time(13, 44),
            max_daily_loss_points=120.0,
        )
        self.assertIsNotNone(sig)
        assert sig is not None
        self.assertEqual(sig.action, "Sell")
        self.assertEqual(sig.audit.reason, "vwap_stretch_fade")

    def test_no_entry_when_z_below_stretch(self) -> None:
        mkt = _mk_market(price=18040.0, vwap=18000.0, atr=25.0)  # z=1.6
        sig, _ = self.strategy.evaluate(
            mkt,
            _flat_position(),
            _flat_risk(),
            (150.0, 1.0, 150.0),
            session_force_flatten_time=datetime.time(13, 44),
            max_daily_loss_points=120.0,
        )
        self.assertIsNone(sig)

    def test_cooldown_blocks_second_entry(self) -> None:
        mkt1 = _mk_market(price=18060.0, ts=1_000)
        sig1, _ = self.strategy.evaluate(
            mkt1,
            _flat_position(),
            _flat_risk(),
            (150.0, 1.0, 150.0),
            session_force_flatten_time=datetime.time(13, 44),
            max_daily_loss_points=120.0,
        )
        self.assertIsNotNone(sig1)
        mkt2 = _mk_market(price=18060.0, ts=1_030)
        sig2, _ = self.strategy.evaluate(
            mkt2,
            _flat_position(),
            _flat_risk(),
            (150.0, 1.0, 150.0),
            session_force_flatten_time=datetime.time(13, 44),
            max_daily_loss_points=120.0,
        )
        self.assertIsNone(sig2)

    def test_stretch_fade_records_momentum_observability(self) -> None:
        obs = _ObsSpy()
        cfg = default_runtime_config()
        cfg.stretch_k = 2.0
        strategy = VwapStretchFadeStrategy(
            params=StretchFadeParams.from_runtime_config(cfg),
            obs=obs,
        )
        mkt = _mk_market(price=18060.0, vwap=18000.0, atr=25.0)
        sig, _ = strategy.evaluate(
            mkt,
            _flat_position(),
            _flat_risk(),
            (150.0, 1.0, 150.0),
            session_force_flatten_time=datetime.time(13, 44),
            max_daily_loss_points=120.0,
        )
        self.assertIsNotNone(sig)
        self.assertEqual(obs.triggers, 1)
        self.assertEqual(obs.entries, 1)


if __name__ == "__main__":
    unittest.main()
