"""Tests for flow flip counterfactual v2."""

from __future__ import annotations

import unittest

from reporting.flow_flip_counterfactual import (
    RollingFlowWindow,
    _evaluate_phase0_gate,
    _fade_direction,
    _flip_surge_ok,
    _footprint_confirms,
)


class TestFadeDirection(unittest.TestCase):
    def test_buy_setup_fades_short(self) -> None:
        self.assertEqual(_fade_direction("buy"), "Short")


class TestRollingFlowWindow(unittest.TestCase):
    def test_buy_ratio(self) -> None:
        w = RollingFlowWindow(10)
        w.push(1000, 10, 1)
        w.push(1001, 10, 2)
        self.assertAlmostEqual(w.buy_ratio, 0.5)


class TestPhase0Gate(unittest.TestCase):
    def test_pass(self) -> None:
        summary = {
            "buy": {
                "mid": {
                    "scalp": {"n": 25, "gross_mean": 7.0, "net_mean": 2.0},
                }
            }
        }
        gate = _evaluate_phase0_gate(summary)
        self.assertTrue(gate["pass"])


class TestFootprint(unittest.TestCase):
    def test_sell_at_highs_for_buy_setup(self) -> None:
        ticks = [
            (1000, 18010.0, 5, 2),
            (1001, 18010.0, 8, 2),
            (1002, 18009.0, 2, 1),
        ]
        self.assertTrue(_footprint_confirms("buy", ticks))


class TestFlipSurge(unittest.TestCase):
    def test_surge_detected(self) -> None:
        ticks = [
            (1000, 18000.0, 10, 2),
            (1020, 18001.0, 10, 2),
            (1040, 18002.0, 30, 2),
            (1050, 18002.0, 30, 2),
        ]
        self.assertTrue(_flip_surge_ok("buy", ticks, 1050, 30, 1.5))


if __name__ == "__main__":
    unittest.main()
