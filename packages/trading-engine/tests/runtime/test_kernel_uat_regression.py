"""KERNEL.md Phase B regression: B3 reconnect, B4 pending timeout, B6 snapshot sync."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from trading_engine.testing.helpers import (
    arm_pending_exit,
    make_broker_with_positions,
    make_host,
)


class _ImmediateThread:
    def __init__(self, target=None, args=(), kwargs=None, **kw):
        self._target = target

    def start(self) -> None:
        if self._target is not None:
            self._target()


class TestKernelUatRegression(unittest.TestCase):
    def test_b3_session_event_12_marks_disconnected(self):
        host = make_host()
        host._api_connected = True
        host._disconnect_since = 0.0

        host.handle_session_event(0, 12, "reconnecting", "")

        self.assertFalse(host._api_connected)
        self.assertGreater(host._disconnect_since, 0.0)

    def test_b3_session_event_13_triggers_reconnect_sync(self):
        host = make_host()
        host._api_connected = False
        host.sync_positions = MagicMock()
        host.refresh_atr = MagicMock()
        host._resubscribe_ticks = MagicMock()
        host._reconcile_pending_trade = MagicMock()

        arm_pending_exit(host, order_id="reconnect-ord")
        trade = MagicMock()
        trade.order.id = host.pending_order_id
        host.pending_trade = trade

        with patch("trading_engine.engine.threading.Thread", _ImmediateThread):
            host.handle_session_event(0, 13, "ok", "")

        host._reconcile_pending_trade.assert_called_with(trade)
        host.sync_positions.assert_called()
        host._resubscribe_ticks.assert_called()
        host.refresh_atr.assert_called()
        self.assertTrue(host._api_connected)

    def test_b4_pending_timeout_critical_alert_and_sync(self):
        alerts = MagicMock()
        host = make_host()
        host._alerts = alerts
        host.sync_positions = MagicMock()

        logged: list[str] = []

        def _capture_info(msg, *args, **kwargs):
            logged.append(msg % args if args else str(msg))

        arm_pending_exit(host, order_id="timeout-ord")
        host.position_qty = 1
        host.pending_since = host._clock() - host._cfg.pending_timeout_sec - 1
        trade = MagicMock()
        trade.order.id = host.pending_order_id
        host.pending_trade = trade
        host.api.update_status.return_value = None
        host.api.order_deal_records.return_value = []

        with patch("trading_engine.order_executor.logger.info", side_effect=_capture_info):
            host._check_pending_timeout()

        self.assertFalse(host.is_pending)
        self.assertTrue(host.block_new_entry)
        host.sync_positions.assert_called()
        alerts.send.assert_called()
        self.assertEqual(alerts.send.call_args.kwargs.get("level"), "CRITICAL")
        self.assertTrue(
            any("EXEC_AUDIT" in line and "pending_timeout" in line for line in logged),
            f"expected EXEC_AUDIT pending_timeout log line, got: {logged}",
        )

    def test_b6_sync_positions_matches_get_state_snapshot_long(self):
        broker = make_broker_with_positions(
            {"code": "TXFR1", "quantity": 2, "direction": "Buy", "price": 17950.0}
        )
        host = make_host(api=broker)
        host.contract = MagicMock(code="TXFR1")
        host.position_qty = 0
        host.position_dir = "Flat"

        host.sync_positions()
        snap = host.get_state_snapshot()

        self.assertEqual(snap.position_qty, 2)
        self.assertEqual(snap.position_dir, "Long")
        self.assertAlmostEqual(snap.entry_price, 17950.0)
        self.assertTrue(snap.has_position)

    def test_b6_sync_positions_matches_get_state_snapshot_flat(self):
        broker = make_broker_with_positions(
            {"code": "TXFR1", "quantity": 0, "direction": "Buy", "price": 0.0}
        )
        host = make_host(api=broker)
        host.contract = MagicMock(code="TXFR1")
        host.position_qty = 3
        host.position_dir = "Long"
        host.entry_price = 18000.0

        host.sync_positions()
        snap = host.get_state_snapshot()

        self.assertEqual(snap.position_qty, 0)
        self.assertEqual(snap.position_dir, "Flat")
        self.assertFalse(snap.has_position)


if __name__ == "__main__":
    unittest.main()