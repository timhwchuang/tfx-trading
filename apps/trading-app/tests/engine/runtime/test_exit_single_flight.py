"""Regression: exit L3 infer-clear must not allow double-send (live 2026-06-29 RCA)."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from trading_engine.core.types import OrderSignal
from trading_engine.testing.helpers import arm_pending_exit, make_host


def _pos(qty: int, direction: str) -> SimpleNamespace:
    return SimpleNamespace(code="TXFR1", quantity=qty, direction=direction, price=45467.0)


class TestExitSingleFlight(unittest.TestCase):
    def _arm(self, host):
        host.contract = MagicMock(code="TXFR1")
        host.api.futopt_account = MagicMock()

    def test_unchanged_broker_keeps_pending_within_miss_window(self) -> None:
        host = make_host()
        self._arm(host)
        host._cfg.reconcile_confirm_reads = 1
        host.position_qty = 1
        host.position_dir = "Short"
        arm_pending_exit(host, order_id="100609", exit_reason="stop_loss", qty=1)
        host._settling = True
        host._settle_since = host._clock()
        host.api.list_positions.return_value = [_pos(1, "Sell")]
        placed: list[OrderSignal] = []
        host.place_order = lambda sig: placed.append(sig)

        for _ in range(5):
            host._settle_via_reconcile()

        self.assertTrue(host.is_pending)
        self.assertEqual(host.pending_order_id, "100609")
        self.assertEqual(len(placed), 0)

    def test_after_miss_window_stop_loss_escalates_not_strategy_retry(self) -> None:
        host = make_host()
        self._arm(host)
        host._cfg.reconcile_confirm_reads = 1
        host.position_qty = 1
        host.position_dir = "Short"
        arm_pending_exit(host, order_id="100609", exit_reason="stop_loss", qty=1)
        host._settling = True
        host._settle_since = host._clock() - host._cfg.exit_miss_confirm_sec - 1
        host.api.list_positions.return_value = [_pos(1, "Sell")]
        placed: list[OrderSignal] = []
        host.place_order = lambda sig: placed.append(sig)

        host._settle_via_reconcile()

        self.assertFalse(host.is_pending)
        self.assertTrue(host._stop_market_flatten_request)
        self.assertEqual(len(placed), 0)


if __name__ == "__main__":
    unittest.main()
