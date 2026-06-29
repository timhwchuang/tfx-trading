"""Tests for simulate_fvg_mid_trail_skew_exit (FT-019 · PLAN T1–T8)."""

from __future__ import annotations

import unittest

from reporting.simulate_fvg_mid_trail_skew_exit import simulate_fvg_mid_trail_skew_exit


def _ticks(prices: list[tuple[int, float]]) -> list[tuple[int, float, int, int]]:
    return [(ts, p, 1, 1) for ts, p in prices]


class TestFvgMidTrailExit(unittest.TestCase):
    _ATR = 20.0
    _ENTRY = 110.0
    _MID = 100.0
    _RISK = 10.0

    def _sim(self, ticks: list[tuple[int, float]], **kwargs: object) -> dict:
        defaults = {
            "direction": "Long",
            "entry_price": self._ENTRY,
            "entry_ts": 1_000,
            "fvg_mid": self._MID,
            "atr": self._ATR,
            "be_risk_k": 1.0,
            "trail_arm_risk_k": 2.0,
            "trail_arm_atr_k": 1.5,
            "trail_dist_atr_k": 0.5,
            "hard_tp_risk_k": 4.0,
            "min_atr_pts": 10.0,
        }
        defaults.update(kwargs)
        return simulate_fvg_mid_trail_skew_exit(ticks=_ticks(ticks), **defaults)  # type: ignore[arg-type]

    def test_t1_initial_fvg_mid_stop(self) -> None:
        """T1: initial stop = fvg_mid · hit mid → gross = −(entry−mid)."""
        sim = self._sim([(1_001, 105), (1_002, 100)])
        self.assertEqual(sim["gross_pnl"], -self._RISK)
        self.assertEqual(sim["exit_reason"], "fvg_mid_stop")

    def test_t2_be_then_pullback(self) -> None:
        """T2: float profit ≥ 1×risk_unit → BE → pullback → gross 0."""
        sim = self._sim([(1_001, 120), (1_002, 115), (1_003, 110)])
        self.assertEqual(sim["gross_pnl"], 0.0)
        self.assertEqual(sim["exit_reason"], "breakeven")
        self.assertTrue(sim["be_armed"])

    def test_t3_trail_arm_risk_path(self) -> None:
        """T3: trail arms at 2×risk_unit · peak rises · trail dist 0.5×ATR exit."""
        sim = self._sim([(1_001, 130), (1_002, 140), (1_003, 130)])
        self.assertEqual(sim["exit_reason"], "trail_stop")
        self.assertTrue(sim["trail_armed"])
        self.assertEqual(sim["gross_pnl"], 20.0)

    def test_t4_trail_arm_atr_on_same_tick(self) -> None:
        """T4: ATR trail threshold arms on jump tick (dual trigger)."""
        sim = self._sim(
            [(1_001, 125)],
            entry_price=110.0,
            fvg_mid=109.0,
            atr=20.0,
            trail_arm_risk_k=2.0,
            trail_arm_atr_k=1.5,
        )
        self.assertTrue(sim["trail_armed"])

    def test_t5_hard_tp_4x_risk(self) -> None:
        """T5: hard TP at 4×risk_unit."""
        sim = self._sim([(1_001, 150)])
        self.assertEqual(sim["gross_pnl"], 40.0)
        self.assertEqual(sim["exit_reason"], "take_profit")

    def test_t6_stop_before_tp_same_tick(self) -> None:
        """T6: peak at TP zone but pullback hits trail stop before TP."""
        sim = self._sim([(1_001, 149), (1_002, 135)])
        self.assertEqual(sim["exit_reason"], "trail_stop")
        self.assertLess(sim["gross_pnl"], 40.0)

    def test_t7_time_exit(self) -> None:
        """T7: max_hold_sec=900 horizon exit."""
        sim = self._sim(
            [(1_100, 111), (1_900, 112), (1_901, 200)],
            max_hold_sec=900,
        )
        self.assertEqual(sim["exit_reason"], "horizon")
        self.assertEqual(sim["gross_pnl"], 2.0)
        self.assertEqual(sim["hold_sec"], 900)

    def test_t8_invalid_risk_unit_sim(self) -> None:
        """T8: risk_unit ≤ 0 rejected inside sim (CF must skip entry earlier)."""
        sim = self._sim(
            [(1_001, 105)],
            entry_price=100.0,
            fvg_mid=100.0,
        )
        self.assertEqual(sim["exit_reason"], "invalid_risk_unit")


if __name__ == "__main__":
    unittest.main()
