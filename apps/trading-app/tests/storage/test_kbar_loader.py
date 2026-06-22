"""K-bar timestamp conversion (simulation vs production API)."""

from __future__ import annotations

import datetime
import unittest

from storage.kbar_loader import kbar_ts_from_ns
from storage.tick_loader import _ns_to_taipei_naive


class TestKbarTsFromNs(unittest.TestCase):
    def test_simulation_wall_clock_as_utc_epoch(self):
        """UAT simulation: 10:26 exchange time is stored as UTC epoch 10:26 (not +8)."""
        wall_as_utc = datetime.datetime(
            2026, 6, 22, 10, 26, 0, tzinfo=datetime.timezone.utc
        )
        ts_ns = int(wall_as_utc.timestamp() * 1_000_000_000)
        dt = kbar_ts_from_ns(ts_ns, simulation=True)
        self.assertEqual(dt, datetime.datetime(2026, 6, 22, 10, 26, 0))

    def test_simulation_old_conversion_would_add_eight_hours(self):
        wall_as_utc = datetime.datetime(
            2026, 6, 22, 10, 26, 0, tzinfo=datetime.timezone.utc
        )
        ts_ns = int(wall_as_utc.timestamp() * 1_000_000_000)
        wrong = _ns_to_taipei_naive(ts_ns)
        self.assertEqual(wrong, datetime.datetime(2026, 6, 22, 18, 26, 0))

    def test_production_true_utc_epoch(self):
        """Production kbars.ts: true UTC epoch -> Taipei naive via +8."""
        true_utc = datetime.datetime(
            2026, 6, 22, 2, 26, 0, tzinfo=datetime.timezone.utc
        )
        ts_ns = int(true_utc.timestamp() * 1_000_000_000)
        dt = kbar_ts_from_ns(ts_ns, simulation=False)
        self.assertEqual(dt, datetime.datetime(2026, 6, 22, 10, 26, 0))


if __name__ == "__main__":
    unittest.main()
