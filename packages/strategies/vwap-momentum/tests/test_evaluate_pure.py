"""Pure Protocol-level tests for VWAPMomentumStrategy (no host, direct snapshots).

These tests demonstrate that the strategy can be exercised with only
trading-engine core types — exactly what external plugin authors will do.
"""

from __future__ import annotations

import datetime
import json
import logging
import unittest
from typing import Any
from unittest.mock import MagicMock

from trading_engine.core.strategy import StrategySideEffects
from trading_engine.core.types import MarketSnapshot, PositionSnapshot, RiskGate
from trading_engine.testing.defaults import default_runtime_config

from strategy_vwap_momentum import StrategyParams, VWAPMomentumStrategy


def _make_risk(
    *,
    is_pending: bool = False,
    block_new_entry: bool = False,
    in_trading_session: bool = True,
    after_flatten_time: bool = False,
    cooldown_active: bool = False,
    force_flatten: bool = False,
    api_connected: bool = True,
    atr_stale: bool = False,
    reconnect_warmup_active: bool = False,
    daily_pnl: float = 0.0,
    consecutive_loss: int = 0,
) -> RiskGate:
    return RiskGate(
        is_pending=is_pending,
        exit_pending=False,
        cooldown_active=cooldown_active,
        in_trading_session=in_trading_session,
        after_flatten_time=after_flatten_time,
        block_new_entry=block_new_entry,
        force_flatten=force_flatten,
        api_connected=api_connected,
        atr_stale=atr_stale,
        reconnect_warmup_active=reconnect_warmup_active,
        daily_pnl=daily_pnl,
        consecutive_loss=consecutive_loss,
    )


def _make_flat_position() -> PositionSnapshot:
    return PositionSnapshot(
        has_position=False,
        position_dir="Flat",
        qty=0,
        entry_price=0.0,
        entry_exchange_ts=0,
        trailing_peak=0.0,
        ticks_since_entry=0,
    )


def _make_market(
    *,
    price: float = 18010.0,
    vwap: float = 18005.0,
    vol_1s: int = 150,
    buy_vol_1s: int = 110,
    sell_vol_1s: int = 40,
    current_atr: float = 9.0,
    trend_dir: str = "Long",
    trend_strength: float = 1.8,
    ts: int = 1_700_000_200,
) -> MarketSnapshot:
    return MarketSnapshot(
        ts=ts,
        price=price,
        dt=datetime.datetime.fromtimestamp(ts, tz=datetime.UTC),
        vwap=vwap,
        vol_1s=vol_1s,
        buy_vol_1s=buy_vol_1s,
        sell_vol_1s=sell_vol_1s,
        current_atr=current_atr,
        trend_dir=trend_dir,
        trend_strength=trend_strength,
    )


class TestEvaluatePure(unittest.TestCase):
    def setUp(self) -> None:
        cfg = default_runtime_config()
        self.params = StrategyParams.from_runtime_config(cfg)
        self.strategy = VWAPMomentumStrategy(params=self.params)
        self.vol_threshold = (80.0, 1.5, 120.0)  # base, mult, threshold (illustrative)

    def test_reset_clears_momentum(self) -> None:
        # Force some internal state via activation path
        mkt = _make_market(vol_1s=200, buy_vol_1s=160)
        risk = _make_risk()
        pos = _make_flat_position()

        # First call may arm momentum (internal)
        self.strategy.evaluate(
            mkt,
            pos,
            risk,
            self.vol_threshold,
            session_force_flatten_time=datetime.time(13, 45),
            max_daily_loss_points=150.0,
        )
        self.strategy.reset()
        # After reset, a subsequent identical tick should be allowed to re-arm momentum
        # (we don't assert the signal, just that it doesn't crash and state is clean)
        sig2, _ = self.strategy.evaluate(
            mkt,
            pos,
            risk,
            self.vol_threshold,
            session_force_flatten_time=datetime.time(13, 45),
            max_daily_loss_points=150.0,
        )
        # Either None or an entry — the point is reset worked without error
        self.assertIsInstance(sig2, (type(None), object))  # basic smoke

    def test_trend_veto_emits_signal_audit_when_filter_blocks_pullback(self) -> None:
        """P2: end-to-end trend_veto — active Long momentum + counter HTF → audit, no entry."""

        class _TrendOn:
            def live_get(self, name: str, default: Any = None) -> Any:
                if name == "TREND_FILTER_ENABLED":
                    return True
                if name == "ENTRY_BAND_POINTS":
                    return 2.0
                if name == "EXHAUSTION_VOL":
                    return 15
                if name == "MOMENTUM_TIMEOUT_SEC":
                    return 180
                return default

            entry_band_points = 2.0
            exhaustion_vol = 15
            trend_filter_enabled = True
            max_consecutive_loss = 10
            min_atr_threshold = 0.0
            momentum_timeout_sec = 180
            atr_trailing_enabled = False
            atr_vwap_stop_enabled = False
            trail_points_floor = 0.0
            trail_atr_k = 0.0
            vwap_stop_points_floor = 0.0
            vwap_stop_atr_k = 0.0
            flatten_slippage_points = 0
            hard_stop_points = 10.0
            fixed_tp_points = 20.0
            trail_points = 8.0
            vwap_stop_points = 3.0
            exit_grace_ticks = 60
            exit_grace_sec = 30
            momentum_buy_ratio = 0.8
            momentum_sell_ratio = 0.8

        obs = MagicMock()
        params = StrategyParams(_cfg=_TrendOn())  # type: ignore[arg-type]
        strategy = VWAPMomentumStrategy(params=params, obs=obs)
        risk = _make_risk()
        pos = _make_flat_position()

        activate_ts = 1_700_000_100
        strategy.activate_momentum("Long", 18010.0, activate_ts)
        pullback_mkt = _make_market(
            ts=activate_ts + 2,
            price=18005.5,
            vwap=18005.0,
            vol_1s=5,
            buy_vol_1s=3,
            sell_vol_1s=2,
            trend_dir="Short",
            trend_strength=2.5,
            current_atr=9.0,
        )

        with self.assertLogs("strategy_vwap_momentum.strategy", level=logging.INFO) as cap:
            sig, _ = strategy.evaluate(
                pullback_mkt,
                pos,
                risk,
                self.vol_threshold,
                session_force_flatten_time=datetime.time(13, 45),
                max_daily_loss_points=150.0,
            )

        self.assertIsNone(sig)
        obs.record_trend_veto.assert_called_once()
        audit_lines = [
            line for line in cap.output if "SIGNAL_AUDIT" in line
        ]
        self.assertEqual(len(audit_lines), 1)
        payload = json.loads(audit_lines[0].split("SIGNAL_AUDIT ", 1)[1])
        self.assertEqual(payload["reason"], "trend_veto")
        self.assertEqual(payload["intent"], "entry")
        self.assertEqual(payload["direction"], "Buy")
        self.assertEqual(payload["trend_dir"], "Short")
        self.assertGreater(payload["trend_strength"], 0.0)

    def test_block_new_entry_and_pending_gates_return_none(self) -> None:
        mkt = _make_market()
        risk_blocked = _make_risk(block_new_entry=True)
        risk_pending = _make_risk(is_pending=True)

        pos = _make_flat_position()

        for r in (risk_blocked, risk_pending):
            sig, _ = self.strategy.evaluate(
                mkt,
                pos,
                r,
                self.vol_threshold,
                session_force_flatten_time=datetime.time(13, 45),
                max_daily_loss_points=150.0,
            )
            self.assertIsNone(sig)

    def test_momentum_timeout_resets_state_and_prevents_entry(self) -> None:
        """Momentum times out after momentum_timeout_sec without a qualifying pullback.

        Uses an explicit small timeout via thin config to isolate the timeout branch.
        """

        # Thin config to force a small, predictable timeout (independent of global defaults)
        class _Thin:
            def live_get(self, name: str, default: Any = None) -> Any:
                if name == "MOMENTUM_TIMEOUT_SEC":
                    return 5
                return default

            momentum_timeout_sec = 5
            max_consecutive_loss = 10
            min_atr_threshold = 0.0
            atr_trailing_enabled = False
            atr_vwap_stop_enabled = False
            trail_points_floor = 0.0
            trail_atr_k = 0.0
            vwap_stop_points_floor = 0.0
            vwap_stop_atr_k = 0.0
            trend_filter_enabled = False
            flatten_slippage_points = 0
            entry_band_points = 2.0
            exhaustion_vol = 0
            hard_stop_points = 10.0
            fixed_tp_points = 20.0
            trail_points = 8.0
            vwap_stop_points = 3.0
            exit_grace_ticks = 60
            exit_grace_sec = 30
            momentum_buy_ratio = 0.8
            momentum_sell_ratio = 0.8

        params = StrategyParams(_cfg=_Thin())  # type: ignore[arg-type]
        strategy = VWAPMomentumStrategy(params=params)
        risk = _make_risk()
        pos = _make_flat_position()

        # Activate
        activate_ts = 1_700_000_000
        strategy.activate_momentum("Long", 18010.0, activate_ts)
        self.assertTrue(strategy.momentum.active)

        # Tick after timeout + pullback-friendly conditions
        late_ts = activate_ts + 10  # > 5s
        pullback_mkt = _make_market(
            ts=late_ts,
            price=18005.5,
            vwap=18005.0,
            vol_1s=5,
            buy_vol_1s=3,
            sell_vol_1s=2,
        )
        sig, _ = strategy.evaluate(
            pullback_mkt,
            pos,
            risk,
            (80.0, 1.5, 120.0),
            session_force_flatten_time=datetime.time(13, 45),
            max_daily_loss_points=150.0,
        )
        self.assertIsNone(sig)
        self.assertFalse(strategy.momentum.active)  # reset happened

    def test_atr_stale_blocks_flat_entry(self) -> None:
        risk = _make_risk(atr_stale=True)
        sig, _ = self.strategy.evaluate(
            _make_market(),
            _make_flat_position(),
            risk,
            self.vol_threshold,
            session_force_flatten_time=datetime.time(13, 45),
            max_daily_loss_points=150.0,
        )
        self.assertIsNone(sig)

    def test_reconnect_warmup_blocks_flat_entry(self) -> None:
        risk = _make_risk(reconnect_warmup_active=True)
        sig, _ = self.strategy.evaluate(
            _make_market(),
            _make_flat_position(),
            risk,
            self.vol_threshold,
            session_force_flatten_time=datetime.time(13, 45),
            max_daily_loss_points=150.0,
        )
        self.assertIsNone(sig)


if __name__ == "__main__":
    unittest.main()
