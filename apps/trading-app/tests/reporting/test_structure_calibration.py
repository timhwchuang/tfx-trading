"""A-class unit tests for P6-SMC-CAL structure calibration harness (synthetic only).

SYNTHETIC GUARD: numbers here verify harness logic only — not for Go/No-Go.
"""

from __future__ import annotations

import datetime
import unittest

from reporting.structure_calibration import (
    ArmedCandidate,
    TrendHarnessConfig,
    apply_friction,
    compute_regime_veto_calibration,
    counterfactual_regime_allows,
    entry_ts_within_window,
    make_synthetic_armed_scenario,
    parse_momentum_armed,
    run_counterfactual_comparison,
)
from storage.kbar_loader import KBarRecord
from strategy_vwap_momentum.structure import StructureParams, StructureState
from trading_engine.core.audit.decision_audit import DecisionAudit
from trading_engine.core.audit.signal_audit import SignalAudit


def _kbar(day: datetime.date, minute_offset: int, close: float) -> KBarRecord:
    base = datetime.datetime.combine(day, datetime.time(8, 45))
    ts = base + datetime.timedelta(minutes=minute_offset)
    return KBarRecord(
        ts=ts,
        Open=close,
        High=close + 1,
        Low=close - 1,
        Close=close,
        Volume=1,
    )


class TestStructureCalibrationHarness(unittest.TestCase):
    def test_parse_momentum_armed(self):
        decisions = [
            DecisionAudit(
                event_type="momentum_armed",
                ts=100,
                episode_id="e1",
                direction="Long",
                trigger_price=21800.0,
                atr=25.0,
            ),
            DecisionAudit(event_type="momentum_timeout", ts=200, episode_id="e1"),
        ]
        armed = parse_momentum_armed(decisions)
        self.assertEqual(len(armed), 1)
        self.assertEqual(armed[0].price, 21800.0)

    def test_entry_ts_within_window(self):
        signals = [
            SignalAudit(intent="entry", direction="Buy", price=100.0, ts=125, episode_id="e1"),
            SignalAudit(intent="entry", direction="Buy", price=100.0, ts=200, episode_id="e1"),
            SignalAudit(intent="entry", direction="Buy", price=100.0, ts=200, episode_id="e2"),
        ]
        self.assertEqual(entry_ts_within_window(100, "e1", signals), 125)
        self.assertIsNone(entry_ts_within_window(100, "e2", signals))

    def test_counterfactual_structure_only_vetoes_counter_bias(self):
        state = StructureState(bias="Short", in_premium=True)
        allowed, reason = counterfactual_regime_allows(
            "structure_only",
            structure_state=state,
            trend_dir="Flat",
            momentum_dir="Long",
            price=100.0,
            structure_params=StructureParams(structure_min_strength=0.0),
        )
        self.assertFalse(allowed)
        self.assertEqual(reason, "structure_veto")

    def test_counterfactual_no_filter_always_allows(self):
        state = StructureState(bias="Short")
        allowed, reason = counterfactual_regime_allows(
            "no_filter",
            structure_state=state,
            trend_dir="Short",
            momentum_dir="Long",
            price=100.0,
            structure_params=StructureParams(),
        )
        self.assertTrue(allowed)
        self.assertEqual(reason, "")

    def test_apply_friction(self):
        self.assertEqual(apply_friction(10.0, 2.0), 8.0)

    def test_compute_regime_veto_calibration_synthetic(self):
        day = datetime.date(2026, 6, 12)
        bars = [_kbar(day, i, 100.0 + i) for i in range(20)]
        prices = [float(p) for p in range(100, 140)]
        candidates = make_synthetic_armed_scenario(prices, armed_at=[5, 12, 20], direction="Long")

        def fwd(price: float, ts: int, direction: str = "Long") -> float:
            idx = int(ts)
            j = min(len(prices) - 1, idx + 10)
            sign = 1.0 if direction == "Long" else -1.0
            return sign * (prices[j] - price)

        res = compute_regime_veto_calibration(
            candidates,
            scenario="no_filter",
            bars_1m=bars,
            get_forward_pnl=fwd,
        )
        self.assertEqual(res["n_veto"], 0)
        self.assertEqual(res["n_allowed"], 3)
        self.assertEqual(res["veto_rate"], 0.0)
        self.assertIn("delta_expectancy", res)

    def test_run_counterfactual_comparison_has_three_scenarios(self):
        day = datetime.date(2026, 6, 12)
        bars = [_kbar(day, i, 100.0 + i * 0.5) for i in range(30)]
        candidates = [
            ArmedCandidate(episode_id="a", ts=1000, direction="Long", price=100.0, atr=10.0)
        ]
        # Use epoch that maps to session with enough bars
        ts = int(datetime.datetime(2026, 6, 12, 9, 15).timestamp())
        candidates = [
            ArmedCandidate(episode_id="a", ts=ts, direction="Long", price=110.0, atr=10.0)
        ]
        out = run_counterfactual_comparison(candidates, bars_1m=bars)
        self.assertIn("no_filter", out)
        self.assertIn("structure_only", out)
        self.assertIn("trend_only", out)
        self.assertIn("comparison", out)
        self.assertIn("delta_structure_vs_trend", out["comparison"])


if __name__ == "__main__":
    unittest.main()