"""EXEC_AUDIT pending_armed contract: defer when order_id empty at place time."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from trading_engine.core.order_events import FUTURES_DEAL, FUTURES_ORDER
from trading_engine.core.types import OrderSignal
from trading_engine.testing.helpers import arm_pending_entry, arm_pending_exit, make_host


class TestPendingArmedAudit(unittest.TestCase):
    def test_place_order_skips_armed_when_order_id_empty(self):
        host = make_host()
        host.contract = MagicMock(code="TXFR1")
        host.api.futopt_account = MagicMock()
        trade = MagicMock()
        trade.order = SimpleNamespace(id="")
        host.api.place_order.return_value = trade

        host.is_pending = True
        host.pending_intent = "entry"
        host.pending_signal_id = "sig-001"
        host.pending_limit_price = 18003.0

        logged: list[str] = []

        def _capture(msg, *args, **kwargs):
            logged.append(msg % args if args else str(msg))

        with patch("trading_engine.order_executor.logger.info", side_effect=_capture):
            host.place_order(
                OrderSignal(
                    "Buy",
                    1,
                    18000.0,
                    "entry",
                    exchange_ts=100,
                    signal_id="sig-001",
                )
            )

        armed_lines = [
            line for line in logged if "EXEC_AUDIT" in line and "pending_armed" in line
        ]
        self.assertEqual(armed_lines, [])
        self.assertEqual(host.pending_order_id, "")

    def test_place_order_emits_armed_when_order_id_known(self):
        host = make_host()
        host.contract = MagicMock(code="TXFR1")
        host.api.futopt_account = MagicMock()
        trade = MagicMock()
        trade.order = SimpleNamespace(id="OID-immediate")
        host.api.place_order.return_value = trade

        host.is_pending = True
        host.pending_intent = "entry"
        host.pending_signal_id = "sig-002"
        host.pending_limit_price = 18003.0

        logged: list[str] = []

        def _capture(msg, *args, **kwargs):
            logged.append(msg % args if args else str(msg))

        with patch("trading_engine.order_executor.logger.info", side_effect=_capture):
            host.place_order(
                OrderSignal(
                    "Buy",
                    1,
                    18000.0,
                    "entry",
                    exchange_ts=120,
                    signal_id="sig-002",
                )
            )

        armed_lines = [
            line for line in logged if "EXEC_AUDIT" in line and "pending_armed" in line
        ]
        self.assertEqual(len(armed_lines), 1)
        self.assertIn("OID-immediate", armed_lines[0])
        self.assertNotIn("backfilled", armed_lines[0])

    def test_order_callback_backfill_emits_single_armed(self):
        host = make_host()
        host.is_pending = True
        host.pending_intent = "entry"
        host.pending_order_id = ""
        host.pending_signal_id = "sig-003"
        host.pending_limit_price = 18003.0
        host._pending_action = "Buy"
        host.pending_exchange_ts = 100

        logged: list[str] = []

        def _capture(msg, *args, **kwargs):
            logged.append(msg % args if args else str(msg))

        order_msg = {
            "operation": {"op_code": "00", "op_type": "New"},
            "status": {"status": "Submitted", "deal_quantity": 0},
            "trade_id": "OID-backfill",
        }

        with patch("trading_engine.order_executor.logger.info", side_effect=_capture):
            host.handle_order_event(FUTURES_ORDER, order_msg)

        armed_lines = [
            line for line in logged if "EXEC_AUDIT" in line and "pending_armed" in line
        ]
        self.assertEqual(len(armed_lines), 1)
        self.assertIn("OID-backfill", armed_lines[0])
        self.assertIn("backfilled", armed_lines[0])
        self.assertEqual(host.pending_order_id, "OID-backfill")

    def test_deal_first_backfill_emits_single_armed(self):
        host = make_host()
        arm_pending_entry(host, order_id="", signal_price=18000.0, exchange_ts=200)
        host.pending_signal_id = "sig-004"
        host._pending_action = "Buy"

        logged: list[str] = []

        def _capture(msg, *args, **kwargs):
            logged.append(msg % args if args else str(msg))

        deal_msg = {
            "price": "18010",
            "quantity": 1,
            "action": "Buy",
            "trade_id": "OID-deal-first",
        }

        with patch("trading_engine.order_executor.logger.info", side_effect=_capture):
            host.handle_order_event(FUTURES_DEAL, deal_msg)

        armed_lines = [
            line for line in logged if "EXEC_AUDIT" in line and "pending_armed" in line
        ]
        self.assertEqual(len(armed_lines), 1)
        self.assertIn("OID-deal-first", armed_lines[0])
        self.assertIn("backfilled from deal", armed_lines[0])
        # Deal completes the pending lifecycle; order_id is cleared with _clear_pending.
        self.assertFalse(host.is_pending)
        self.assertEqual(host.position_qty, 1)

    def test_sim_timeout_resolves_cleanly_when_broker_consistent(self):
        """P0-5: timeout with an empty order_id, but the broker confirms the
        position is unchanged and consistent → clean resolution (no HALT, no
        block). Outcome is UNKNOWN-then-confirmed, not FAILED."""
        alerts = MagicMock()
        host = make_host()
        host._alerts = alerts
        host._cfg.simulation = True
        arm_pending_exit(host, order_id="")
        host.position_qty = 1
        host.position_dir = "Long"
        host.contract = MagicMock(code="TXFR1")
        host.api.list_positions.return_value = [
            SimpleNamespace(code="TXFR1", quantity=1, direction="Buy", price=18000.0)
        ]
        host.pending_since = host._clock() - host._cfg.pending_timeout_sec - 1
        host.pending_trade = MagicMock()

        host._check_pending_timeout()

        self.assertFalse(host.is_pending)
        self.assertFalse(host._settling)
        self.assertFalse(host.block_new_entry)
        self.assertFalse(host._position_unconfirmed)
        self.assertEqual(host.position_qty, 1)


if __name__ == "__main__":
    unittest.main()