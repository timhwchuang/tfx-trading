"""Invariant: runtime order paths never call api.update_status(trade=...)."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from trading_engine.core.types import OrderSignal
from trading_engine.testing.helpers import arm_pending_entry, make_host


def _pos(qty: int, direction: str) -> SimpleNamespace:
    return SimpleNamespace(code="TXFR1", quantity=qty, direction=direction, price=100.0)


class TestNoUpdateStatusInvariant(unittest.TestCase):
    def _host(self):
        host = make_host()
        host._cfg.simulation = False
        host._cfg.reconcile_confirm_reads = 1
        host._order_sync_mode = True
        host.contract = MagicMock(code="TXFR1")
        host.api.futopt_account = MagicMock()
        host.api.list_positions.return_value = []
        host.api.order_deal_records.return_value = []
        return host

    def test_timeout_path_never_updates_status(self) -> None:
        host = self._host()
        arm_pending_entry(host, order_id="ord-1")
        host.pending_since = host._clock() - 10
        host._check_pending_timeout()
        host.api.update_status.assert_not_called()

    def test_settle_path_never_updates_status(self) -> None:
        host = self._host()
        arm_pending_entry(host, order_id="ord-1")
        host._settling = True
        host._settle_since = host._clock()
        host._settle_via_reconcile()
        host.api.update_status.assert_not_called()

    def test_place_order_path_never_updates_status(self) -> None:
        host = self._host()
        host._cfg.simulation = True
        trade = SimpleNamespace(
            order=SimpleNamespace(id="placed-1"),
            status=SimpleNamespace(
                status="Submitted", deal_quantity=0, cancel_quantity=0
            ),
        )
        host.api.place_order.return_value = trade
        host.api.list_positions.return_value = [_pos(1, "Buy")]
        signal = OrderSignal("Buy", 1, 100.0, "entry", exchange_ts=1)
        with unittest.mock.patch.object(
            host, "_call_api", side_effect=lambda fn, *a, **kw: fn(*a, **kw)
        ):
            host.place_order(signal)
        host.api.update_status.assert_not_called()


class TestCancelCallbackNoDeadlock(unittest.TestCase):
    def test_cancel_under_lock_does_not_deadlock(self) -> None:
        """Regression: _handle_futures_order must not re-acquire self.lock."""
        host = make_host()
        host.is_pending = True
        host.pending_intent = "entry"
        host.pending_order_id = "ord-cancel-1"
        host._pending_action = "Buy"
        msg = {
            "operation": {"op_type": "Cancel", "op_code": "00"},
            "status": {"status": "Cancelled", "deal_quantity": 0},
            "trade_id": "ord-cancel-1",
        }
        with host.lock:
            host._handle_futures_order(msg)
        self.assertFalse(host.is_pending)


if __name__ == "__main__":
    unittest.main()
