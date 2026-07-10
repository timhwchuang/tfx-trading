"""Unit tests for progressive capital MDD (not day-scoped)."""

from __future__ import annotations

import unittest

from trading_engine.core.risk import CapitalRiskState, compute_limit_price


class TestCapitalRiskState(unittest.TestCase):
    def test_peak_and_drawdown(self):
        s = CapitalRiskState()
        s.apply_realized_pnl(50.0)
        self.assertEqual(s.realized_pnl, 50.0)
        self.assertEqual(s.equity_peak, 50.0)
        self.assertEqual(s.current_drawdown, 0.0)

        s.apply_realized_pnl(-30.0)
        self.assertEqual(s.realized_pnl, 20.0)
        self.assertEqual(s.equity_peak, 50.0)
        self.assertEqual(s.current_drawdown, 30.0)

    def test_mdd_disabled_when_zero(self):
        s = CapitalRiskState()
        s.apply_realized_pnl(-100.0)
        self.assertFalse(s.evaluate_mdd(0))
        self.assertFalse(s.capital_frozen)
        self.assertFalse(s.evaluate_mdd(-1))
        self.assertFalse(s.capital_frozen)

    def test_mdd_breach_is_sticky(self):
        s = CapitalRiskState()
        s.apply_realized_pnl(10.0)
        s.apply_realized_pnl(-15.0)  # equity -5, peak 10, dd 15
        self.assertTrue(s.evaluate_mdd(15))
        self.assertTrue(s.capital_frozen)
        # further recovery does not auto-unfreeze
        s.apply_realized_pnl(100.0)
        self.assertFalse(s.evaluate_mdd(15))  # already frozen, no re-transition
        self.assertTrue(s.capital_frozen)

    def test_clear_resets_book(self):
        s = CapitalRiskState()
        s.apply_realized_pnl(-20.0)
        s.evaluate_mdd(10)
        self.assertTrue(s.capital_frozen)
        s.clear()
        self.assertEqual(s.realized_pnl, 0.0)
        self.assertEqual(s.equity_peak, 0.0)
        self.assertFalse(s.capital_frozen)

    def test_compute_limit_price(self):
        self.assertEqual(compute_limit_price(18000, is_buy=True, ioc_slippage=3), 18003)
        self.assertEqual(compute_limit_price(18000, is_buy=False, ioc_slippage=3), 17997)


if __name__ == "__main__":
    unittest.main()
