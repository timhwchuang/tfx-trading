"""Order event stat normalization (incl. Shioaji OrderState quirk)."""

from __future__ import annotations

import unittest

from trading_engine.core.order_events import (
    FUTURES_DEAL,
    FUTURES_ORDER,
    is_futures_deal,
    is_futures_order,
    normalize_order_stat,
)


class TestOrderEvents(unittest.TestCase):
    def test_string_stats(self):
        self.assertEqual(normalize_order_stat(FUTURES_ORDER), FUTURES_ORDER)
        self.assertTrue(is_futures_order(FUTURES_ORDER))
        self.assertTrue(is_futures_deal(FUTURES_DEAL))

    def test_shioaji_order_state_enum(self):
        try:
            import shioaji as sj
        except ImportError:
            self.skipTest("shioaji not installed")

        order_stat = sj.OrderState.FuturesOrder
        deal_stat = sj.OrderState.FuturesDeal
        # Shioaji marks OrderState as str-like; must still route callbacks correctly.
        self.assertIsInstance(order_stat, str)
        self.assertEqual(normalize_order_stat(order_stat), FUTURES_ORDER)
        self.assertEqual(normalize_order_stat(deal_stat), FUTURES_DEAL)
        self.assertTrue(is_futures_order(order_stat))
        self.assertTrue(is_futures_deal(deal_stat))
        self.assertFalse(is_futures_order(deal_stat))
        self.assertFalse(is_futures_deal(order_stat))


if __name__ == "__main__":
    unittest.main()
