"""Tests for FT-015 FVG retest pullback counterfactual."""

from __future__ import annotations

import datetime as dt
import unittest

from reporting.fvg_retest_pullback_counterfactual import (
    FrpParams,
    _evaluate_fingerprint_gate,
    _evaluate_phase0_gate_params,
    _in_entry_window_ts,
    _price_in_fvg,
    _vol_threshold,
)
from storage.kbar_loader import KBarRecord


def _fp() -> FrpParams:
    return FrpParams(3, 6, 0.40, 1.0, 2.0)


class TestHelpers(unittest.TestCase):
    def test_entry_window(self) -> None:
        ts_in = int(dt.datetime(2026, 4, 1, 10, 0, 0).timestamp())
        ts_out = int(dt.datetime(2026, 4, 1, 12, 30, 0).timestamp())
        self.assertTrue(_in_entry_window_ts(ts_in))
        self.assertFalse(_in_entry_window_ts(ts_out))

    def test_fvg_zone_inclusive(self) -> None:
        self.assertTrue(_price_in_fvg(100.0, 99.0, 101.0))
        self.assertFalse(_price_in_fvg(98.0, 99.0, 101.0))

    def test_vol_threshold_p40(self) -> None:
        self.assertEqual(_vol_threshold([10, 20, 30, 40, 50], 0.40), 20.0)


class TestGateHelpers(unittest.TestCase):
    def test_fingerprint_gate_skew_n15(self) -> None:
        post = {"n": 16, "forward": {"W1800": {"close_delta_median": 1.0}}}
        self.assertTrue(_evaluate_fingerprint_gate(post)["pass"])
        post2 = {"n": 10, "forward": {"W1800": {"close_delta_median": 5.0}}}
        self.assertFalse(_evaluate_fingerprint_gate(post2)["pass"])

    def test_phase0_gate_skew_min_n(self) -> None:
        summary = {
            "sl3_age6_vp0p4_ksl1_tp2": {
                "atr_barrier_900s": {"n": 16, "gross_mean": 6.0, "net_mean": 1.0}
            }
        }
        gate = _evaluate_phase0_gate_params(summary)
        self.assertTrue(gate["pass"])
        self.assertEqual(gate["min_n"], 15)


if __name__ == "__main__":
    unittest.main()
