"""Buy/Sell round-trip smoke tests (mock callbacks, no live Shioaji)."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from trading_engine.core.order_events import FUTURES_DEAL, FUTURES_ORDER
from trading_engine.core.types import OrderSignal
from trading_engine.testing.helpers import make_host


def _deal(order_id: str, *, action: str, price: str, qty: int = 1) -> dict:
    return {
        "price": price,
        "quantity": qty,
        "action": action,
        "trade_id": order_id,
    }


def _order_new(order_id: str, *, status: str = "Submitted") -> dict:
    return {
        "operation": {"op_code": "00", "op_type": "New"},
        "status": {"status": status, "deal_quantity": 0},
        "trade_id": order_id,
    }


def _order_cancel(order_id: str) -> dict:
    return {
        "operation": {"op_type": "Cancel", "op_code": "00"},
        "status": {"status": "Cancelled", "deal_quantity": 0},
        "trade_id": order_id,
    }


class TestOrderSmoke(unittest.TestCase):
    """Minimal buy → sell lifecycle through handle_order_event (kernel smoke)."""

    def test_buy_then_sell_round_trip(self):
        host = make_host()
        host._validate_order_signal = MagicMock(return_value=True)

        entry = OrderSignal("Buy", 1, 18000.0, "entry", exchange_ts=100, signal_id="smoke-sig-001")
        host._arm_pending(entry)
        host.handle_order_event(FUTURES_ORDER, _order_new("smoke-buy-1"))
        host.handle_order_event(FUTURES_DEAL, _deal("smoke-buy-1", action="Buy", price="18003"))

        self.assertFalse(host.is_pending)
        self.assertEqual(host.position_qty, 1)
        self.assertEqual(host.position_dir, "Long")

        exit_sig = OrderSignal("Sell", 1, 18010.0, "exit", exchange_ts=200, signal_id="smoke-sig-002")
        host._arm_pending(exit_sig)
        host.handle_order_event(FUTURES_ORDER, _order_new("smoke-sell-1"))
        host.handle_order_event(FUTURES_DEAL, _deal("smoke-sell-1", action="Sell", price="18007"))

        self.assertFalse(host.is_pending)
        self.assertEqual(host.position_qty, 0)
        self.assertEqual(host.position_dir, "Flat")
        self.assertGreater(host.daily_pnl, 0)

    def test_buy_cancel_no_fill_clears_pending(self):
        host = make_host()
        host._validate_order_signal = MagicMock(return_value=True)

        entry = OrderSignal("Buy", 1, 18000.0, "entry", exchange_ts=100, signal_id="smoke-sig-003")
        host._arm_pending(entry)
        host.handle_order_event(FUTURES_ORDER, _order_new("smoke-buy-ioc"))
        host.handle_order_event(FUTURES_ORDER, _order_cancel("smoke-buy-ioc"))

        self.assertFalse(host.is_pending)
        self.assertEqual(host.position_qty, 0)

    def test_place_order_buy_with_empty_order_id_then_callback_backfill(self):
        host = make_host()
        host.contract = MagicMock(code="TMFR1")
        host.api.futopt_account = MagicMock()
        trade = MagicMock()
        trade.order = SimpleNamespace(id="")
        host.api.place_order.return_value = trade

        host._validate_order_signal = MagicMock(return_value=True)
        host._arm_pending(
            OrderSignal("Buy", 1, 18000.0, "entry", exchange_ts=100, signal_id="smoke-sig-004")
        )
        host.place_order(
            OrderSignal("Buy", 1, 18000.0, "entry", exchange_ts=100, signal_id="smoke-sig-004")
        )
        self.assertEqual(host.pending_order_id, "")

        host.handle_order_event(FUTURES_ORDER, _order_new("cb-backfill-1"))
        self.assertEqual(host.pending_order_id, "cb-backfill-1")

        host.handle_order_event(FUTURES_DEAL, _deal("cb-backfill-1", action="Buy", price="18003"))
        self.assertEqual(host.position_qty, 1)
        self.assertFalse(host.is_pending)

    def test_simulation_timeout_when_no_callback(self):
        """Documents UAT failure mode: sim reconcile short-circuits, no callback → timeout."""
        alerts = MagicMock()
        host = make_host()
        host._alerts = alerts
        host._cfg.simulation = True
        host._validate_order_signal = MagicMock(return_value=True)

        host._arm_pending(
            OrderSignal("Buy", 1, 18000.0, "exit", exchange_ts=100, signal_id="smoke-sig-005")
        )
        host.position_qty = 1
        host.position_dir = "Long"
        host.pending_trade = MagicMock()
        host.pending_since = host._clock() - host._cfg.pending_timeout_sec - 1

        host._check_pending_timeout()

        self.assertFalse(host.is_pending)
        self.assertTrue(host.block_new_entry)
        alerts.send.assert_called()
        self.assertIn("CRITICAL", alerts.send.call_args.kwargs.get("level", ""))


if __name__ == "__main__":
    unittest.main()
