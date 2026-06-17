"""Cooldown gate uses exchange timestamp (pure strategy test).

Cooldown is enforced by the kernel via RiskGate.cooldown_active.
The strategy must simply respect the gate (no new entry while active).
"""

from __future__ import annotations

import datetime
import unittest

from trading_engine.core.types import MarketSnapshot, PositionSnapshot, RiskGate
from trading_engine.testing.defaults import default_test_settings

from strategy_vwap_momentum import StrategyParams, VWAPMomentumStrategy


def _make_strategy():
    s = default_test_settings()
    try:
        from trading_engine.testing.defaults import default_runtime_config

        params = StrategyParams.from_runtime_config(default_runtime_config())
    except Exception:

        class _T:
            pass

        t = _T()
        setattr(t, "cooldown_sec", getattr(s, "cooldown_sec", 30))
        setattr(t, "momentum_timeout_sec", getattr(s, "momentum_timeout_sec", 180))
        params = StrategyParams(_cfg=t)  # type: ignore

    return VWAPMomentumStrategy(params=params), s


class TestCooldownUsesExchangeTs(unittest.TestCase):
    def test_cooldown_blocks_entry_while_gate_active(self):
        strategy, s = _make_strategy()
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
            ts=1_700_000_010,
            price=18000.0,
            dt=datetime.datetime.fromtimestamp(1_700_000_010, tz=datetime.UTC),
            vwap=18000.0,
            vol_1s=200,
            buy_vol_1s=160,
            sell_vol_1s=40,
            current_atr=100.0,
            trend_dir="Long",
            trend_strength=1.0,
        )
        risk = RiskGate(
            is_pending=False,
            exit_pending=False,
            cooldown_active=True,
            in_trading_session=True,
            after_flatten_time=False,
            block_new_entry=False,
            force_flatten=False,
            api_connected=True,
            daily_pnl=0.0,
            consecutive_loss=0,
        )
        sig, _ = strategy.evaluate(
            market,
            pos,
            risk,
            (80.0, 1.5, 120.0),
            session_force_flatten_time=datetime.time(13, 45),
            max_daily_loss_points=150.0,
        )
        self.assertIsNone(sig)


if __name__ == "__main__":
    unittest.main()
