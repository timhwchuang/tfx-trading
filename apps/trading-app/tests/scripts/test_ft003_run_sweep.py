"""Smoke tests for scripts/ft003_run_sweep.py."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sweep.sweep_instance_lock import SweepInstanceLock

_SRC = Path(__file__).resolve().parents[2] / "src"
_SCRIPT = _SRC / "scripts" / "ft003_run_sweep.py"


def _load_ft003():
    spec = importlib.util.spec_from_file_location("ft003_run_sweep", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {_SCRIPT}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestFt003RunSweep(unittest.TestCase):
    def _workspace(self, root: Path, agent: str) -> Path:
        ws = root / "workspaces" / agent
        (ws / "logs").mkdir(parents=True, exist_ok=True)
        (ws / "grid.json").write_text(
            json.dumps({"entry_band_points": [2.0]}),
            encoding="utf-8",
        )
        return ws

    def test_missing_grid_returns_exit_1(self):
        ft003 = _load_ft003()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "workspaces" / "agent-x" / "logs").mkdir(parents=True)
            with patch.object(ft003, "_repo_root", return_value=root):
                code = ft003.main(["agent-x"])
        self.assertEqual(code, 1)

    def test_lock_held_returns_exit_2(self):
        ft003 = _load_ft003()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agent = "agent-y"
            self._workspace(root, agent)
            lock_path = root / "workspaces" / agent / "logs" / "sweep.lock"
            held = SweepInstanceLock(lock_path)
            held.acquire()
            try:
                with patch.object(ft003, "_repo_root", return_value=root):
                    code = ft003.main([agent])
            finally:
                held.release()
        self.assertEqual(code, 2)

    def test_success_writes_done_progress(self):
        ft003 = _load_ft003()
        train = [__import__("datetime").date(2026, 3, 1)]
        valid = [__import__("datetime").date(2026, 4, 1)]
        fake_rows = [{"valid_score": 1.0, "params": {"entry_band_points": 2.0}}]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agent = "agent-z"
            ws = self._workspace(root, agent)
            with (
                patch.object(ft003, "_repo_root", return_value=root),
                patch.object(ft003, "resolve_cli_tick_cache_dates", side_effect=[train, valid]),
                patch.object(ft003, "sweep", return_value=fake_rows),
            ):
                code = ft003.main([agent])

            progress = json.loads(
                (ws / "logs" / "sweep_progress.log")
                .read_text(encoding="utf-8")
                .strip()
                .splitlines()[-1]
            )
            self.assertEqual(code, 0)
            self.assertEqual(progress["event"], "sweep_done")
            self.assertEqual(progress["exit_code"], 0)

    def test_default_bulk_days_in_sweep_start(self):
        ft003 = _load_ft003()
        train = [__import__("datetime").date(2026, 3, 1)]
        valid = [__import__("datetime").date(2026, 4, 1)]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agent = "agent-bulk"
            ws = self._workspace(root, agent)
            with (
                patch.object(ft003, "_repo_root", return_value=root),
                patch.object(ft003, "resolve_cli_tick_cache_dates", side_effect=[train, valid]),
                patch.object(ft003, "sweep", return_value=[]) as mock_sweep,
            ):
                ft003.main([agent])

            start = json.loads(
                (ws / "logs" / "sweep_progress.log")
                .read_text(encoding="utf-8")
                .strip()
                .splitlines()[0]
            )
            mock_sweep.assert_called_once()
            self.assertTrue(mock_sweep.call_args.kwargs["bulk_days"])
            self.assertTrue(start["bulk_days"])

    def test_per_day_flag_disables_bulk_days(self):
        ft003 = _load_ft003()
        train = [__import__("datetime").date(2026, 3, 1)]
        valid = [__import__("datetime").date(2026, 4, 1)]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agent = "agent-day"
            ws = self._workspace(root, agent)
            with (
                patch.object(ft003, "_repo_root", return_value=root),
                patch.object(ft003, "resolve_cli_tick_cache_dates", side_effect=[train, valid]),
                patch.object(ft003, "sweep", return_value=[]) as mock_sweep,
            ):
                ft003.main([agent, "--per-day"])

            start = json.loads(
                (ws / "logs" / "sweep_progress.log")
                .read_text(encoding="utf-8")
                .strip()
                .splitlines()[0]
            )
            self.assertFalse(mock_sweep.call_args.kwargs["bulk_days"])
            self.assertFalse(start["bulk_days"])

    def test_holdout_rejected_before_start_sweep_preserves_result(self):
        ft003 = _load_ft003()
        holdout = [__import__("datetime").date(2026, 5, 15)]
        valid = [__import__("datetime").date(2026, 4, 1)]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agent = "agent-h"
            ws = self._workspace(root, agent)
            result_path = ws / "sweep_result.jsonl"
            result_path.write_text('{"kept": true}\n', encoding="utf-8")
            with (
                patch.object(ft003, "_repo_root", return_value=root),
                patch.object(
                    ft003,
                    "resolve_cli_tick_cache_dates",
                    side_effect=[holdout, valid],
                ),
            ):
                code = ft003.main([agent])

            self.assertEqual(code, 1)
            self.assertEqual(result_path.read_text(encoding="utf-8"), '{"kept": true}\n')
            self.assertFalse((ws / "logs" / "sweep_progress.log").exists())

    def test_heartbeat_sec_cli_passed_to_tracker(self):
        ft003 = _load_ft003()
        train = [__import__("datetime").date(2026, 3, 1)]
        valid = [__import__("datetime").date(2026, 4, 1)]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agent = "agent-hb"
            self._workspace(root, agent)
            with (
                patch.object(ft003, "_repo_root", return_value=root),
                patch.object(ft003, "resolve_cli_tick_cache_dates", side_effect=[train, valid]),
                patch.object(ft003, "SweepProgressTracker") as mock_tracker_cls,
                patch.object(ft003, "sweep", return_value=[]),
            ):
                ft003.main([agent, "--heartbeat-sec", "45"])
            mock_tracker_cls.assert_called_once()
            self.assertEqual(mock_tracker_cls.call_args.kwargs["heartbeat_sec"], 45.0)

    def test_heartbeat_sec_rejects_below_minimum(self):
        ft003 = _load_ft003()
        with self.assertRaises(SystemExit):
            ft003.main(["agent-z", "--heartbeat-sec", "0"])

    def test_keyboard_interrupt_writes_sweep_failed_130(self):
        ft003 = _load_ft003()
        train = [__import__("datetime").date(2026, 3, 1)]
        valid = [__import__("datetime").date(2026, 4, 1)]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agent = "agent-k"
            ws = self._workspace(root, agent)
            with (
                patch.object(ft003, "_repo_root", return_value=root),
                patch.object(ft003, "resolve_cli_tick_cache_dates", side_effect=[train, valid]),
                patch.object(ft003, "sweep", side_effect=KeyboardInterrupt),
            ):
                code = ft003.main([agent])

            progress = json.loads(
                (ws / "logs" / "sweep_progress.log")
                .read_text(encoding="utf-8")
                .strip()
                .splitlines()[-1]
            )
        self.assertEqual(code, 130)
        self.assertEqual(progress["event"], "sweep_failed")
        self.assertEqual(progress["exit_code"], 130)

    def test_exception_writes_sweep_failed_1(self):
        ft003 = _load_ft003()
        train = [__import__("datetime").date(2026, 3, 1)]
        valid = [__import__("datetime").date(2026, 4, 1)]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agent = "agent-e"
            ws = self._workspace(root, agent)
            with (
                patch.object(ft003, "_repo_root", return_value=root),
                patch.object(ft003, "resolve_cli_tick_cache_dates", side_effect=[train, valid]),
                patch.object(ft003, "sweep", side_effect=RuntimeError("boom")),
            ):
                code = ft003.main([agent])

            progress = json.loads(
                (ws / "logs" / "sweep_progress.log")
                .read_text(encoding="utf-8")
                .strip()
                .splitlines()[-1]
            )
        self.assertEqual(code, 1)
        self.assertEqual(progress["event"], "sweep_failed")
        self.assertEqual(progress["exit_code"], 1)
        self.assertIn("boom", progress["error"])


if __name__ == "__main__":
    unittest.main()
