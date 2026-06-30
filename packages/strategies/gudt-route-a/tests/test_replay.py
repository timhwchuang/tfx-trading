"""Unit tests for replay plan builder."""

from __future__ import annotations

import unittest

from strategy_gudt_route_a.replay import build_replay_plan


class TestBuildReplayPlan(unittest.TestCase):
    def test_long_only_sealed(self) -> None:
        pick = {"day": "2026-06-01", "path": "p0+sealed", "net": 100.0, "hedge": "none"}
        long_row = {"entry_ts": 1000, "entry_px": 22000.0}
        long_sim = {"hold_sec": 900, "exit_price": 22100.0, "exit_reason": "horizon"}
        plan = build_replay_plan(pick, long_row=long_row, long_sim=long_sim)
        self.assertEqual(len(plan.events), 2)
        self.assertEqual(plan.events[0].leg, "long_entry")
        self.assertEqual(plan.events[1].leg, "long_exit")
        self.assertEqual(plan.events[1].ts, 1900)

    def test_flip_day(self) -> None:
        pick = {
            "day": "2026-06-29",
            "path": "p0+sealed",
            "net": -40.0,
            "hedge": "flip",
            "dist_confirm": "pass",
            "dist_short_ts": 2000,
        }
        long_row = {"entry_ts": 1000, "entry_px": 22000.0}
        long_sim = {"hold_sec": 500, "exit_price": 21950.0, "exit_reason": "horizon"}
        flip_signal = {"flip_ts": 1500, "flip_px": 21980.0}
        short_sim = {"hold_sec": 600, "exit_price": 21920.0, "exit_reason": "stop_loss", "entry_price": 21970.0}
        plan = build_replay_plan(
            pick,
            long_row=long_row,
            long_sim=long_sim,
            flip_signal=flip_signal,
            short_sim=short_sim,
        )
        legs = [e.leg for e in plan.events]
        self.assertEqual(legs, ["long_entry", "long_exit", "short_entry", "short_exit"])
        self.assertEqual(plan.hedge, "flip")

    def test_confirm_veto_no_short(self) -> None:
        pick = {
            "day": "2026-06-25",
            "path": "p0+sealed",
            "net": 50.0,
            "hedge": "none",
            "dist_confirm": "veto",
        }
        long_row = {"entry_ts": 1000, "entry_px": 22000.0}
        long_sim = {"hold_sec": 900, "exit_price": 22050.0, "exit_reason": "horizon"}
        plan = build_replay_plan(pick, long_row=long_row, long_sim=long_sim)
        self.assertEqual(len(plan.events), 2)


if __name__ == "__main__":
    unittest.main()
