"""Phase 6: reconnect + timeout + reconcile races."""

from __future__ import annotations

import threading
import unittest
from unittest.mock import MagicMock

from trading_engine.testing.helpers import arm_pending_exit, make_host
from trading_engine.engine import AtrRefreshResult, ReconnectOutcome


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
        # Broker position query fails -> reconcile cannot confirm -> timeout path.
        host.api.list_positions.side_effect = RuntimeError("broker unavailable")

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
        host.refresh_atr = MagicMock(return_value=AtrRefreshResult(True))

        host._on_reconnected()

        host.sync_positions.assert_called()
        self.assertTrue(host._api_connected)

    def test_on_reconnected_reattaches_trade_report_channel(self):
        # P0-1: reconnect must re-attach the order/deal report channel, not only
        # quote ticks. Otherwise fills arrive silently and orders perpetually
        # time out (the 24-lot phantom-short root cause).
        host = make_host()
        host._api_connected = False
        host._disconnect_since = host._clock() - 100
        host.contract = MagicMock(code="TXFR1")
        host.sync_positions = MagicMock()
        host._resubscribe_ticks = MagicMock()
        host._resubscribe_trade = MagicMock()
        host.refresh_atr = MagicMock(return_value=AtrRefreshResult(True))

        host._on_reconnected()

        host._resubscribe_ticks.assert_called()
        host._resubscribe_trade.assert_called()

    def test_reconnect_trade_resubscribe_failure_degrades_session(self):
        # P0-1: if re-attaching the trade channel fails, the session must be
        # marked unhealthy (STALE) rather than continuing to trade blind.
        host = make_host()
        host._api_connected = False
        host._disconnect_since = host._clock() - 100
        host.contract = MagicMock(code="TXFR1")
        host.sync_positions = MagicMock()
        host._resubscribe_ticks = MagicMock()
        host._resubscribe_trade = MagicMock(side_effect=RuntimeError("subscribe_trade failed"))
        host.refresh_atr = MagicMock(return_value=AtrRefreshResult(True))

        outcome = host._on_reconnected()

        self.assertEqual(outcome, ReconnectOutcome.UNHEALTHY)
        self.assertFalse(host._api_connected)

    def test_stale_reconnect_does_not_undo_healthy_state(self):
        host = make_host()
        host._api_connected = True
        host._disconnect_count_today = 0
        host.contract = MagicMock(code="TXFR1")
        host.sync_positions = MagicMock()
        host._resubscribe_ticks = MagicMock()

        started = threading.Event()
        proceed = threading.Event()

        def slow_unhealthy_refresh():
            started.set()
            proceed.wait(timeout=1)
            return AtrRefreshResult(False, True)

        host.refresh_atr = MagicMock(side_effect=slow_unhealthy_refresh)

        stale = threading.Thread(target=host._on_reconnected, name="stale-reconnect")
        stale.start()
        started.wait(timeout=1)

        host.refresh_atr = MagicMock(return_value=AtrRefreshResult(True))
        self.assertEqual(host._on_reconnected(), ReconnectOutcome.HEALTHY)
        self.assertTrue(host._api_connected)

        proceed.set()
        stale.join(timeout=2)
        self.assertTrue(host._api_connected)
        self.assertEqual(host._disconnect_count_today, 0)

    def test_unhealthy_reconnect_does_not_undo_newer_healthy(self):
        host = make_host()
        host._api_connected = True
        host._disconnect_count_today = 0
        host.contract = MagicMock(code="TXFR1")
        host.sync_positions = MagicMock()
        host._resubscribe_ticks = MagicMock()

        started = threading.Event()
        proceed = threading.Event()

        def slow_unhealthy_atr():
            started.set()
            proceed.wait(timeout=1)
            return AtrRefreshResult(False, True)

        host.refresh_atr = MagicMock(side_effect=slow_unhealthy_atr)

        slow = threading.Thread(target=host._on_reconnected, name="slow-unhealthy")
        slow.start()
        started.wait(timeout=1)

        host.refresh_atr = MagicMock(return_value=AtrRefreshResult(True))
        self.assertEqual(host._on_reconnected(), ReconnectOutcome.HEALTHY)
        self.assertTrue(host._api_connected)

        proceed.set()
        slow.join(timeout=2)
        self.assertTrue(host._api_connected)
        self.assertEqual(host._disconnect_count_today, 0)

    def test_newer_unhealthy_reconnect_does_not_tear_down_established_session(self):
        host = make_host()
        host._api_connected = False
        host.sync_positions = MagicMock()
        host._resubscribe_ticks = MagicMock()
        host.refresh_atr = MagicMock(return_value=AtrRefreshResult(True))

        self.assertEqual(host._on_reconnected(), ReconnectOutcome.HEALTHY)
        self.assertTrue(host._api_connected)
        established_gen = host._connected_reconnect_generation

        host.refresh_atr = MagicMock(return_value=AtrRefreshResult(False, True))
        outcome = host._on_reconnected()

        self.assertEqual(outcome, ReconnectOutcome.STALE)
        self.assertTrue(host._api_connected)
        self.assertEqual(host._connected_reconnect_generation, established_gen)
        self.assertEqual(host._disconnect_count_today, 0)
