"""Layer 2: IOC terminal-state query via update_status(trade) on order worker."""

from __future__ import annotations

import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from trading_engine.core.types import OrderSignal, QueryStatusTask
from trading_engine.testing.helpers import (
    arm_pending_entry,
    arm_pending_exit,
    make_host,
)


def _pos(qty: int, direction: str, price: float = 100.0) -> SimpleNamespace:
    return SimpleNamespace(code="TXFR1", quantity=qty, direction=direction, price=price)


def _fake_trade(
    status: str,
    *,
    oid: str = "ord-1",
    deal_qty: int = 0,
    cancel_qty: int = 0,
) -> SimpleNamespace:
    return SimpleNamespace(
        order=SimpleNamespace(id=oid),
        status=SimpleNamespace(
            status=status,
            deal_quantity=deal_qty,
            cancel_quantity=cancel_qty,
        ),
    )


def _qtask(host, order_id: str) -> QueryStatusTask:
    """Build a QueryStatusTask with the host's current pending generation."""
    with host.lock:
        return QueryStatusTask(order_id=order_id, generation=host._pending_generation)


class TestReadTradeTerminalState(unittest.TestCase):
    def test_maps_all_verified_statuses(self) -> None:
        cases = {
            "Filled": "filled",
            "PartFilled": "partial",
            "Cancelled": "cancelled",
            "Failed": "failed",
            "Inactive": "inactive",
            "PendingSubmit": "working",
            "PreSubmitted": "working",
            "Submitted": "working",
        }
        host = make_host()
        for raw, expected in cases.items():
            state, deal, cancel = host._read_trade_terminal_state(
                _fake_trade(raw, deal_qty=1, cancel_qty=2)
            )
            self.assertEqual(state, expected, raw)
            self.assertEqual(deal, 1)
            self.assertEqual(cancel, 2)

    def test_unknown_on_missing_status(self) -> None:
        host = make_host()
        state, deal, cancel = host._read_trade_terminal_state(SimpleNamespace())
        self.assertEqual(state, "unknown")
        self.assertEqual(deal, 0)
        self.assertEqual(cancel, 0)


class TestFlagOffRegression(unittest.TestCase):
    def test_enqueue_query_status_noop_when_disabled(self) -> None:
        host = make_host()
        host._cfg.order_status_query_enabled = False
        arm_pending_entry(host)
        host.pending_trade = _fake_trade("Cancelled")
        host._enqueue_query_status()
        host.api.update_status.assert_not_called()

    def test_pending_timeout_uses_legacy_reconcile_when_disabled(self) -> None:
        host = make_host()
        host._cfg.order_status_query_enabled = False
        host._cfg.simulation = False
        arm_pending_entry(host)
        host.pending_since = host._clock() - 10
        host.pending_trade = _fake_trade("Submitted", oid="ord-entry-1")
        with patch.object(host, "_reconcile_pending_trade", return_value=False) as mock_trade:
            with patch.object(host, "_enqueue_query_status") as mock_enqueue:
                host._check_pending_timeout()
                mock_trade.assert_called_once()
                mock_enqueue.assert_not_called()
        self.assertTrue(host._settling)

    def test_layer2_runs_in_simulation_uat_when_enabled(self) -> None:
        """UAT uses the real Shioaji simulation API, so the flag (not the
        simulation flag) must control Layer 2 — otherwise UAT can never validate
        borrow safety before production."""
        host = make_host()
        host._cfg.order_status_query_enabled = True
        host._cfg.simulation = True
        arm_pending_entry(host)
        host.pending_since = host._clock() - 10
        host.pending_trade = _fake_trade("Submitted", oid="ord-entry-1")
        host.api.list_positions.return_value = []
        with patch.object(host, "_enqueue_query_status") as mock_enqueue:
            host._check_pending_timeout()
            mock_enqueue.assert_called()

    def test_layer2_timeout_still_calls_deal_records(self) -> None:
        """Flag ON: L3 snapshot → order_deal_records → L2 enqueue."""
        host = make_host()
        host._cfg.order_status_query_enabled = True
        host._cfg.simulation = False
        arm_pending_entry(host)
        host.pending_since = host._clock() - 10
        host.pending_trade = _fake_trade("Submitted", oid="ord-entry-1")
        with patch.object(
            host, "_reconcile_pending_via_broker_snapshot", return_value=False
        ) as mock_snap:
            with patch.object(
                host, "_reconcile_pending_trade", return_value=False
            ) as mock_deals:
                with patch.object(host, "_enqueue_query_status") as mock_l2:
                    host._check_pending_timeout()
                    mock_snap.assert_called_once()
                    mock_deals.assert_called_once()
                    mock_l2.assert_called()


class TestGracefulFallback(unittest.TestCase):
    def test_query_failure_falls_back_to_inference(self) -> None:
        """An update_status failure (e.g. a borrow panic in production) is caught,
        logged, and degrades to the existing inference path — pending is untouched
        and _status_query_inflight is released."""
        host = make_host()
        host._cfg.order_status_query_enabled = True
        host._cfg.simulation = False
        host._order_sync_mode = True
        host.contract = MagicMock(code="TXFR1")
        host.api.futopt_account = MagicMock()
        arm_pending_entry(host, order_id="ord-1")
        host.pending_trade = _fake_trade("Cancelled", oid="ord-1")
        host.api.update_status = MagicMock(side_effect=RuntimeError("borrow panic"))

        host._query_pending_status(_qtask(host, "ord-1"))

        self.assertTrue(host.is_pending)  # not resolved by the failed query
        self.assertFalse(host._status_query_inflight)  # released for the next attempt


class TestQueryResolve(unittest.TestCase):
    def _live_host(self):
        host = make_host()
        host._cfg.order_status_query_enabled = True
        host._cfg.simulation = False
        host._cfg.reconcile_confirm_reads = 1
        host._order_sync_mode = True
        host.contract = MagicMock(code="TXFR1")
        host.api.futopt_account = MagicMock()
        return host

    def test_cancelled_entry_flat_resumes_immediately(self) -> None:
        host = self._live_host()
        arm_pending_entry(host, order_id="ord-entry-1")
        host.pending_trade = _fake_trade("Cancelled", oid="ord-entry-1")
        host.api.list_positions.return_value = []

        host._query_pending_status(_qtask(host, "ord-entry-1"))

        self.assertFalse(host.is_pending)
        self.assertFalse(host._position_unconfirmed)
        self.assertFalse(host._settling)

    def test_filled_entry_adopts_broker_position(self) -> None:
        host = self._live_host()
        arm_pending_entry(host, order_id="ord-entry-1")
        host.pending_trade = _fake_trade("Filled", oid="ord-entry-1", deal_qty=1)
        host.api.list_positions.return_value = [_pos(1, "Buy")]

        host._query_pending_status(_qtask(host, "ord-entry-1"))

        self.assertEqual(host.position_qty, 1)
        self.assertEqual(host.position_dir, "Long")
        self.assertFalse(host.is_pending)

    def test_cancelled_with_deal_qty_adopts_via_broker(self) -> None:
        """Cancelled + deal_qty>0 must reconcile through Layer 3, not declare miss."""
        host = self._live_host()
        arm_pending_entry(host, order_id="ord-entry-1")
        host.pending_trade = _fake_trade(
            "Cancelled", oid="ord-entry-1", deal_qty=1, cancel_qty=0
        )
        host.api.list_positions.return_value = [_pos(1, "Buy")]

        host._query_pending_status(_qtask(host, "ord-entry-1"))

        self.assertEqual(host.position_qty, 1)
        self.assertEqual(host.position_dir, "Long")
        self.assertFalse(host.is_pending)

    def test_cancelled_entry_kernel_matches_broker_adopts_not_miss(self) -> None:
        """Cancelled status with kernel already holding the fill must adopt, not miss."""
        host = self._live_host()
        arm_pending_entry(host, order_id="ord-entry-1")
        host.position_qty = 1
        host.position_dir = "Long"
        host.pending_trade = _fake_trade("Cancelled", oid="ord-entry-1")
        host.api.list_positions.return_value = [_pos(1, "Buy")]

        host._query_pending_status(_qtask(host, "ord-entry-1"))

        self.assertFalse(host.is_pending)
        self.assertEqual(host.position_qty, 1)

    def test_cancelled_with_position_halts_and_clears_pending(self) -> None:
        """Entry anomaly: terminal at exchange + broker lot in the WRONG direction →
        HALT and clear pending so convergence flatten is not blocked."""
        host = self._live_host()
        arm_pending_entry(host, order_id="ord-entry-1")  # Buy → expect Long
        host.pending_trade = _fake_trade("Cancelled", oid="ord-entry-1")
        # Short position on a Buy entry = unexplained / wrong-direction lot
        host.api.list_positions.return_value = [_pos(1, "Sell")]

        host._query_pending_status(_qtask(host, "ord-entry-1"))

        self.assertTrue(host._position_unconfirmed)
        self.assertTrue(host.block_new_entry)
        self.assertFalse(host.is_pending)

    def test_entry_anomaly_allows_convergence_flatten(self) -> None:
        host = self._live_host()
        arm_pending_entry(host, order_id="ord-entry-1")
        host.pending_trade = _fake_trade("Cancelled", oid="ord-entry-1")
        host.api.list_positions.return_value = [_pos(1, "Sell")]
        host._query_pending_status(_qtask(host, "ord-entry-1"))

        self.assertFalse(host.is_pending)
        self.assertTrue(host._position_unconfirmed)
        with patch.object(host, "_enqueue_order") as mock_enqueue:
            host._maybe_converge_flatten()
            mock_enqueue.assert_called_once()

    def test_working_falls_back_without_clearing_pending(self) -> None:
        host = self._live_host()
        arm_pending_entry(host, order_id="ord-entry-1")
        host._settling = True
        host.pending_trade = _fake_trade("Submitted", oid="ord-entry-1")
        host.api.list_positions.return_value = []

        host._query_pending_status(_qtask(host, "ord-entry-1"))

        self.assertTrue(host.is_pending)
        self.assertTrue(host._settling)

    def test_stop_loss_cancelled_sets_market_escalation(self) -> None:
        host = self._live_host()
        host.position_qty = 1
        host.position_dir = "Long"
        arm_pending_exit(host, order_id="ord-exit-1", exit_reason="stop_loss")
        host.pending_trade = _fake_trade("Cancelled", oid="ord-exit-1")
        host.api.list_positions.return_value = [_pos(1, "Buy")]

        host._query_pending_status(_qtask(host, "ord-exit-1"))

        self.assertFalse(host.is_pending)
        self.assertTrue(host._stop_market_flatten_request)

    def test_stale_task_is_noop(self) -> None:
        host = self._live_host()
        arm_pending_entry(host, order_id="current")
        host.pending_trade = _fake_trade("Cancelled", oid="current")
        host.api.list_positions.return_value = []

        host._query_pending_status(QueryStatusTask("stale-id", generation=999))

        self.assertTrue(host.is_pending)
        host.api.update_status.assert_not_called()

    def test_empty_oid_task_rejected_when_generation_changed(self) -> None:
        """A task enqueued with an empty order_id (oid unknown) must NOT act on a
        later pending after the original was cleared + a new order armed."""
        host = self._live_host()
        # Original pending → enqueue captures generation with empty order_id.
        host._arm_pending(OrderSignal("Buy", 1, 100.0, "entry", exchange_ts=1))
        host.pending_order_id = ""
        host._enqueue_query_status()  # sync mode runs nothing yet (trade None) → builds task
        with host.lock:
            stale_gen = host._pending_generation
        # The original resolves and a brand-new order is armed (generation bumps).
        host._clear_pending()
        host._arm_pending(OrderSignal("Sell", 1, 200.0, "exit", exchange_ts=2))
        host.position_qty = 1
        host.position_dir = "Long"
        host.pending_trade = _fake_trade("Cancelled", oid="new")
        host.api.update_status.reset_mock()

        host._query_pending_status(QueryStatusTask("", generation=stale_gen))

        # The stale task must not touch the new pending.
        self.assertTrue(host.is_pending)
        self.assertEqual(host.pending_intent, "exit")
        host.api.update_status.assert_not_called()


class TestHaltNoLayer2Clear(unittest.TestCase):
    def _live_host(self):
        host = make_host()
        host._cfg.order_status_query_enabled = True
        host._cfg.simulation = False
        host._cfg.reconcile_confirm_reads = 1
        host._order_sync_mode = True
        host.contract = MagicMock(code="TXFR1")
        host.api.futopt_account = MagicMock()
        return host

    def test_halt_l2_exit_cancelled_clears_pending_for_retry(self) -> None:
        """Layer 2 authoritative terminal during HALT: clear pending (same as
        callback Cancelled) so convergence can re-arm a missed flatten."""
        host = self._live_host()
        host.position_qty = 1
        host.position_dir = "Long"
        arm_pending_exit(host, order_id="flat-1", exit_reason="take_profit")
        host._position_unconfirmed = True
        host.pending_trade = _fake_trade("Cancelled", oid="flat-1")
        host.api.list_positions.return_value = [_pos(1, "Buy")]

        host._query_pending_status(_qtask(host, "flat-1"))

        self.assertFalse(host.is_pending)
        self.assertTrue(host._position_unconfirmed)

    def test_halt_l2_exit_cancelled_allows_convergence_retry(self) -> None:
        host = self._live_host()
        host.position_qty = 1
        host.position_dir = "Long"
        arm_pending_exit(host, order_id="flat-1", exit_reason="take_profit")
        host._position_unconfirmed = True
        host.pending_trade = _fake_trade("Cancelled", oid="flat-1")
        host.api.list_positions.return_value = [_pos(1, "Buy")]
        host._query_pending_status(_qtask(host, "flat-1"))

        self.assertFalse(host.is_pending)
        with patch.object(host, "_enqueue_order") as mock_enqueue:
            host._maybe_converge_flatten()
            mock_enqueue.assert_called_once()

    def test_halt_l3_consistent_read_still_keeps_pending(self) -> None:
        """Signal taxonomy: L3 inference unchanged read during HALT must NOT
        clear — only authoritative terminal (L1/L2) may clear during HALT."""
        host = self._live_host()
        host.position_qty = 1
        host.position_dir = "Long"
        arm_pending_exit(host, order_id="flat-l3", exit_reason="stop_loss", qty=1)
        host._position_unconfirmed = True
        host._settling = True

        resolved = host._apply_pending_broker_truth(1, "Long")

        self.assertFalse(resolved)
        self.assertTrue(host.is_pending)
        self.assertEqual(host.pending_order_id, "flat-l3")

    def test_cancelled_exit_clears_when_not_halted(self) -> None:
        host = self._live_host()
        host.position_qty = 1
        host.position_dir = "Long"
        arm_pending_exit(host, order_id="flat-2", exit_reason="take_profit")
        host._position_unconfirmed = False
        host.pending_trade = _fake_trade("Cancelled", oid="flat-2")
        host.api.list_positions.return_value = [_pos(1, "Buy")]

        host._query_pending_status(_qtask(host, "flat-2"))

        self.assertFalse(host.is_pending)


class TestOidBackfill(unittest.TestCase):
    def test_place_refresh_backfills_empty_oid(self) -> None:
        host = make_host()
        host._cfg.order_status_query_enabled = True
        host._order_sync_mode = True
        host.contract = MagicMock()
        host.api.futopt_account = MagicMock()
        trade = _fake_trade("Submitted", oid="")
        trade.order.id = ""
        host.api.update_status = MagicMock(
            side_effect=lambda **kw: setattr(trade.order, "id", "backfilled-1") or None
        )

        signal = OrderSignal("Buy", 1, 100.0, "entry", exchange_ts=1)
        host._arm_pending(signal)
        host._refresh_trade_after_place(trade, signal)

        self.assertEqual(host.pending_order_id, "backfilled-1")

    def test_early_cancelled_at_place_resolves_entry(self) -> None:
        host = make_host()
        host._cfg.order_status_query_enabled = True
        host._cfg.reconcile_confirm_reads = 1
        host._order_sync_mode = True
        host.contract = MagicMock(code="TXFR1")
        host.api.futopt_account = MagicMock()
        host.api.list_positions.return_value = []
        trade = _fake_trade("Cancelled", oid="ord-early")
        signal = OrderSignal("Buy", 1, 100.0, "entry", exchange_ts=1)
        host._arm_pending(signal)
        host.pending_trade = trade

        host._refresh_trade_after_place(trade, signal)

        self.assertFalse(host.is_pending)


class TestWorkerDispatch(unittest.TestCase):
    def test_query_task_routes_to_query_not_place(self) -> None:
        host = make_host()
        host._cfg.order_status_query_enabled = True
        host._order_sync_mode = False
        arm_pending_entry(host)
        host.pending_trade = _fake_trade("Submitted")
        host.api.list_positions.return_value = []

        with patch.object(host, "_query_pending_status") as mock_query:
            with patch.object(host, "place_order") as mock_place:
                host._enqueue_query_status()
                time.sleep(0.05)
                mock_query.assert_called_once()
                mock_place.assert_not_called()

    def test_update_status_only_from_worker_thread(self) -> None:
        host = make_host()
        host._cfg.order_status_query_enabled = True
        host._order_sync_mode = False
        arm_pending_entry(host, order_id="ord-1")
        host.pending_trade = _fake_trade("Cancelled", oid="ord-1")
        host.api.list_positions.return_value = []
        caller_threads: list[str] = []

        def record_update(**kwargs):
            caller_threads.append(threading.current_thread().name)

        host.api.update_status = MagicMock(side_effect=record_update)

        host._enqueue_query_status()
        deadline = time.time() + 2.0
        while host.is_pending and time.time() < deadline:
            time.sleep(0.02)

        self.assertTrue(caller_threads)
        for name in caller_threads:
            self.assertEqual(name, "order-worker")


class TestBoundedTimeout(unittest.TestCase):
    def test_query_passes_configured_timeout(self) -> None:
        host = make_host()
        host._cfg.order_status_query_enabled = True
        host._cfg.order_status_query_timeout_ms = 750
        host._order_sync_mode = True
        arm_pending_entry(host)
        host.pending_trade = _fake_trade("Submitted")

        host._query_pending_status(_qtask(host, "ord-entry-1"))

        host.api.update_status.assert_called_once()
        _, kwargs = host.api.update_status.call_args
        self.assertEqual(kwargs.get("timeout"), 750)


if __name__ == "__main__":
    unittest.main()
