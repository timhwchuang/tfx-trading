"""Phase C/G1: connectivity / integrity / ticks composition (explicit owners)."""

from __future__ import annotations

import unittest

from trading_engine.connectivity import ConnectivityState
from trading_engine.integrity import IntegrityState
from trading_engine.testing.helpers import make_host
from trading_engine.ticks import TickState


class TestPhaseCState(unittest.TestCase):
    def test_engine_composes_link_and_integrity(self):
        host = make_host()
        host._link._api_connected = False
        self.assertFalse(host._link._api_connected)
        host._integrity._settling = True
        self.assertTrue(host._integrity._settling)
        host._integrity.clear_settling_window()
        self.assertFalse(host._integrity._settling)
        host._ticks._no_tick_resubscribe_streak = 3
        self.assertEqual(host._ticks._no_tick_resubscribe_streak, 3)

    def test_day_ops_resets_composed_states(self):
        host = make_host()
        host._link._disconnect_count_today = 2
        host._integrity._position_unconfirmed = True
        host._integrity._consecutive_missed_entries = 2
        host._ticks._tick_type_counts[1] = 9
        host._reset_daily_state()
        self.assertEqual(host._link._disconnect_count_today, 0)
        self.assertFalse(host._integrity._position_unconfirmed)
        self.assertEqual(host._integrity._consecutive_missed_entries, 0)
        self.assertEqual(host._ticks._tick_type_counts[1], 0)

    def test_state_dataclasses_standalone(self):
        link = ConnectivityState()
        link._disconnect_count_today = 1
        link.reset_day_ops()
        self.assertEqual(link._disconnect_count_today, 0)
        integ = IntegrityState()
        integ._settling = True
        integ.clear_settling_window()
        self.assertFalse(integ._settling)
        ticks = TickState()
        ticks._tick_type_counts[0] = 5
        ticks.reset_day_counters()
        self.assertEqual(ticks._tick_type_counts[0], 0)

    def test_clear_settling_does_not_lift_halt(self):
        """P0-5: clearing pending/SETTLING must leave HALT sticky."""
        host = make_host()
        host._integrity._settling = True
        host._integrity._settle_since = 1.0
        host._integrity._reconcile_last_read = (1, "Long")
        host._integrity._reconcile_read_streak = 2
        host._integrity._position_unconfirmed = True

        host._integrity.clear_settling_window()
        self.assertFalse(host._integrity._settling)
        self.assertEqual(host._integrity._settle_since, 0.0)
        self.assertIsNone(host._integrity._reconcile_last_read)
        self.assertEqual(host._integrity._reconcile_read_streak, 0)
        self.assertTrue(host._integrity._position_unconfirmed)

        # Full pending clear path also must not lift HALT.
        host._integrity._settling = True
        host._integrity._position_unconfirmed = True
        host._book.is_pending = True
        host._book.pending_intent = "exit"
        host._clear_pending()
        self.assertFalse(host._book.is_pending)
        self.assertFalse(host._integrity._settling)
        self.assertTrue(host._integrity._position_unconfirmed)


if __name__ == "__main__":
    unittest.main()
