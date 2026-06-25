"""Phase 1 + 6: position_qty accounting, partials (within pending), sync, full exit flatten."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from trading_engine.core.order_events import FUTURES_DEAL
from trading_engine.testing.helpers import (
    arm_pending_entry,
    arm_pending_exit,
    make_broker_with_positions,
    make_host,
)


class TestPositionQty(unittest.TestCase):
    def test_entry_full_sets_qty_from_filled(self):
        host = make_host()
        arm_pending_entry(host, order_id="e1", qty=3, exchange_ts=1000)

        msg = {"price": "18005", "quantity": 3, "action": "Buy", "trade_id": "e1"}
        host.handle_order_event(FUTURES_DEAL, msg)

        self.assertEqual(host.position_qty, 3)
        self.assertTrue(host.has_position)
        self.assertEqual(host.position_dir, "Long")

    def test_partial_entry_keeps_pending_and_does_not_set_position_yet(self):
        host = make_host()
        arm_pending_entry(host, order_id="e-part", qty=2)

        msg = {"price": "18005", "quantity": 1, "action": "Buy", "trade_id": "e-part"}
        host.handle_order_event(FUTURES_DEAL, msg)

        self.assertTrue(host.is_pending)
        self.assertEqual(host.filled_qty, 1)
        self.assertEqual(host.position_qty, 0)  # not yet applied
        self.assertFalse(host.has_position)

    def test_exit_full_flattens_qty_to_zero(self):
        host = make_host()
        arm_pending_exit(host, order_id="x1", qty=2)
        host.position_qty = 2
        host.position_dir = "Long"
        host.entry_price = 18000.0

        msg = {"price": "18020", "quantity": 2, "action": "Sell", "trade_id": "x1"}
        host.handle_order_event(FUTURES_DEAL, msg)

        self.assertEqual(host.position_qty, 0)
        self.assertFalse(host.has_position)
        self.assertEqual(host.position_dir, "Flat")
        self.assertEqual(host.daily_pnl, 40.0)  # 20 pts × 2 lots

    def test_multi_lot_exit_scales_pnl_by_filled_qty(self):
        host = make_host()
        arm_pending_exit(host, order_id="x-multi", qty=3)
        host.position_qty = 3
        host.position_dir = "Long"
        host.entry_price = 18000.0

        msg = {"price": "18020", "quantity": 3, "action": "Sell", "trade_id": "x-multi"}
        host.handle_order_event(FUTURES_DEAL, msg)

        self.assertEqual(host.position_qty, 0)
        self.assertEqual(host.daily_pnl, 60.0)  # 20 pts × 3 lots

    def test_oversized_exit_fill_capped_at_position_qty(self):
        host = make_host()
        arm_pending_exit(host, order_id="x-over", qty=5)
        host.position_qty = 2
        host.position_dir = "Long"
        host.entry_price = 18000.0

        msg = {"price": "18020", "quantity": 5, "action": "Sell", "trade_id": "x-over"}
        host.handle_order_event(FUTURES_DEAL, msg)

        self.assertEqual(host.position_qty, 0)
        self.assertEqual(host.daily_pnl, 40.0)  # capped at 2 lots, not 5

    def test_multi_lot_partial_exit_pnl_uses_each_fill_price(self):
        """Multi-lot IOC exit: PnL sums per deal leg, not last price × total."""
        host = make_host()
        arm_pending_exit(host, order_id="x-partial", qty=3)
        host.position_qty = 3
        host.position_dir = "Short"
        host.entry_price = 100.0

        for price, qty in ((98.0, 1), (97.0, 1), (96.0, 1)):
            msg = {
                "price": str(price),
                "quantity": qty,
                "action": "Buy",
                "trade_id": "x-partial",
            }
            host.handle_order_event(FUTURES_DEAL, msg)

        # Short: (100-98) + (100-97) + (100-96) = 2+3+4 = 9
        self.assertEqual(host.position_qty, 0)
        self.assertEqual(host.daily_pnl, 9.0)
        self.assertFalse(host.is_pending)

    def test_partial_exit_reduces_qty_and_keeps_position(self):
        # P1-1: a single exit fill must not flatten the whole position. The
        # residual is kept and re-synced against the broker (which still shows 1).
        broker = make_broker_with_positions(
            {"code": "TXFR1", "quantity": 1, "direction": "Buy", "price": 18000.0}
        )
        host = make_host(api=broker)
        host.contract = MagicMock(code="TXFR1")
        arm_pending_exit(host, order_id="xp", qty=1)
        host.position_qty = 2
        host.position_dir = "Long"
        host.entry_price = 18000.0

        msg = {"price": "18020", "quantity": 1, "action": "Sell", "trade_id": "xp"}
        host.handle_order_event(FUTURES_DEAL, msg)

        self.assertEqual(host.position_qty, 1)
        self.assertTrue(host.has_position)
        self.assertEqual(host.position_dir, "Long")
        self.assertFalse(host.is_pending)

    def test_exit_fill_triggers_resync_to_confirm_flat(self):
        # P1-1: kernel self-believes flat after exit, but broker is the source of
        # truth. Broker still showing a position must be adopted (residual kept).
        broker = make_broker_with_positions(
            {"code": "TXFR1", "quantity": 1, "direction": "Buy", "price": 18000.0}
        )
        host = make_host(api=broker)
        host.contract = MagicMock(code="TXFR1")
        arm_pending_exit(host, order_id="xf", qty=1)
        host.position_qty = 1
        host.position_dir = "Long"
        host.entry_price = 18000.0

        msg = {"price": "18020", "quantity": 1, "action": "Sell", "trade_id": "xf"}
        host.handle_order_event(FUTURES_DEAL, msg)

        # Kernel briefly self-flattened, but the confirming re-sync re-adopted the
        # broker's residual position instead of leaving an orphan at the broker.
        self.assertEqual(host.position_qty, 1)
        self.assertEqual(host.position_dir, "Long")

    def test_sync_positions_writes_qty_from_broker(self):
        broker = make_broker_with_positions(
            {"code": "TXFR1", "quantity": 5, "direction": "Buy", "price": 17950.0}
        )
        host = make_host(api=broker)
        host.contract = MagicMock(code="TXFR1")

        host.sync_positions(force_resync=True)

        self.assertEqual(host.position_qty, 5)
        self.assertEqual(host.position_dir, "Long")
        self.assertEqual(host.entry_price, 17950.0)

    def test_sync_positions_to_flat_writes_qty_zero(self):
        broker = make_broker_with_positions()  # empty
        host = make_host(api=broker)
        host.contract = MagicMock(code="TXFR1")
        host.position_qty = 3
        host.position_dir = "Short"

        host.sync_positions(force_resync=True)

        self.assertEqual(host.position_qty, 0)
        self.assertEqual(host.position_dir, "Flat")

    def test_position_snapshot_includes_qty(self):
        host = make_host()
        host.position_qty = 4
        host.position_dir = "Short"
        host.entry_price = 18100.0

        snap = host._position_snapshot()
        self.assertEqual(snap.qty, 4)
        self.assertEqual(snap.position_dir, "Short")
        self.assertTrue(snap.has_position)
