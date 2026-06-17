"""Exit grace period: decouple VWAP stop from hard stop after entry (pure)."""

from __future__ import annotations

import datetime
import unittest

from trading_engine.core.types import MarketSnapshot, PositionSnapshot
from trading_engine.testing.defaults import default_test_settings

from strategy_vwap_momentum import StrategyParams, VWAPMomentumStrategy


def _make_strategy_and_settings():
    s = default_test_settings()
    try:
        from trading_engine.testing.defaults import default_runtime_config

        params = StrategyParams.from_runtime_config(default_runtime_config())
    except Exception:

        class _T:
            pass

        t = _T()
        for k in (
            "vwap_stop_points",
            "hard_stop_points",
            "exit_grace_ticks",
            "exit_grace_sec",
            "atr_vwap_stop_enabled",
            "vwap_stop_points_floor",
            "vwap_stop_atr_k",
            "momentum_timeout_sec",
        ):
            val = getattr(s, k, 0) if k != "momentum_timeout_sec" else getattr(s, k, 180)
            setattr(t, k, val)
        params = StrategyParams(_cfg=t)  # type: ignore

    return VWAPMomentumStrategy(params=params), s


def _mk_market(price: float, vwap: float, ts: int = 1010) -> MarketSnapshot:
    return MarketSnapshot(
        ts=ts,
        price=price,
        dt=datetime.datetime.fromtimestamp(ts, tz=datetime.UTC),
        vwap=vwap,
        vol_1s=10,
        buy_vol_1s=5,
        sell_vol_1s=5,
        current_atr=10.0,
        trend_dir="Flat",
        trend_strength=0.0,
    )


class TestExitGracePeriod(unittest.TestCase):
    def setUp(self) -> None:
        self.strategy, self.s = _make_strategy_and_settings()

    def _long_pos(self, ticks: int = 10, entry_ts: int = 1000) -> PositionSnapshot:
        return PositionSnapshot(
            has_position=True,
            position_dir="Long",
            qty=1,
            entry_price=18000.0,
            entry_exchange_ts=entry_ts,
            trailing_peak=18000.0,
            ticks_since_entry=ticks,
        )

    def test_in_grace_vwap_stop_suppressed(self):
        pos = self._long_pos()
        vwap = 18000.0
        vwap_stop_dist = self.s.vwap_stop_points
        mkt = _mk_market(price=vwap - vwap_stop_dist, vwap=vwap, ts=1010)
        sig, _ = self.strategy.manage_exit(mkt, pos)
        self.assertIsNone(sig)

    def test_in_grace_hard_stop_still_fires(self):
        pos = self._long_pos()
        mkt = _mk_market(price=18000.0 - self.s.hard_stop_points, vwap=18000.0, ts=1010)
        sig, _ = self.strategy.manage_exit(mkt, pos)
        self.assertIsNotNone(sig)
        assert sig is not None
        self.assertEqual(sig.audit.reason, "stop_loss")

    def test_out_of_grace_vwap_stop_active(self):
        pos = self._long_pos(ticks=self.s.exit_grace_ticks, entry_ts=1000)
        vwap = 18000.0
        vwap_stop_dist = self.s.vwap_stop_points
        mkt = _mk_market(
            price=vwap - vwap_stop_dist,
            vwap=vwap,
            ts=1000 + self.s.exit_grace_sec,
        )
        sig, _ = self.strategy.manage_exit(mkt, pos)
        self.assertIsNotNone(sig)
        assert sig is not None
        self.assertEqual(sig.audit.reason, "stop_loss_vwap")

    def test_still_in_grace_when_ticks_met_but_time_not(self):
        pos = self._long_pos(ticks=self.s.exit_grace_ticks, entry_ts=1000)
        mkt = _mk_market(
            price=18000.0 - self.s.vwap_stop_points,
            vwap=18000.0 - self.s.vwap_stop_points,
            ts=1000 + self.s.exit_grace_sec - 1,
        )
        sig, _ = self.strategy.manage_exit(mkt, pos)
        self.assertIsNone(sig)

    def test_short_in_grace_vwap_stop_suppressed(self):
        pos = PositionSnapshot(
            has_position=True,
            position_dir="Short",
            qty=1,
            entry_price=18000.0,
            entry_exchange_ts=1000,
            trailing_peak=18000.0,
            ticks_since_entry=5,
        )
        mkt = _mk_market(
            price=18000.0 + self.s.vwap_stop_points, vwap=18000.0 + self.s.vwap_stop_points, ts=1010
        )
        sig, _ = self.strategy.manage_exit(mkt, pos)
        self.assertIsNone(sig)


if __name__ == "__main__":
    unittest.main()
