"""Tests for GUDT replay tick jump scheduling."""

from __future__ import annotations

import datetime as dt
import unittest

from trading_backtest.gudt_replay_jump import GudtReplayJump, build_day_anchor_ts


class TestGudtReplayJump(unittest.TestCase):
    def test_build_day_anchors_includes_events(self) -> None:
        day = dt.date(2026, 3, 18)
        plan = {
            "skipped": False,
            "events": [{"ts": 1773798595, "leg": "long_entry"}],
        }
        anchors = build_day_anchor_ts(
            day,
            plan,
            session_start=dt.time(8, 45),
            session_end=dt.time(13, 45),
            session_flatten=dt.time(13, 40),
            force_flatten=dt.time(13, 44),
        )
        self.assertIn(1773798595.0, anchors)
        self.assertTrue(any(a > 1773798595 for a in anchors))

    def test_skip_between_anchors(self) -> None:
        jump = GudtReplayJump(
            {
                "2026-03-18": {
                    "skipped": False,
                    "events": [
                        {"ts": 1000.0, "leg": "long_entry"},
                        {"ts": 2000.0, "leg": "long_exit"},
                    ],
                }
            },
            session_start=dt.time(8, 45),
            session_end=dt.time(13, 45),
            session_flatten=dt.time(13, 40),
            force_flatten=dt.time(13, 44),
        )
        day = "2026-03-18"
        jump.on_tick_processed(500.0, day, idle=True)
        self.assertTrue(jump.should_skip(600.0, day))
        jump.set_active(True)
        self.assertFalse(jump.should_skip(600.0, day))


if __name__ == "__main__":
    unittest.main()
