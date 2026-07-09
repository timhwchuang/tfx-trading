"""Tests for VWAP stretch fade counterfactual."""

from __future__ import annotations

import datetime as dt
import unittest

from reporting.vwap_stretch_fade_counterfactual import (
    TickSnapshot,
    _evaluate_phase0_gate,
    fade_direction,
    session_bucket_for_ts,
    simulate_stretch_fade_entries,
)


class TestSessionBucket(unittest.TestCase):
    def test_open_30m(self) -> None:
        # 2026-04-01 08:50 Taiwan - use local timestamp construction
        ts = int(dt.datetime(2026, 4, 1, 8, 50, 0).timestamp())
        self.assertEqual(session_bucket_for_ts(ts), "open_30m")

    def test_close_1h(self) -> None:
        ts = int(dt.datetime(2026, 4, 1, 13, 0, 0).timestamp())
        self.assertEqual(session_bucket_for_ts(ts), "close_1h")


class TestFadeDirection(unittest.TestCase):
    def test_positive_z_short(self) -> None:
        self.assertEqual(fade_direction(2.0), "Short")

    def test_negative_z_long(self) -> None:
        self.assertEqual(fade_direction(-2.0), "Long")


class TestSimulateEntries(unittest.TestCase):
    def test_triggers_on_stretch(self) -> None:
        snaps = [
            TickSnapshot(1000, 18050.0, 18000.0, 25.0, 2.0, "mid"),
            TickSnapshot(1061, 18050.0, 18000.0, 25.0, 2.0, "mid"),
        ]
        ticks = [(1000, 18050.0, 1, 1), (1100, 18000.0, 1, 1)]
        rows = simulate_stretch_fade_entries(
            snaps, ticks, stretch_k=1.5, cooldown_sec=60, reset_z=0.5
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["direction"], "Short")

    def test_reset_blocks_until_z_small(self) -> None:
        snaps = [
            TickSnapshot(1000, 18050.0, 18000.0, 25.0, 2.0, "mid"),
            TickSnapshot(1100, 18050.0, 18000.0, 25.0, 2.0, "mid"),
        ]
        ticks = [(1000, 18050.0, 1, 1), (1100, 18050.0, 1, 1)]
        rows = simulate_stretch_fade_entries(
            snaps, ticks, stretch_k=1.5, cooldown_sec=0, reset_z=0.5
        )
        self.assertEqual(len(rows), 1)


class TestPhase0Gate(unittest.TestCase):
    def test_pass_when_bucket_qualifies(self) -> None:
        summary = {
            "2.0": {
                "mid": {
                    "atr_barrier_180s": {
                        "n": 40,
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
