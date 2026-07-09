"""Tests for sweep.sweep_progress."""

from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from sweep.sweep_progress import SweepProgressTracker, slim_sweep_row


class TestSweepProgress(unittest.TestCase):
    def test_append_progress_and_combo_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = root / "sweep_progress.log"
            results = root / "sweep_result.jsonl"
            tracker = SweepProgressTracker(progress, results, heartbeat_sec=3600)
            tracker.start_sweep(agent="agent-conservative", combos=2)
            tracker.combo_start(
                1, 2, {"a": 1}, run_index=1, run_total=2, train_days=2, valid_days=1
            )
            tracker.day_complete(1, 2, __import__("datetime").date(2026, 1, 2), "train")
            row = {
                "params": {"a": 1},
                "valid_score": 1.5,
                "train_kpi": {"daily_pnl_points": 0.0, "_summaries": [{"x": 1}]},
                "valid_kpi": {"daily_pnl_points": 1.0},
            }
            tracker.combo_done(row)
            tracker.finish("DONE", exit_code=0, top_valid_score=1.5)

            lines = progress.read_text(encoding="utf-8").strip().splitlines()
            self.assertGreaterEqual(len(lines), 4)
            events = [json.loads(line)["event"] for line in lines]
            self.assertEqual(events[0], "sweep_start")
            self.assertIn("combo_done", events)
            self.assertEqual(events[-1], "sweep_done")

            start = json.loads(lines[0])
            self.assertIn("run_id", start)
            self.assertEqual(json.loads(lines[1])["run_id"], start["run_id"])

            result_lines = results.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(result_lines), 1)
            parsed = json.loads(result_lines[0])
            self.assertNotIn("_summaries", parsed["train_kpi"])

    def test_start_sweep_truncates_progress_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = root / "sweep_progress.log"
            results = root / "sweep_result.jsonl"
            progress.write_text("stale line\n", encoding="utf-8")
            tracker = SweepProgressTracker(progress, results, heartbeat_sec=3600)
            tracker.start_sweep(agent="a")
            tracker.finish("DONE", exit_code=0)
            lines = progress.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[0])["event"], "sweep_start")
            self.assertNotEqual(lines[0], "stale line")

    def test_concurrent_progress_writes_valid_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = root / "sweep_progress.log"
            results = root / "sweep_result.jsonl"
            tracker = SweepProgressTracker(progress, results, heartbeat_sec=0.05)
            tracker.start_sweep(agent="test")
            tracker.combo_start(1, 1, {"x": 1}, run_index=1, run_total=1, train_days=10, valid_days=5)

            def writer() -> None:
                d = __import__("datetime").date(2026, 1, 1)
                for i in range(30):
                    tracker.day_complete(i + 1, 30, d, "train")

            threads = [threading.Thread(target=writer) for _ in range(3)]
            for t in threads:
                t.start()
            time.sleep(0.25)
            tracker.finish("DONE", exit_code=0)
            for t in threads:
                t.join(timeout=2)

            for line in progress.read_text(encoding="utf-8").strip().splitlines():
                parsed = json.loads(line)
                self.assertIn("event", parsed)

    def test_combo_skipped_increments_counter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = root / "sweep_progress.log"
            results = root / "sweep_result.jsonl"
            tracker = SweepProgressTracker(progress, results, heartbeat_sec=3600)
            tracker.start_sweep(agent="a")
            tracker.combo_skipped(2, 9, {"x": 1}, reason="regime_conflict")
            tracker.finish("DONE", exit_code=0)
            events = [json.loads(line) for line in progress.read_text(encoding="utf-8").strip().splitlines()]
            skipped = [e for e in events if e["event"] == "combo_skipped"][0]
            self.assertEqual(skipped["combos_skipped"], 1)
            self.assertEqual(events[-1]["combos_skipped"], 1)

    def test_heartbeat_includes_phase_elapsed_sec(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            progress = root / "sweep_progress.log"
            results = root / "sweep_result.jsonl"
            tracker = SweepProgressTracker(progress, results, heartbeat_sec=0.05)
            tracker.start_sweep(agent="test", bulk_days=True)
            tracker.combo_start(
                1, 1, {"a": 1}, run_index=1, run_total=1, train_days=2, valid_days=1
            )
            tracker.phase_start("train", day_total=2)
            time.sleep(0.25)
            tracker.finish("DONE", exit_code=0)
            events = [json.loads(line) for line in progress.read_text(encoding="utf-8").strip().splitlines()]
            heartbeats = [e for e in events if e["event"] == "heartbeat"]
            self.assertTrue(heartbeats)
            self.assertGreater(
                max(e["phase_elapsed_sec"] for e in heartbeats),
                0.0,
            )

    def test_slim_sweep_row(self):
        slim = slim_sweep_row(
            {"train_kpi": {"a": 1, "_summaries": []}, "valid_kpi": {"b": 2}}
        )
        self.assertEqual(slim["train_kpi"], {"a": 1})


if __name__ == "__main__":
    unittest.main()
