"""P0-3: periodic broker/kernel position reconcile + drift circuit-breaker."""

from __future__ import annotations

import datetime
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock

from trading_engine.testing.helpers import make_host


def _pos(qty: int, direction: str, price: float = 18000.0) -> SimpleNamespace:
    return SimpleNamespace(code="TXFR1", quantity=qty, direction=direction, price=price)


def _arm_reconcile(host, *, kernel_qty, kernel_dir, broker_positions):
    host._alerts = MagicMock()
    host._api_connected = True
    host.contract = MagicMock(code="TXFR1")
    # Inside the trading session (08:45-13:45).
    host._last_tick_exchange_dt = datetime.datetime(2026, 6, 24, 10, 0, 0)
    host.position_qty = kernel_qty
    host.position_dir = kernel_dir
    host.api.list_positions.return_value = broker_positions
    host._last_reconcile_wall = 0.0
    host._clock = lambda: 10_000.0  # well past position_reconcile_sec


class TestPositionReconcile(unittest.TestCase):
    def test_drift_blocks_and_adopts_broker_truth(self):
        host = make_host()
        _arm_reconcile(
            host,
            kernel_qty=1,
            kernel_dir="Long",
            broker_positions=[
                SimpleNamespace(code="TXFR1", quantity=24, direction="Sell", price=46592.6)
            ],
        )

        host._check_position_reconcile()

        self.assertTrue(host.block_new_entry)
        self.assertTrue(host._position_drift_detected)
        # P0-5: broker holds 24 (> kernel 1 and > ceiling) → HALT, not just drift.
        self.assertTrue(host._position_unconfirmed)
        self.assertEqual(host.position_qty, 24)
        self.assertEqual(host.position_dir, "Short")
        host._alerts.send.assert_called()
        self.assertEqual(host._alerts.send.call_args.kwargs.get("level"), "CRITICAL")

    def test_in_sync_does_not_block(self):
        host = make_host()
        _arm_reconcile(
            host,
            kernel_qty=1,
            kernel_dir="Long",
            broker_positions=[
                SimpleNamespace(code="TXFR1", quantity=1, direction="Buy", price=18000.0)
            ],
        )

        host._check_position_reconcile()

        self.assertFalse(host.block_new_entry)
        self.assertFalse(host._position_drift_detected)
        host._alerts.send.assert_not_called()

    def test_severe_drift_flat_vs_long_halts(self):
        host = make_host()
        _arm_reconcile(
            host,
            kernel_qty=0,
            kernel_dir="Flat",
            broker_positions=[_pos(1, "Buy", price=45490.0)],
        )
        host._cfg.reconcile_confirm_reads = 1
        host._order_sync_mode = True
        placed = []
        host.place_order = lambda sig: placed.append(sig)

        host._check_position_reconcile()

        self.assertTrue(host._position_unconfirmed)
        self.assertTrue(host.block_new_entry)
        self.assertEqual(host.position_qty, 1)
        self.assertEqual(host.position_dir, "Long")
        host._maybe_converge_flatten()
        self.assertEqual(len(placed), 1)
        self.assertTrue(placed[0].market)

    def test_severe_drift_requires_debounce_reads(self) -> None:
        host = make_host()
        _arm_reconcile(
            host,
            kernel_qty=0,
            kernel_dir="Flat",
            broker_positions=[_pos(1, "Buy", price=45490.0)],
        )
        host._cfg.reconcile_confirm_reads = 3
        host._post_exit_reconcile_until = host._clock() + 15
        t = [host._clock()]

        def _tick_clock() -> float:
            return t[0]

        host._clock = _tick_clock

        host._check_position_reconcile()
        self.assertFalse(host._position_unconfirmed)
        t[0] += 2
        host._check_position_reconcile()
        self.assertFalse(host._position_unconfirmed)
        t[0] += 2
        host._check_position_reconcile()
        self.assertTrue(host._position_unconfirmed)

    def test_post_exit_transient_broker_lag_no_spurious_halt(self) -> None:
        host = make_host()
        _arm_reconcile(
            host,
            kernel_qty=0,
            kernel_dir="Flat",
            broker_positions=[_pos(1, "Buy", price=45490.0)],
        )
        host._cfg.reconcile_confirm_reads = 3
        host._post_exit_reconcile_until = host._clock() + 15
        t = [host._clock()]
        host._clock = lambda: t[0]
        reads = {"n": 0}

        def _list_positions(**_kwargs):
            reads["n"] += 1
            if reads["n"] == 1:
                return [_pos(1, "Buy", price=45490.0)]
            return []

        host.api.list_positions.side_effect = _list_positions

        host._check_position_reconcile()
        t[0] += 2
        host._check_position_reconcile()

        self.assertFalse(host._position_unconfirmed)
        self.assertFalse(host.block_new_entry)

    def test_throttled_within_interval(self):
        host = make_host()
        _arm_reconcile(
            host,
            kernel_qty=1,
            kernel_dir="Long",
            broker_positions=[
                SimpleNamespace(code="TXFR1", quantity=24, direction="Sell", price=46592.6)
            ],
        )
        # Last reconcile just happened; not enough time elapsed.
        host._last_reconcile_wall = host._clock()

        host._check_position_reconcile()

        self.assertFalse(host.block_new_entry)
        host._alerts.send.assert_not_called()

    def test_skips_while_pending(self):
        host = make_host()
        _arm_reconcile(
            host,
            kernel_qty=1,
            kernel_dir="Long",
            broker_positions=[
                SimpleNamespace(code="TXFR1", quantity=24, direction="Sell", price=46592.6)
            ],
        )
        host.is_pending = True

        host._check_position_reconcile()

        self.assertFalse(host.block_new_entry)

    def test_pending_skip_does_not_consume_reconcile_throttle(self):
        host = make_host()
        _arm_reconcile(
            host,
            kernel_qty=1,
            kernel_dir="Long",
            broker_positions=[
                SimpleNamespace(code="TXFR1", quantity=24, direction="Sell", price=46592.6)
            ],
        )
        host.is_pending = True
        host._check_position_reconcile()
        self.assertFalse(host.block_new_entry)

        host.is_pending = False
        host._check_position_reconcile()
        self.assertTrue(host.block_new_entry)

    def test_failed_broker_read_does_not_consume_reconcile_throttle(self):
        host = make_host()
        _arm_reconcile(
            host,
            kernel_qty=1,
            kernel_dir="Long",
            broker_positions=[],
        )
        host.api.list_positions.side_effect = RuntimeError("broker down")
        host._check_position_reconcile()
        self.assertFalse(host.block_new_entry)
        self.assertEqual(host._last_reconcile_wall, 0.0)

        host.api.list_positions.side_effect = None
        host.api.list_positions.return_value = [
            SimpleNamespace(code="TXFR1", quantity=24, direction="Sell", price=46592.6)
        ]
        host._check_position_reconcile()
        self.assertTrue(host.block_new_entry)

    def test_disabled_when_interval_zero(self):
        host = make_host()
        host._cfg._base = replace(host._cfg._base, position_reconcile_sec=0)
        _arm_reconcile(
            host,
            kernel_qty=1,
            kernel_dir="Long",
            broker_positions=[
                SimpleNamespace(code="TXFR1", quantity=24, direction="Sell", price=46592.6)
            ],
        )

        host._check_position_reconcile()

        self.assertFalse(host.block_new_entry)


if __name__ == "__main__":
    unittest.main()
