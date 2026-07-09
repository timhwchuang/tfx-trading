"""Tests for adverse continuation guard."""

from __future__ import annotations

import unittest

from strategy_momentum_continuation.adverse_guard import adverse_blocks_continuation


class TestAdverseGuard(unittest.TestCase):
    def test_long_blocks_when_price_far_below_vwap(self) -> None:
        self.assertTrue(
            adverse_blocks_continuation(
                "Long",
                price=17970.0,
                vwap=18000.0,
                atr=20.0,
                max_adverse_atr_k=1.0,
            )
        )

    def test_long_allows_near_vwap(self) -> None:
        self.assertFalse(
            adverse_blocks_continuation(
                "Long",
                price=17985.0,
                vwap=18000.0,
                atr=20.0,
                max_adverse_atr_k=1.0,
            )
        )

    def test_disabled_when_k_zero(self) -> None:
        self.assertFalse(
            adverse_blocks_continuation(
                "Long",
                price=17900.0,
                vwap=18000.0,
                atr=20.0,
                max_adverse_atr_k=0.0,
            )
        )


if __name__ == "__main__":
    unittest.main()
