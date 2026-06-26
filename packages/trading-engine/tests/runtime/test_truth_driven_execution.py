"""P0-5 (truth-driven execution): timeout = UNKNOWN, freeze on uncertainty,
broker position is the single source of truth, kernel converges via a single
flatten. Regression for the ">1 lot from cascading re-issued orders" incident.
"""

from __future__ import annotations

import datetime
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from trading_engine.core.types import OrderSignal
from trading_engine.testing.helpers import arm_pending_exit, make_host


def _pos(qty: int, direction: str, price: float = 100.0) -> SimpleNamespace:
    return SimpleNamespace(code="TXFR1", quantity=qty, direction=direction, price=price)


class TestFreezeOnUncertainty(unittest.TestCase):
    def test_settling_rejects_new_entry_and_exit(self) -> None:
        host = make_host()
        host._settling = True
        host.position_qty = 1
        host.position_dir = "Long"
        entry = OrderSignal("Buy", 1, 100.0, "entry", exchange_ts=1)
        exit_ = OrderSignal("Sell", 1, 100.0, "exit", exchange_ts=1)
        self.assertFalse(host._validate_order_signal(entry))
        self.assertFalse(host._validate_order_signal(exit_))

    def test_unconfirmed_rejects_new_entry_and_exit(self) -> None:
        host = make_host()
        host._position_unconfirmed = True
        host.position_qty = 1
        host.position_dir = "Long"
        entry = OrderSignal("Buy", 1, 100.0, "entry", exchange_ts=1)
        exit_ = OrderSignal("Sell", 1, 100.0, "exit", exchange_ts=1)
        self.assertFalse(host._validate_order_signal(entry))
        self.assertFalse(host._validate_order_signal(exit_))

    def test_kernel_converging_flag_bypasses_freeze_for_exit(self) -> None:
        host = make_host()
        host._position_unconfirmed = True
        host.position_qty = 1
        host.position_dir = "Long"
        host._kernel_converging = True
        exit_ = OrderSignal("Sell", 1, 100.0, "exit", exchange_ts=1)
        self.assertTrue(host._validate_order_signal(exit_))


class TestLateFillAttribution(unittest.TestCase):
    def test_late_deal_during_settling_attributes_no_orphan_no_double(self) -> None:
        """During SETTLING the pending stays in flight, so a late fill for that
        same order attributes correctly instead of becoming an orphan / extra lot.
        """
        host = make_host()
        host._cfg.simulation = True
        host.contract = MagicMock(code="TXFR1")
        host.position_qty = 1
        host.position_dir = "Long"
        host.entry_price = 100.0
        arm_pending_exit(host, order_id="X", signal_price=100.0)
        # Enter settling; broker is momentarily unreadable so it won't resolve.
        host._settling = True
        host._settle_since = host._clock()
        host.api.list_positions.side_effect = RuntimeError("down")

        # The delayed deal callback for the SAME pending order finally arrives.
        host.handle_order_event(
            "FuturesDeal",
            {"price": 99.0, "quantity": 1, "action": "Sell", "trade_id": "X"},
        )

        self.assertEqual(host.position_qty, 0)
        self.assertFalse(host.is_pending)
        self.assertFalse(host._settling)
        self.assertFalse(host._position_unconfirmed)

    def test_mismatched_deal_while_pending_halts_and_enters_settling(self) -> None:
        """A fill for a different order while pending → HALT, but it must also
        transition the in-flight pending into SETTLING so the broker poll /
        convergence starts immediately (not after pending_timeout_sec)."""
        host = make_host()
        host.contract = MagicMock(code="TXFR1")
        host.api.futopt_account = MagicMock()
        host.api.list_positions.return_value = [_pos(1, "Buy")]
        arm_pending_exit(host, order_id="A")
        host.position_qty = 1
        host.position_dir = "Long"

        host.handle_order_event(
            "FuturesDeal",
            {"price": 100.0, "quantity": 1, "action": "Buy", "trade_id": "B"},
        )

        self.assertTrue(host._position_unconfirmed)
        self.assertTrue(host.block_new_entry)
        self.assertTrue(host._settling)
        self.assertTrue(host.is_pending)

    def test_orphan_deal_with_no_pending_halts(self) -> None:
        host = make_host()
        host.contract = MagicMock(code="TXFR1")
        host.api.futopt_account = MagicMock()
        host.api.list_positions.return_value = [_pos(1, "Buy")]

        host.handle_order_event(
            "FuturesDeal",
            {"price": 100.0, "quantity": 1, "action": "Buy", "trade_id": "Z"},
        )

        self.assertTrue(host._position_unconfirmed)
        self.assertTrue(host.block_new_entry)


class TestSettleResolution(unittest.TestCase):
    def _arm_timed_out_exit(self, host) -> None:
        host._cfg.simulation = True
        host.contract = MagicMock(code="TXFR1")
        host.api.futopt_account = MagicMock()
        host.position_qty = 1
        host.position_dir = "Long"
        host.entry_price = 100.0
        arm_pending_exit(host, order_id="X", signal_price=100.0)
        host.pending_trade = MagicMock()
        host.pending_since = host._clock() - host._cfg.pending_timeout_sec - 1

    def test_exit_nofill_consistent_resolves_cleanly(self) -> None:
        host = make_host()
        self._arm_timed_out_exit(host)
        host.api.list_positions.return_value = [_pos(1, "Buy")]  # unchanged

        host._check_pending_timeout()

        self.assertFalse(host.is_pending)
        self.assertFalse(host._settling)
        self.assertFalse(host._position_unconfirmed)
        self.assertFalse(host.block_new_entry)
        self.assertEqual(host.position_qty, 1)

    def test_exit_filled_confirmed_resolves_to_flat(self) -> None:
        host = make_host()
        self._arm_timed_out_exit(host)
        host.api.list_positions.return_value = []  # broker flat -> exit filled

        host._check_pending_timeout()

        self.assertFalse(host.is_pending)
        self.assertFalse(host._position_unconfirmed)
        self.assertEqual(host.position_qty, 0)

    def test_unreadable_broker_settles_then_halts_after_window(self) -> None:
        host = make_host()
        host._alerts = MagicMock()
        self._arm_timed_out_exit(host)
        host.api.list_positions.side_effect = RuntimeError("broker down")

        host._check_pending_timeout()
        self.assertTrue(host._settling)
        self.assertTrue(host.is_pending)
        self.assertFalse(host.block_new_entry)

        host._settle_since = host._clock() - host._cfg.settle_timeout_sec - 1
        host._settle_via_reconcile()

        self.assertTrue(host._position_unconfirmed)
        self.assertTrue(host.block_new_entry)
        self.assertFalse(host.is_pending)

    def test_debounce_requires_consecutive_consistent_reads(self) -> None:
        host = make_host()
        host._cfg.reconcile_confirm_reads = 2
        # First read of (1, Long): streak 1 -> not yet confirmed.
        self.assertFalse(host._record_reconcile_read((1, "Long")))
        # Second identical read: confirmed.
        self.assertTrue(host._record_reconcile_read((1, "Long")))
        # A different read resets the streak.
        self.assertFalse(host._record_reconcile_read((2, "Short")))


class TestCeilingBackstopAndConverge(unittest.TestCase):
    def _arm_reconcile(self, host, *, kernel_qty, kernel_dir, broker_positions):
        host._alerts = MagicMock()
        host._api_connected = True
        host.contract = MagicMock(code="TXFR1")
        host._last_tick_exchange_dt = datetime.datetime(2026, 6, 24, 10, 0, 0)
        host.position_qty = kernel_qty
        host.position_dir = kernel_dir
        host.api.futopt_account = MagicMock()
        host.api.list_positions.return_value = broker_positions
        host._last_reconcile_wall = 0.0
        host._clock = lambda: 10_000.0

    def test_reconcile_ceiling_breach_halts_then_converges_single_exit(self) -> None:
        host = make_host()
        self._arm_reconcile(
            host, kernel_qty=0, kernel_dir="Flat", broker_positions=[_pos(2, "Buy")]
        )
        host._order_sync_mode = True
        placed: list[OrderSignal] = []
        host.place_order = lambda sig: placed.append(sig)

        host._check_position_reconcile()

        # Broker holds 2 (> kernel 0 and > ceiling 1) -> HALT + adopt truth.
        self.assertTrue(host._position_unconfirmed)
        self.assertTrue(host.block_new_entry)
        self.assertEqual(host.position_qty, 2)
        self.assertEqual(host.position_dir, "Long")

        # Convergence sends exactly ONE flatten sized to the held qty.
        host._maybe_converge_flatten()
        self.assertEqual(len(placed), 1)
        self.assertEqual(placed[0].intent, "exit")
        self.assertEqual(placed[0].action, "Sell")
        self.assertEqual(placed[0].qty, 2)
        self.assertTrue(host.is_pending)
        # Convergence returns to SETTLING so the settle loop polls for its outcome.
        self.assertTrue(host._settling)

        # While that convergence order is in flight, no second flatten is sent.
        host._maybe_converge_flatten()
        self.assertEqual(len(placed), 1)

    def test_converge_lifts_halt_when_confirmed_flat(self) -> None:
        host = make_host()
        host._position_unconfirmed = True
        host.block_new_entry = True
        host.position_qty = 0
        host.position_dir = "Flat"

        host._maybe_converge_flatten()

        self.assertFalse(host._position_unconfirmed)
        # Entries stay blocked until daily reset / manual clear.
        self.assertTrue(host.block_new_entry)


if __name__ == "__main__":
    unittest.main()
