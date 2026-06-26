"""Tests for sweep.sweep_instance_lock."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sweep.sweep_instance_lock import SweepInstanceLock


class TestSweepInstanceLock(unittest.TestCase):
    def test_acquire_release_and_reacquire(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "sweep.lock"
            lock = SweepInstanceLock(lock_path)
            lock.acquire()
            self.assertTrue(lock_path.is_file())
            self.assertIn(str(os.getpid()), lock_path.read_text(encoding="utf-8"))
            lock.release()
            self.assertFalse(lock_path.exists())

            with SweepInstanceLock(lock_path):
                self.assertTrue(lock_path.is_file())
            self.assertFalse(lock_path.exists())

    def test_second_acquire_fails_while_held(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "sweep.lock"
            first = SweepInstanceLock(lock_path)
            first.acquire()
            second = SweepInstanceLock(lock_path)
            with self.assertRaises(RuntimeError):
                second.acquire()
            first.release()

    def test_stale_lock_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "sweep.lock"
            lock_path.write_text("999999 dead\n", encoding="utf-8")
            lock = SweepInstanceLock(lock_path)
            lock.acquire()
            self.assertIn(str(os.getpid()), lock_path.read_text(encoding="utf-8"))
            lock.release()

    def test_o_excl_race_maps_to_runtime_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "sweep.lock"
            lock_path.write_text("4242 ft003_run_sweep\n", encoding="utf-8")
            lock = SweepInstanceLock(lock_path)
            with (
                patch.object(Path, "exists", return_value=False),
                patch("sweep.sweep_instance_lock._pid_alive", return_value=True),
            ):
                with self.assertRaises(RuntimeError) as ctx:
                    lock.acquire()
            self.assertIn("another sweep is running", str(ctx.exception))
            self.assertIn("4242", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
