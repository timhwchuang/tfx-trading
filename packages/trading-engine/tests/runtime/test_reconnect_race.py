"""Phase 6: reconnect + timeout + reconcile races."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from trading_engine.testing.helpers import arm_pending_exit, make_host


class TestReconnectRace(unittest.TestCase):
    def test_reconcile_on_reconnect_confirms_fill(self):
        host = make_host()
        host._cfg.simulation = False  # force non-sim path for records
        arm_pending_exit(host, order_id="r1")
        host.position_qty = 1
        host.position_dir = "Long"
        host.entry_price = 18000.0

        # Simulate via order_deal_records (preferred non-mutating path)
        # Return a deal event for the order_id
        host.api.order_deal_records.return_value = [
            ("FuturesDeal", {"trade_id": "r1", "price": 18015.0, "quantity": 1, "action": "Sell"})
        ]

        host.pending_trade = MagicMock()
        host.pending_trade.order.id = "r1"

        # Force the reconcile path
        host._reconcile_pending_trade(host.pending_trade)

        # After reconcile the position should be flattened (deal applied)
        self.assertEqual(host.position_qty, 0)

    def test_timeout_reconcile_with_no_broker_result_clears_and_alerts(self):
        host = make_host()
        arm_pending_exit(host)
        host.position_qty = 1
        trade = MagicMock()
        trade.order.id = host.pending_order_id
        host.pending_trade = trade

        # Make update_status and records return nothing useful
        host.api.update_status.return_value = None
        host.api.order_deal_records.return_value = []

        host._check_pending_timeout()

        # Pending should be cleared after timeout path
        self.assertFalse(host.is_pending)
        # block_new_entry set on hard timeout
        self.assertTrue(host.block_new_entry)

    def test_reconnect_after_disconnect_triggers_sync_and_reconcile(self):
        host = make_host()
        host._api_connected = False
        host._disconnect_since = host._clock() - 100
        host.contract = MagicMock(code="TXFR1")
        host.api.login = MagicMock()
        host.sync_positions = MagicMock()
        host.refresh_atr = MagicMock()

        host._on_reconnected()

        host.sync_positions.assert_called()
        self.assertTrue(host._api_connected)
