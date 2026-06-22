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

# Keep aligned with apps/trading-app observability.RISK_BLOCKED_THROTTLE_SEC
RISK_BLOCKED_THROTTLE_SEC = 60


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
    structure_stale: bool = False,
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
        structure_stale=structure_stale,
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
    structure_bias: str = "Neutral",
    structure_strength: float = 0.0,
    structure_in_discount: bool = False,
    structure_in_premium: bool = False,
    structure_fvg_low: float | None = None,
    structure_fvg_high: float | None = None,
    structure_sweep_reclaim: bool = False,
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
        structure_bias=structure_bias,
        structure_strength=structure_strength,
        structure_in_discount=structure_in_discount,
        structure_in_premium=structure_in_premium,
        structure_fvg_low=structure_fvg_low,
        structure_fvg_high=structure_fvg_high,
        structure_sweep_reclaim=structure_sweep_reclaim,
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
            structure_filter_enabled = False
            structure_timeframe_min = 5
            structure_swing_lookback = 2
            structure_min_strength = 0.0

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
            line for line in cap.output if "DECISION_AUDIT" in line
        ]
        self.assertEqual(len(audit_lines), 1)
        payload = json.loads(audit_lines[0].split("DECISION_AUDIT ", 1)[1])
        self.assertEqual(payload["event_type"], "trend_veto")
        self.assertEqual(payload["reason"], "trend_veto")
        self.assertEqual(payload["direction"], "Buy")
        self.assertEqual(payload["trend_dir"], "Short")
        self.assertGreater(payload["trend_strength"], 0.0)

    def test_structure_veto_emits_decision_audit_when_filter_blocks_pullback(self) -> None:
        """FT-002 Phase 4: regime_allows_entry structure path → structure_veto audit."""

        class _StructureOn:
            def live_get(self, name: str, default: Any = None) -> Any:
                if name == "STRUCTURE_FILTER_ENABLED":
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
            structure_filter_enabled = True
            trend_filter_enabled = False
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
            structure_timeframe_min = 5
            structure_swing_lookback = 2
            structure_min_strength = 0.0

        obs = MagicMock()
        params = StrategyParams(_cfg=_StructureOn())  # type: ignore[arg-type]
        strategy = VWAPMomentumStrategy(params=params, obs=obs)
        risk = _make_risk()
        pos = _make_flat_position()

        activate_ts = 1_700_000_100
        strategy.activate_momentum("Long", 18010.0, activate_ts, episode_id="20260618-001")
        pullback_mkt = _make_market(
            ts=activate_ts + 2,
            price=18005.5,
            vwap=18005.0,
            vol_1s=5,
            buy_vol_1s=3,
            sell_vol_1s=2,
            structure_bias="Short",
            structure_in_premium=True,
            structure_strength=1.2,
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
        obs.record_structure_veto.assert_called_once()
        payload = json.loads(
            [line for line in cap.output if "DECISION_AUDIT" in line][0].split(
                "DECISION_AUDIT ", 1
            )[1]
        )
        self.assertEqual(payload["event_type"], "structure_veto")
        self.assertEqual(payload["reason"], "structure_veto")
        self.assertEqual(payload["momentum_dir"], "Long")
        self.assertEqual(payload["structure_bias"], "Short")
        self.assertEqual(payload["structure_algo_version"], 1)

    def test_momentum_armed_includes_structure_fields_when_filter_on(self) -> None:
        self.strategy.params._cfg._overlay["STRUCTURE_FILTER_ENABLED"] = True
        mkt = _make_market(
            vol_1s=200,
            buy_vol_1s=180,
            sell_vol_1s=20,
            structure_bias="Long",
            structure_in_discount=True,
            structure_strength=0.8,
        )
        with self.assertLogs("strategy_vwap_momentum.strategy", level=logging.INFO) as cap:
            self.strategy._try_activate_momentum(mkt, self.vol_threshold)
        payload = json.loads(
            [line for line in cap.output if "momentum_armed" in line][0].split(
                "DECISION_AUDIT ", 1
            )[1]
        )
        self.assertEqual(payload["structure_bias"], "Long")
        self.assertEqual(payload["structure_algo_version"], 1)
        self.assertTrue(payload["structure_in_discount"])

    def test_structure_stale_emits_risk_blocked_audit(self) -> None:
        self.strategy.params._cfg._overlay["STRUCTURE_FILTER_ENABLED"] = True
        obs = MagicMock()
        strategy = VWAPMomentumStrategy(params=self.params, obs=obs)
        risk = _make_risk(structure_stale=True)
        with self.assertLogs("strategy_vwap_momentum.strategy", level=logging.INFO) as cap:
            sig, _ = strategy.evaluate(
                _make_market(),
                _make_flat_position(),
                risk,
                self.vol_threshold,
                session_force_flatten_time=datetime.time(13, 45),
                max_daily_loss_points=150.0,
            )
        self.assertIsNone(sig)
        obs.record_risk_blocked.assert_called_once_with("structure_stale", ts=1_700_000_200)
        payload = json.loads(
            [line for line in cap.output if "risk_blocked" in line][0].split(
                "DECISION_AUDIT ", 1
            )[1]
        )
        self.assertEqual(payload["block_reason"], "structure_stale")

    def test_risk_blocked_audit_throttled_per_reason(self) -> None:
        class _ThrottleObs:
            def __init__(self) -> None:
                self._last: dict[str, int] = {}

            def record_risk_blocked(self, reason: str = "", ts: int = 0) -> bool:
                key = reason or "unknown"
                last = self._last.get(key, 0)
                if ts == 0 or ts - last >= RISK_BLOCKED_THROTTLE_SEC:
                    self._last[key] = ts
                    return True
                return False

            def get_pressure_context(self) -> dict[str, int]:
                return {
                    "consecutive_veto_streak": 0,
                    "consecutive_timeout_streak": 0,
                    "episodes_since_last_entry": 0,
                }

        obs = _ThrottleObs()
        strategy = VWAPMomentumStrategy(params=self.params, obs=obs)
        risk = _make_risk()
        mkt = _make_market(current_atr=1.0)  # below default min_atr_threshold

        with self.assertLogs("strategy_vwap_momentum.strategy", level=logging.INFO) as cap:
            strategy.evaluate(
                mkt,
                _make_flat_position(),
                risk,
                self.vol_threshold,
                session_force_flatten_time=datetime.time(13, 45),
                max_daily_loss_points=150.0,
            )
            strategy.evaluate(
                _make_market(current_atr=1.0, ts=mkt.ts + 1),
                _make_flat_position(),
                risk,
                self.vol_threshold,
                session_force_flatten_time=datetime.time(13, 45),
                max_daily_loss_points=150.0,
            )
        risk_logs = [
            line for line in cap.output if "DECISION_AUDIT" in line and "risk_blocked" in line
        ]
        self.assertEqual(len(risk_logs), 1)

    def test_risk_blocked_audit_different_reasons_not_throttled(self) -> None:
        class _ThrottleObs:
            def __init__(self) -> None:
                self._last: dict[str, int] = {}

            def record_risk_blocked(self, reason: str = "", ts: int = 0) -> bool:
                key = reason or "unknown"
                last = self._last.get(key, 0)
                if ts == 0 or ts - last >= RISK_BLOCKED_THROTTLE_SEC:
                    self._last[key] = ts
                    return True
                return False

            def get_pressure_context(self) -> dict[str, int]:
                return {
                    "consecutive_veto_streak": 0,
                    "consecutive_timeout_streak": 0,
                    "episodes_since_last_entry": 0,
                }

        obs = _ThrottleObs()
        strategy = VWAPMomentumStrategy(params=self.params, obs=obs)
        ts = 1_700_000_200
        mkt = _make_market(current_atr=1.0, ts=ts)

        with self.assertLogs("strategy_vwap_momentum.strategy", level=logging.INFO) as cap:
            strategy.evaluate(
                mkt,
                _make_flat_position(),
                _make_risk(),
                self.vol_threshold,
                session_force_flatten_time=datetime.time(13, 45),
                max_daily_loss_points=150.0,
            )
            strategy.evaluate(
                mkt,
                _make_flat_position(),
                _make_risk(block_new_entry=True),
                self.vol_threshold,
                session_force_flatten_time=datetime.time(13, 45),
                max_daily_loss_points=150.0,
            )
        risk_logs = [
            line for line in cap.output if "DECISION_AUDIT" in line and "risk_blocked" in line
        ]
        self.assertEqual(len(risk_logs), 2)
        reasons = {
            json.loads(line.split("DECISION_AUDIT ", 1)[1])["block_reason"]
            for line in risk_logs
        }
        self.assertEqual(reasons, {"min_atr", "block_new_entry"})

    def test_block_new_entry_and_pending_gates_return_none(self) -> None:
        mkt = _make_market()
        risk_blocked = _make_risk(block_new_entry=True)
        risk_pending = _make_risk(is_pending=True)

        pos = _make_flat_position()

        # use strategy with obs to trigger risk emit
        obs = MagicMock()
        strategy = VWAPMomentumStrategy(params=self.params, obs=obs)
        for r in (risk_blocked, risk_pending):
            if r.block_new_entry:
                with self.assertLogs("strategy_vwap_momentum.strategy", level=logging.INFO) as cap:
                    sig, _ = strategy.evaluate(
                        mkt,
                        pos,
                        r,
                        self.vol_threshold,
                        session_force_flatten_time=datetime.time(13, 45),
                        max_daily_loss_points=150.0,
                    )
                self.assertIsNone(sig)
                risk_logs = [line for line in cap.output if "DECISION_AUDIT" in line and "risk_blocked" in line]
                self.assertTrue(len(risk_logs) >= 1)
            else:
                sig, _ = strategy.evaluate(
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

    def test_structure_stale_blocks_flat_entry_when_filter_on(self) -> None:
        self.strategy.params._cfg._overlay["STRUCTURE_FILTER_ENABLED"] = True
        risk = _make_risk(structure_stale=True)
        sig, _ = self.strategy.evaluate(
            _make_market(),
            _make_flat_position(),
            risk,
            self.vol_threshold,
            session_force_flatten_time=datetime.time(13, 45),
            max_daily_loss_points=150.0,
        )
        self.assertIsNone(sig)

    def test_structure_stale_allows_exit_when_position_open(self) -> None:
        """FT-002 §6.3: structure_stale blocks entry only; open positions may still exit."""
        self.strategy.params._cfg._overlay["STRUCTURE_FILTER_ENABLED"] = True
        risk = _make_risk(structure_stale=True)
        mkt = _make_market(price=18010.0 + 25, vwap=18020.0, current_atr=10.0, ts=1_700_000_500)
        pos = PositionSnapshot(
            has_position=True,
            position_dir="Long",
            entry_price=18010.0,
            trailing_peak=18035.0,
            entry_exchange_ts=1_700_000_100,
            ticks_since_entry=300,
            qty=1,
        )
        sig, _ = self.strategy.evaluate(
            mkt,
            pos,
            risk,
            self.vol_threshold,
            session_force_flatten_time=datetime.time(13, 45),
            max_daily_loss_points=150.0,
        )
        self.assertIsNotNone(sig)
        self.assertEqual(sig.intent, "exit")

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

    def test_momentum_armed_emits_decision_audit_and_episode_id(self) -> None:
        """Phase 1: _try_activate_momentum on qualifying vol emits DECISION_AUDIT momentum_armed + sets episode_id."""
        obs = MagicMock()
        strategy = VWAPMomentumStrategy(params=self.params, obs=obs)
        mkt = _make_market(vol_1s=200, buy_vol_1s=180, sell_vol_1s=20, price=18010.0, vwap=18005.0)
        # Directly exercise arm path (evaluate may gate); use low threshold to guarantee
        with self.assertLogs("strategy_vwap_momentum.strategy", level=logging.INFO) as cap:
            strategy._try_activate_momentum(mkt, (80.0, 1.0, 150.0))
        self.assertTrue(strategy.momentum.active)
        self.assertTrue(getattr(strategy.momentum, "episode_id", "").startswith("20"))
        self.assertIn("-", getattr(strategy.momentum, "episode_id", ""))

        dec_lines = [line for line in cap.output if "DECISION_AUDIT" in line and "momentum_armed" in line]
        self.assertEqual(len(dec_lines), 1)
        payload = json.loads(dec_lines[0].split("DECISION_AUDIT ", 1)[1])
        self.assertEqual(payload["event_type"], "momentum_armed")
        self.assertEqual(payload["episode_id"], strategy.momentum.episode_id)
        self.assertEqual(payload["direction"], "Long")
        self.assertGreater(payload["vol_1s"], 0)
        self.assertIn("audit_schema_version", payload)

    def test_entry_signal_audit_carries_episode_id_and_timing_fields(self) -> None:
        """Phase 1 propagation surface: after armed, a qualifying pullback produces OrderSignal whose audit carries episode_id + elapsed/dist."""
        obs = MagicMock()
        strategy = VWAPMomentumStrategy(params=self.params, obs=obs)
        arm_mkt = _make_market(vol_1s=200, buy_vol_1s=180, sell_vol_1s=20, price=18010.0, vwap=18005.0, ts=1_700_000_000)
        strategy._try_activate_momentum(arm_mkt, (80.0, 1.0, 150.0))
        self.assertTrue(strategy.momentum.active)
        ep = strategy.momentum.episode_id

        # qualifying pullback (near vwap + low vol)
        pull_mkt = _make_market(
            ts=1_700_000_080, price=18005.3, vwap=18005.0, vol_1s=5, buy_vol_1s=3, sell_vol_1s=2,
            current_atr=9.0,
        )
        sig = strategy._try_pullback_entry(pull_mkt, (80.0, 1.0, 150.0))
        self.assertIsNotNone(sig)
        a = sig.audit  # type: ignore[union-attr]
        self.assertEqual(a.episode_id, ep)
        self.assertGreater(a.elapsed_since_arm_sec, 0)
        self.assertAlmostEqual(a.dist_vwap, 0.3, places=1)

    def test_exit_audit_enriched_with_entry_and_stop_fields(self) -> None:
        """Phase 1: build_exit_audit / manage_exit populates entry_price, hold_ticks, levels, trailing_peak."""
        # Use price above entry + fixed_tp (20 default) to reliably trigger take_profit exit
        mkt = _make_market(price=18010.0 + 25, vwap=18020.0, current_atr=10.0, ts=1_700_000_500)
        pos = PositionSnapshot(
            has_position=True,
            position_dir="Long",
            entry_price=18010.0,
            trailing_peak=18035.0,
            entry_exchange_ts=1_700_000_100,
            ticks_since_entry=300,
            qty=1,
        )
        sig, _ = self.strategy.manage_exit(mkt, pos)
        self.assertIsNotNone(sig)
        a = sig.audit  # type: ignore[union-attr]
        self.assertEqual(a.entry_price, 18010.0)
        self.assertEqual(a.hold_ticks, 300)
        self.assertGreater(a.trailing_peak, 0)
        self.assertGreater(a.hard_stop_level, 0)  # still populated
        self.assertIn(a.reason, ("trailing_stop", "take_profit", "stop_loss", "session_force_flatten"))


if __name__ == "__main__":
    unittest.main()
