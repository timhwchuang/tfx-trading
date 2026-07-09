"""Tests for impulse absorption counterfactual."""

from __future__ import annotations

import unittest

from reporting.impulse_absorption_counterfactual import (
    _evaluate_phase0_gate,
    fade_direction,
    simulate_scalp_exit,
)


class TestFadeDirection(unittest.TestCase):
    def test_long_impulse_fades_short(self) -> None:
        self.assertEqual(fade_direction("Long"), "Short")

    def test_short_impulse_fades_long(self) -> None:
        self.assertEqual(fade_direction("Short"), "Long")


class TestScalpExit(unittest.TestCase):
    def test_take_profit_long(self) -> None:
        ticks = [(1000, 18000.0, 1, 1), (1010, 18015.0, 1, 1)]
        sim = simulate_scalp_exit(
            direction="Long",
            entry_price=18000.0,
            entry_ts=1000,
            ticks=ticks,
            tp_points=12.0,
            sl_points=10.0,
            max_hold_sec=120,
        )
        self.assertEqual(sim["exit_reason"], "take_profit")
        self.assertEqual(sim["gross_pnl"], 12.0)

    def test_stop_loss_short(self) -> None:
        ticks = [(1000, 18000.0, 1, 1), (1010, 18012.0, 1, 1)]
        sim = simulate_scalp_exit(
            direction="Short",
            entry_price=18000.0,
            entry_ts=1000,
            ticks=ticks,
            tp_points=12.0,
            sl_points=10.0,
            max_hold_sec=120,
        )
        self.assertEqual(sim["exit_reason"], "stop_loss")
        self.assertEqual(sim["gross_pnl"], -10.0)


class TestPhase0Gate(unittest.TestCase):
    def test_pass_when_bucket_qualifies(self) -> None:
        summary = {
            "3": {
                "mid": {
                    "scalp": {
                        "n": 25,
                        "gross_mean": 6.0,
                        "net_mean": 1.0,
                    }
                }
            }
        }
        gate = _evaluate_phase0_gate(summary)
        self.assertTrue(gate["pass"])
        self.assertIsNotNone(gate["best_passing"])


if __name__ == "__main__":
    unittest.main()
