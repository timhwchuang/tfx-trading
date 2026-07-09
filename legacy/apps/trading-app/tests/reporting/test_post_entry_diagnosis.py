"""Tests for post_entry_diagnosis."""

from __future__ import annotations

import unittest

from reporting.forward_pnl import TickSeries
from reporting.post_entry_diagnosis import (
    enrich_rows_with_forward_windows,
    entry_window_stats,
    interpret_post_entry,
    summarize_post_entry_diagnosis,
)


class TestEntryWindowStats(unittest.TestCase):
    def test_long_favorable_move(self) -> None:
        series = TickSeries(
            timestamps=[100, 110, 120, 130, 140],
            closes=[100.0, 101.0, 103.0, 102.0, 104.0],
        )
        stats = entry_window_stats(100.0, 100, "Long", series, 40)
        self.assertGreater(stats["close_delta"], 0)
        self.assertGreater(stats["MFE_delta"], stats["MAE_delta"])


class TestSummarize(unittest.TestCase):
    def test_exit_kills_edge_verdict(self) -> None:
        base = {
            "direction": "Long",
            "entry_price": 100.0,
            "ts": 100,
            "atr": 20.0,
            "gross_atr_sim": -10.0,
            "net_atr_sim": -15.0,
            "atr_barrier_sim": {"mfe": 12.0, "mae": 8.0},
            "post_entry_forward": {
                "W1800": {
                    "close_delta": 8.0,
                    "MFE_delta": 12.0,
                    "MAE_delta": 4.0,
                }
            },
        }
        rows = [dict(base) for _ in range(5)]
        summary = summarize_post_entry_diagnosis(rows, friction_points=5.0)
        self.assertEqual(summary["n"], 5)
        verdict = summary["interpretation"]["verdict"]
        self.assertIn(verdict, ("exit_kills_edge", "direction_ok_margin_thin"))

    def test_enrich_rows(self) -> None:
        series = TickSeries(
            timestamps=[100, 200, 300],
            closes=[100.0, 105.0, 103.0],
        )
        rows = [
            {
                "direction": "Long",
                "entry_price": 100.0,
                "ts": 100,
                "atr": 10.0,
                "gross_atr_sim": 1.0,
                "net_atr_sim": -4.0,
            }
        ]
        enrich_rows_with_forward_windows(rows, series, windows_sec=(100,))
        self.assertIn("post_entry_forward", rows[0])
        self.assertIn("W100", rows[0]["post_entry_forward"])


class TestInterpret(unittest.TestCase):
    def test_direction_failed(self) -> None:
        summary = {
            "n": 20,
            "barrier": {"gross_median": -7.0},
            "forward": {"W1800": {"close_delta_median": -3.0}},
            "barrier_path": {"MFE_median": 5.0, "MAE_median": 10.0},
        }
        out = interpret_post_entry(summary, friction_points=5.0)
        self.assertEqual(out["verdict"], "direction_failed")


if __name__ == "__main__":
    unittest.main()
