"""Tests for near_miss multi-day aggregation."""

from __future__ import annotations

import unittest

from reporting.near_miss_aggregate import aggregate_near_miss


class TestNearMissAggregate(unittest.TestCase):
    def test_sums_blocked_counters(self) -> None:
        daily = [
            {
                "near_miss": {
                    "blocked_both": 100,
                    "blocked_vwap_only": 10,
                    "blocked_vol_only": 5,
                    "momentum_episodes": 3,
                    "momentum_timeout": 1,
                    "closest_vwap_distance": 0.5,
                }
            },
            {
                "near_miss": {
                    "blocked_both": 200,
                    "blocked_vwap_only": 20,
                    "blocked_vol_only": 8,
                    "momentum_episodes": 4,
                    "momentum_timeout": 0,
                    "closest_vwap_distance": 0.2,
                }
            },
        ]
        agg = aggregate_near_miss(daily)
        assert agg is not None
        self.assertEqual(agg["blocked_both"], 300)
        self.assertEqual(agg["blocked_vwap_only"], 30)
        self.assertEqual(agg["closest_vwap_distance"], 0.2)
        self.assertEqual(agg["_aggregated_from_days"], 2)

    def test_empty_returns_none(self) -> None:
        self.assertIsNone(aggregate_near_miss([]))


if __name__ == "__main__":
    unittest.main()
