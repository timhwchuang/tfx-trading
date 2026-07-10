"""Unit tests for reconcile pure helpers (no broker)."""

from __future__ import annotations

import threading
import unittest
from types import SimpleNamespace

from trading_engine.integrity import IntegrityState
from trading_engine.reconcile import is_severe_drift, severe_drift_confirmed


class TestSevereDrift(unittest.TestCase):
    def test_kernel_flat_broker_long(self):
        self.assertTrue(is_severe_drift(0, "Flat", 1, "Long"))

    def test_direction_reversal(self):
        self.assertTrue(is_severe_drift(1, "Long", 1, "Short"))

    def test_qty_mismatch_same_dir_not_severe(self):
        # Mild drift (qty only) is not severe — adopt + block entry path.
        self.assertFalse(is_severe_drift(1, "Long", 2, "Long"))

    def test_match_not_severe(self):
        self.assertFalse(is_severe_drift(1, "Long", 1, "Long"))
        self.assertFalse(is_severe_drift(0, "Flat", 0, "Flat"))


class TestSevereDriftConfirmed(unittest.TestCase):
    def _host(self, *, need: int = 2) -> SimpleNamespace:
        return SimpleNamespace(
            lock=threading.Lock(),
            _cfg=SimpleNamespace(reconcile_confirm_reads=need),
            _integrity=IntegrityState(),
        )

    def test_streak_reaches_need(self):
        host = self._host(need=2)
        self.assertFalse(
            severe_drift_confirmed(host, 0, "Flat", 1, "Long")
        )
        self.assertEqual(host._integrity._severe_drift_read_streak, 1)
        self.assertTrue(
            severe_drift_confirmed(host, 0, "Flat", 1, "Long")
        )
        self.assertEqual(host._integrity._severe_drift_read_streak, 2)

    def test_broker_tuple_change_resets_streak(self):
        host = self._host(need=2)
        severe_drift_confirmed(host, 0, "Flat", 1, "Long")
        self.assertEqual(host._integrity._severe_drift_read_streak, 1)
        severe_drift_confirmed(host, 0, "Flat", 2, "Long")
        self.assertEqual(host._integrity._severe_drift_read_streak, 1)
        self.assertEqual(host._integrity._severe_drift_broker_read, (2, "Long"))

    def test_non_severe_clears_streak(self):
        host = self._host(need=2)
        severe_drift_confirmed(host, 0, "Flat", 1, "Long")
        self.assertEqual(host._integrity._severe_drift_read_streak, 1)
        self.assertFalse(
            severe_drift_confirmed(host, 1, "Long", 1, "Long")
        )
        self.assertEqual(host._integrity._severe_drift_read_streak, 0)
        self.assertIsNone(host._integrity._severe_drift_broker_read)


if __name__ == "__main__":
    unittest.main()
