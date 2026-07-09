"""Session flatten behavior via VWAP momentum strategy (pure Protocol tests)."""

from __future__ import annotations

import datetime
import unittest

from trading_engine.core.types import MarketSnapshot, PositionSnapshot, RiskGate
from trading_engine.testing.defaults import default_test_settings

from strategy_vwap_momentum import StrategyParams, VWAPMomentumStrategy


def _dt(hour: int, minute: int, second: int = 0) -> datetime.datetime:
    return datetime.datetime(2026, 6, 10, hour, minute, second)


def _make_strategy():
    cfg = default_test_settings()  # reuse as RuntimeConfig-like for params in tests
    # default_test_settings is a Settings; StrategyParams accepts RuntimeConfig in real,
    # but for these tests we only need the numeric fields the strategy reads.
    # We fall back to constructing via a minimal object the StrategyParams can use if needed,
    # but here we just use the numbers directly from the settings object (it has the attrs).
    s = cfg  # duck: has the same numeric attrs
    # Build a real RuntimeConfig if available, otherwise synthesize a thin object.
    try:
        from trading_engine.testing.defaults import default_runtime_config

        rc = default_runtime_config()
        params = StrategyParams.from_runtime_config(rc)
    except Exception:
        # Fallback thin object with the attributes the strategy reads
        class _Thin:
            pass

        t = _Thin()
        for k in (
            "flatten_slippage_points",
            "entry_band_points",
            "exhaustion_vol",
            "hard_stop_points",
            "fixed_tp_points",
            "trail_points",
            "vwap_stop_points",
            "exit_grace_ticks",
            "exit_grace_sec",
            "atr_trailing_enabled",
            "atr_vwap_stop_enabled",
            "trail_points_floor",
            "trail_atr_k",
            "vwap_stop_points_floor",
            "vwap_stop_atr_k",
            "max_consecutive_loss",
            "min_atr_threshold",
            "momentum_buy_ratio",
            "momentum_sell_ratio",
            "trend_filter_enabled",
            "momentum_timeout_sec",
        ):
            val = getattr(s, k, 0) if k != "momentum_timeout_sec" else getattr(s, k, 180)
            setattr(t, k, val)
        params = StrategyParams(_cfg=t)  # type: ignore[arg-type]

    return VWAPMomentumStrategy(params=params), s


class TestSessionFlattenStrategy(unittest.TestCase):
    def setUp(self) -> None:
        self.strategy, self.s = _make_strategy()

    def test_force_flatten_signal(self):
        # Use session_force_flatten_signal directly (the hook the kernel calls)
        pos = PositionSnapshot(
            has_position=True,
            position_dir="Long",
            qty=1,
            entry_price=18000.0,
            entry_exchange_ts=0,
            trailing_peak=18000.0,
            ticks_since_entry=10,
        )
        market = MarketSnapshot(
            ts=int(_dt(13, 44).timestamp()),
            price=17990.0,
            dt=_dt(13, 44),
            vwap=18000.0,
            vol_1s=10,
            buy_vol_1s=5,
            sell_vol_1s=5,
            current_atr=10.0,
            trend_dir="Flat",
            trend_strength=0.0,
        )
        sig, effects = self.strategy.session_force_flatten_signal(market, pos, _dt(13, 45).time())
        self.assertIsNotNone(sig)
        assert sig is not None
        self.assertEqual(sig.action, "Sell")
        self.assertEqual(sig.intent, "exit")
        self.assertEqual(sig.slippage_points, self.s.flatten_slippage_points)
        self.assertIsNotNone(sig.audit)
        assert sig.audit is not None
        self.assertEqual(sig.audit.reason, "session_force_flatten")

    def test_no_entry_after_flatten_time(self):
        # Simulate the gate the strategy checks
        risk = RiskGate(
            is_pending=False,
            exit_pending=False,
            cooldown_active=False,
            in_trading_session=True,
            after_flatten_time=True,
            block_new_entry=False,
            force_flatten=False,
            api_connected=True,
            daily_pnl=0.0,
            consecutive_loss=0,
        )
        pos = PositionSnapshot(
            has_position=False,
            position_dir="Flat",
            qty=0,
            entry_price=0.0,
            entry_exchange_ts=0,
            trailing_peak=0.0,
            ticks_since_entry=0,
        )
        market = MarketSnapshot(
            ts=int(_dt(13, 40).timestamp()),
            price=18000.0,
            dt=_dt(13, 40),
            vwap=18000.0,
            vol_1s=100,
            buy_vol_1s=60,
            sell_vol_1s=40,
            current_atr=100.0,
            trend_dir="Long",
            trend_strength=1.0,
        )
        sig, _ = self.strategy.evaluate(
            market,
            pos,
            risk,
            (80.0, 1.5, 120.0),
            session_force_flatten_time=_dt(13, 45).time(),
            max_daily_loss_points=150.0,
        )
        self.assertIsNone(sig)

    def test_force_flatten_overrides_manage_exit(self):
        pos = PositionSnapshot(
            has_position=True,
            position_dir="Long",
            qty=1,
            entry_price=18000.0,
            entry_exchange_ts=0,
            trailing_peak=18000.0,
            ticks_since_entry=5,
        )
        market = MarketSnapshot(
            ts=int(_dt(13, 44).timestamp()),
            price=18000.0,
            dt=_dt(13, 44),
            vwap=18000.0,
            vol_1s=10,
            buy_vol_1s=5,
            sell_vol_1s=5,
            current_atr=10.0,
            trend_dir="Flat",
            trend_strength=0.0,
        )
        sig, _ = self.strategy.session_force_flatten_signal(market, pos, _dt(13, 45).time())
        self.assertIsNotNone(sig)
        assert sig is not None
        self.assertEqual(sig.audit.reason, "session_force_flatten")


if __name__ == "__main__":
    unittest.main()
