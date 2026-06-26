"""Tests for sweep.sweep_instance_lock."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
