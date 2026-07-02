"""Tests for simulate_atr_trail_skew_exit (FT-018 · PLAN T1–T8)."""

from __future__ import annotations

import unittest

from reporting.simulate_atr_trail_skew_exit import simulate_atr_trail_skew_exit


def _ticks(prices: list[tuple[int, float]]) -> list[tuple[int, float, int, int]]:
    return [(ts, p, 1, 1) for ts, p in prices]


class TestTrailExit(unittest.TestCase):
    _ATR = 30.0

    def _sim(self, ticks: list[tuple[int, float]], **kwargs: object) -> dict:
        defaults = {
            "direction": "Long",
            "entry_price": 100.0,
            "entry_ts": 1_000,
            "atr": self._ATR,
            "hard_stop_atr_k": 1.0,
            "be_trigger_atr_k": 1.0,
            "trail_arm_atr_k": 2.0,
            "trail_dist_atr_k": 0.5,
            "hard_tp_atr_k": 4.0,
            "min_atr_pts": 10.0,
        }
        defaults.update(kwargs)
        return simulate_atr_trail_skew_exit(ticks=_ticks(ticks), **defaults)  # type: ignore[arg-type]

    def test_t1_initial_stop_before_be(self) -> None:
        """T1: hit k_sl×ATR stop before BE arms."""
        sim = self._sim([(1_001, 99), (1_002, 95), (1_003, 69)])
        self.assertEqual(sim["gross_pnl"], -31.0)
        self.assertEqual(sim["exit_reason"], "stop_loss")

    def test_t2_be_then_pullback(self) -> None:
        """T2: float profit 1×ATR → BE → pullback hits BE stop → gross 0."""
        sim = self._sim([(1_001, 130), (1_002, 125), (1_003, 100)])
        self.assertEqual(sim["gross_pnl"], 0.0)
        self.assertEqual(sim["exit_reason"], "breakeven")
        self.assertTrue(sim["be_armed"])

    def test_t3_trail_arm_and_exit(self) -> None:
        """T3: trail arms at 2×ATR, peak +1×ATR more, exit on trail."""
        sim = self._sim([(1_001, 160), (1_002, 190), (1_003, 175)])
        self.assertEqual(sim["gross_pnl"], 75.0)
        self.assertEqual(sim["exit_reason"], "trail_stop")
        self.assertTrue(sim["trail_armed"])

    def test_t4_hard_tp(self) -> None:
        """T4: peak reaches 4×ATR hard TP."""
        sim = self._sim([(1_001, 220)])
        self.assertEqual(sim["gross_pnl"], 120.0)
        self.assertEqual(sim["exit_reason"], "take_profit")

    def test_t5_stop_before_tp_same_tick(self) -> None:
        """T5: peak at TP threshold but pullback hits trail stop before TP exit."""
        sim = self._sim([(1_001, 219), (1_002, 175)])
        self.assertEqual(sim["exit_reason"], "trail_stop")
        self.assertEqual(sim["gross_pnl"], 75.0)

    def test_t6_time_exit(self) -> None:
        """T6: max_hold_sec=900 time exit without BE/trail."""
        sim = self._sim(
            [(1_100, 101), (1_900, 102), (1_901, 200)],
            max_hold_sec=900,
        )
        self.assertEqual(sim["exit_reason"], "horizon")
        self.assertEqual(sim["gross_pnl"], 2.0)
        self.assertEqual(sim["hold_sec"], 900)

    def test_t7_be_without_trail_arm(self) -> None:
        """T7: BE armed but peak never reaches trail arm → BE stop."""
        sim = self._sim([(1_001, 135), (1_002, 132), (1_003, 100)])
        self.assertEqual(sim["gross_pnl"], 0.0)
        self.assertFalse(sim["trail_armed"])
        self.assertTrue(sim["be_armed"])

    def test_t8_min_atr_floor(self) -> None:
        """T8: min_atr_pts=25 floor on stop distance."""
        sim = self._sim([(1_001, 74)], atr=5.0, min_atr_pts=25.0)
        self.assertEqual(sim["gross_pnl"], -26.0)

    def test_struct_floor_above_entry_no_phantom(self) -> None:
        """Drive-low floor above entry fills at market, not at floor."""
        sim = self._sim(
            [(1_001, 88.0)],
            entry_price=83.0,
            initial_stop_price=90.0,
            be_trigger_atr_k=None,
            hard_tp_atr_k=None,
        )
        self.assertEqual(sim["exit_price"], 88.0)
        self.assertEqual(sim["gross_pnl"], 5.0)
        self.assertFalse(sim["gross_pnl"] > 40.0)


if __name__ == "__main__":
    unittest.main()
