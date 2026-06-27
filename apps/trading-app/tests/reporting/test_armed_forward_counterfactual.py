"""Tests for armed-forward counterfactual."""

from __future__ import annotations

import unittest

from reporting.armed_forward_counterfactual import (
    filter_armed_list,
    passes_arm_threshold,
    simulate_atr_barrier_exit,
)
from reporting.structure_calibration import ArmedCandidate


class TestAtrBarrierSim(unittest.TestCase):
    def test_long_stop_loss_first(self) -> None:
        ticks = [
            (1000, 18000.0, 10, 1),
            (1001, 17980.0, 10, 1),  # -20 > 15 stop at 0.75*20
        ]
        out = simulate_atr_barrier_exit(
            direction="Long",
            entry_price=18000.0,
            armed_ts=1000,
            atr=20.0,
            ticks=ticks,
            hard_stop_atr_k=0.75,
            tp_atr_k=2.0,
        )
        self.assertEqual(out["exit_reason"], "stop_loss")
        self.assertEqual(out["gross_pnl"], -15.0)

    def test_long_take_profit(self) -> None:
        ticks = [
            (1000, 18000.0, 10, 1),
            (1001, 18050.0, 10, 1),  # +50 >= 40 tp at 2*20
        ]
        out = simulate_atr_barrier_exit(
            direction="Long",
            entry_price=18000.0,
            armed_ts=1000,
            atr=20.0,
            ticks=ticks,
            hard_stop_atr_k=0.75,
            tp_atr_k=2.0,
        )
        self.assertEqual(out["exit_reason"], "take_profit")
        self.assertEqual(out["gross_pnl"], 40.0)


class TestArmThresholdFilter(unittest.TestCase):
    def _armed(self, **kwargs) -> ArmedCandidate:
        base = dict(
            episode_id="ep-1",
            ts=1_000,
            direction="Long",
            price=18000.0,
            atr=25.0,
            vol_1s=200,
            buy_ratio=0.85,
            sell_ratio=0.15,
        )
        base.update(kwargs)
        return ArmedCandidate(**base)

    def test_passes_vol_and_buy_ratio(self) -> None:
        a = self._armed()
        self.assertTrue(passes_arm_threshold(a, min_vol_1s=180, min_buy_ratio=0.80))
        self.assertFalse(passes_arm_threshold(a, min_vol_1s=210))
        self.assertFalse(passes_arm_threshold(a, min_buy_ratio=0.90))

    def test_filter_short_uses_sell_ratio(self) -> None:
        short = self._armed(direction="Short", buy_ratio=0.2, sell_ratio=0.82)
        kept = filter_armed_list([short], min_sell_ratio=0.80)
        self.assertEqual(len(kept), 1)
        dropped = filter_armed_list([short], min_sell_ratio=0.85)
        self.assertEqual(len(dropped), 0)

    def test_adverse_guard_filters_long_below_vwap(self) -> None:
        from reporting.armed_forward_counterfactual import passes_adverse_guard

        armed = ArmedCandidate(
            episode_id="ep-1",
            ts=1,
            direction="Long",
            price=17950.0,
            atr=20.0,
            vwap=18000.0,
        )
        self.assertFalse(passes_adverse_guard(armed, max_adverse_atr_k=1.0))
        self.assertTrue(passes_adverse_guard(armed, max_adverse_atr_k=3.0))


if __name__ == "__main__":
    unittest.main()
