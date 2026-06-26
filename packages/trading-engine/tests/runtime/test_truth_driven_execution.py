"""P0-5 (truth-driven execution): timeout = UNKNOWN, freeze on uncertainty,
broker position is the single source of truth, kernel converges via a single
flatten. Regression for the ">1 lot from cascading re-issued orders" incident.
"""

from __future__ import annotations

import datetime
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from trading_engine.core.types import OrderSignal
from trading_engine.testing.helpers import (
    arm_pending_entry,
    arm_pending_exit,
    make_host,
)


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
        # Single-flight: an EXIT/flatten may still be working at the broker, so
        # HALT must NOT drop its order_id (would let convergence double-send).
        self.assertTrue(host.is_pending)

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
        host._cfg.reconcile_confirm_reads = 1  # single debounced read confirms
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
        host._alerts = MagicMock()
        host._api_connected = True
        host.contract = MagicMock(code="TXFR1")
        host.api.futopt_account = MagicMock()
        host.api.list_positions.return_value = []  # broker confirmed flat
        host._cfg.reconcile_confirm_reads = 1
        host._position_unconfirmed = True
        host.block_new_entry = True
        host.position_qty = 0
        host.position_dir = "Flat"

        host._maybe_converge_flatten()

        self.assertFalse(host._position_unconfirmed)
        # Entries stay blocked until daily reset / manual clear.
        self.assertTrue(host.block_new_entry)

    def test_converge_single_flight_no_second_order_on_redetect(self) -> None:
        """While a convergence flatten is in flight, a re-detected extra position
        (ceiling breach) must NOT send a second order (single-flight)."""
        host = make_host()
        self._arm_reconcile(
            host, kernel_qty=0, kernel_dir="Flat", broker_positions=[_pos(2, "Buy")]
        )
        host._cfg.reconcile_confirm_reads = 1
        host._order_sync_mode = True
        placed: list[OrderSignal] = []
        host.place_order = lambda sig: placed.append(sig)

        host._check_position_reconcile()  # HALT + adopt Long 2
        host._maybe_converge_flatten()  # exactly ONE flatten, now pending
        self.assertEqual(len(placed), 1)
        self.assertTrue(host.is_pending)

        # Re-running reconcile / convergence while the flatten is live must not
        # issue another order — the live order keeps its order_id (single-flight).
        host._check_position_reconcile()
        host._maybe_converge_flatten()
        self.assertEqual(len(placed), 1)
        self.assertTrue(host.is_pending)


class TestEntryNeverClearsOnFlat(unittest.TestCase):
    def test_entry_flat_snapshot_keeps_settling_never_clears(self) -> None:
        """D1: an acknowledged entry is NEVER resolved as a clean no-fill from a
        flat broker snapshot (a stale flat read is not proof of non-fill)."""
        host = make_host()
        arm_pending_entry(host, order_id="E1", signal_price=18000.0)
        host.position_qty = 0
        host.position_dir = "Flat"

        resolved = host._apply_pending_broker_truth(0, "Flat")

        self.assertFalse(resolved)  # keep settling
        self.assertTrue(host.is_pending)  # order_id retained, never re-armed
        self.assertFalse(host._position_unconfirmed)


class TestIncidentReplayNeverExceedsOneLot(unittest.TestCase):
    """Replay the 10:39 live incident: an entry fills late while
    list_positions reads flat. Assert the net position never exceeds 1,
    missed entry resumes without day-HALT, late fill triggers orphan HALT +
    convergence flatten, and the book ends flat."""

    def test_late_entry_fill_after_miss_orphan_converges_single_flatten(self) -> None:
        host = make_host()
        host._alerts = MagicMock()
        host._api_connected = True
        host.contract = MagicMock(code="TXFR1")
        host.api.futopt_account = MagicMock()
        host._order_sync_mode = True
        host._cfg.reconcile_confirm_reads = 1
        placed: list[OrderSignal] = []
        host.place_order = lambda sig: placed.append(sig)

        clock = {"t": 0.0}
        host._clock = lambda: clock["t"]

        broker_state: dict[str, list] = {"pos": []}
        host.api.list_positions.side_effect = lambda account=None: broker_state["pos"]

        def net() -> int:
            return abs(host.position_qty)

        arm_pending_entry(host, order_id="E1", signal_price=18000.0)
        host.pending_since = 0.0
        host.position_qty = 0
        host.position_dir = "Flat"

        clock["t"] = host._cfg.pending_timeout_sec + 1
        host._check_pending_timeout()
        self.assertTrue(host._settling)
        self.assertTrue(host.is_pending)
        self.assertLessEqual(net(), 1)

        for _ in range(2):
            host._settle_via_reconcile()
            self.assertTrue(host.is_pending)
            self.assertLessEqual(net(), 1)

        # Stable flat past confirm window → MISSED (resume, no sticky day-HALT).
        clock["t"] = host._settle_since + host._cfg.entry_miss_confirm_sec + 1
        host._settle_via_reconcile()
        self.assertFalse(host.is_pending)
        self.assertFalse(host._position_unconfirmed)
        self.assertFalse(host.block_new_entry)
        self.assertLessEqual(net(), 1)

        # Late fill arrives as orphan → HALT (backstop), then single convergence.
        host.handle_order_event(
            "FuturesDeal",
            {"price": 18000.0, "quantity": 1, "action": "Buy", "trade_id": "E1"},
        )
        self.assertTrue(host._position_unconfirmed)
        self.assertTrue(host.block_new_entry)

        broker_state["pos"] = [_pos(1, "Buy")]
        clock["t"] += host._cfg.reconcile_fast_sec + 1
        host._maybe_converge_flatten()
        self.assertEqual(len(placed), 1)
        self.assertEqual(placed[0].action, "Sell")
        self.assertEqual(placed[0].qty, 1)
        self.assertTrue(host.is_pending)
        self.assertLessEqual(net(), 1)

        host._maybe_converge_flatten()
        self.assertEqual(len(placed), 1)

        broker_state["pos"] = []
        clock["t"] += host._cfg.reconcile_fast_sec + 1
        host._settle_via_reconcile()
        host._maybe_converge_flatten()
        self.assertFalse(host.is_pending)
        self.assertEqual(host.position_qty, 0)
        self.assertFalse(host._position_unconfirmed)
        self.assertTrue(host.block_new_entry)


class TestEntryMissResume(unittest.TestCase):
    """Two-tier model: transient SETTLING entry miss → clean resume; HALT only
    for anomalies (unreadable broker, circuit breaker, orphan late fill)."""

    def test_entry_stable_flat_miss_resumes_no_day_halt(self) -> None:
        host = make_host()
        host._alerts = MagicMock()
        host.contract = MagicMock(code="TXFR1")
        host.api.futopt_account = MagicMock()
        host.api.list_positions.return_value = []
        host._cfg.reconcile_confirm_reads = 1
        arm_pending_entry(host, order_id="E1")
        host._settling = True
        host._settle_since = host._clock() - host._cfg.entry_miss_confirm_sec - 1

        host._settle_via_reconcile()

        self.assertFalse(host.is_pending)
        self.assertFalse(host._settling)
        self.assertFalse(host._position_unconfirmed)
        self.assertFalse(host.block_new_entry)
        self.assertEqual(host._consecutive_missed_entries, 1)

    def test_late_entry_fill_adopted_resets_miss_counter(self) -> None:
        host = make_host()
        host.contract = MagicMock(code="TXFR1")
        host.api.futopt_account = MagicMock()
        host.api.list_positions.return_value = [_pos(1, "Buy")]
        host._cfg.reconcile_confirm_reads = 1
        arm_pending_entry(host, order_id="E1")
        host._settling = True
        host._settle_since = 0.0
        host._consecutive_missed_entries = 2
        host.position_qty = 0
        host.position_dir = "Flat"

        host._settle_via_reconcile()

        self.assertFalse(host.is_pending)
        self.assertEqual(host.position_qty, 1)
        self.assertEqual(host._consecutive_missed_entries, 0)
        self.assertFalse(host._position_unconfirmed)

    def test_circuit_breaker_halts_after_consecutive_misses(self) -> None:
        host = make_host()
        host._alerts = MagicMock()
        host.contract = MagicMock(code="TXFR1")
        host.api.futopt_account = MagicMock()
        host.api.list_positions.return_value = []
        host._cfg.reconcile_confirm_reads = 1
        host._cfg.max_consecutive_missed_entries = 2
        host._consecutive_missed_entries = 1
        arm_pending_entry(host, order_id="E2")
        host._settling = True
        host._settle_since = host._clock() - host._cfg.entry_miss_confirm_sec - 1

        host._settle_via_reconcile()

        self.assertTrue(host._position_unconfirmed)
        self.assertTrue(host.block_new_entry)
        self.assertEqual(host._consecutive_missed_entries, 2)

    def test_callback_latency_logged(self) -> None:
        host = make_host()
        arm_pending_entry(host, order_id="E1")
        logged: list[str] = []

        def _capture(msg, *args, **kwargs):
            logged.append(msg % args if args else str(msg))

        with patch("trading_engine.order_executor.logger.info", side_effect=_capture):
            host.handle_order_event(
                "FuturesDeal",
                {
                    "price": 18000.0,
                    "quantity": 1,
                    "action": "Buy",
                    "trade_id": "E1",
                    "status": {"exchange_ts": host._clock() - 0.5},
                },
            )

        self.assertTrue(
            any("CALLBACK_LATENCY deal" in line for line in logged),
            f"expected CALLBACK_LATENCY log, got: {logged}",
        )


class TestEmergencyMarketEscalation(unittest.TestCase):
    """P0-5: emergency market orders. A missed STOP-LOSS IOC escalates to a
    kernel-owned market flatten, and HALT convergence flattens via market —
    bounding time-to-flat in fast/illiquid markets regardless of the unknown
    window. Normal (profit/entry) paths keep limit-IOC behavior."""

    def _market_host(self):
        host = make_host()
        host._alerts = MagicMock()
        host._api_connected = True
        host.contract = MagicMock(code="TXFR1")
        host.api.futopt_account = MagicMock()
        host._order_sync_mode = True
        return host

    def test_stop_loss_ioc_miss_escalates_to_market(self) -> None:
        host = self._market_host()
        host.position_qty = 1
        host.position_dir = "Long"
        host.entry_price = 18000.0
        arm_pending_exit(host, order_id="X", exit_reason="stop_loss")
        placed: list[OrderSignal] = []
        host.place_order = lambda sig: placed.append(sig)

        # Stop-loss IOC comes back Cancelled with no fill.
        host.handle_order_event(
            "FuturesOrder",
            {
                "operation": {"op_code": "00", "op_type": "Cancel"},
                "status": {"status": "Cancelled", "deal_quantity": 0, "id": "X"},
            },
        )
        self.assertFalse(host.is_pending)  # cancelled → cleared
        self.assertTrue(host._stop_market_flatten_request)

        # Kernel escalates to a single guaranteed-fill market flatten.
        host._maybe_emergency_market_flatten()
        self.assertEqual(len(placed), 1)
        self.assertTrue(placed[0].market)
        self.assertEqual(placed[0].action, "Sell")
        self.assertEqual(placed[0].qty, 1)
        self.assertEqual(placed[0].intent, "exit")
        self.assertTrue(host.is_pending)
        self.assertFalse(host._stop_market_flatten_request)

        # Single-flight: no second market order while the first is in flight.
        host._maybe_emergency_market_flatten()
        self.assertEqual(len(placed), 1)

    def test_profit_exit_ioc_miss_does_not_escalate(self) -> None:
        host = self._market_host()
        host.position_qty = 1
        host.position_dir = "Long"
        arm_pending_exit(host, order_id="X", exit_reason="take_profit")
        placed: list[OrderSignal] = []
        host.place_order = lambda sig: placed.append(sig)

        host.handle_order_event(
            "FuturesOrder",
            {
                "operation": {"op_code": "00", "op_type": "Cancel"},
                "status": {"status": "Cancelled", "deal_quantity": 0, "id": "X"},
            },
        )
        self.assertFalse(host._stop_market_flatten_request)
        host._maybe_emergency_market_flatten()
        self.assertEqual(len(placed), 0)  # profit exits keep limit-IOC retry

    def test_stop_escalation_disabled_when_config_off(self) -> None:
        host = self._market_host()
        host._cfg.emergency_market_orders = False
        host.position_qty = 1
        host.position_dir = "Long"
        arm_pending_exit(host, order_id="X", exit_reason="stop_loss")
        placed: list[OrderSignal] = []
        host.place_order = lambda sig: placed.append(sig)

        host.handle_order_event(
            "FuturesOrder",
            {
                "operation": {"op_code": "00", "op_type": "Cancel"},
                "status": {"status": "Cancelled", "deal_quantity": 0, "id": "X"},
            },
        )
        self.assertFalse(host._stop_market_flatten_request)
        host._maybe_emergency_market_flatten()
        self.assertEqual(len(placed), 0)

    def test_convergence_flatten_uses_market(self) -> None:
        host = self._market_host()
        host.api.list_positions.return_value = [_pos(1, "Buy")]
        host._cfg.reconcile_confirm_reads = 1
        host._position_unconfirmed = True
        host.block_new_entry = True
        host.position_qty = 1
        host.position_dir = "Long"
        placed: list[OrderSignal] = []
        host.place_order = lambda sig: placed.append(sig)

        host._maybe_converge_flatten()
        self.assertEqual(len(placed), 1)
        self.assertTrue(placed[0].market)
        self.assertEqual(placed[0].action, "Sell")
        self.assertEqual(placed[0].qty, 1)

    def test_convergence_uses_limit_when_market_disabled(self) -> None:
        host = self._market_host()
        host._cfg.emergency_market_orders = False
        host.api.list_positions.return_value = [_pos(1, "Buy")]
        host._cfg.reconcile_confirm_reads = 1
        host._position_unconfirmed = True
        host.block_new_entry = True
        host.position_qty = 1
        host.position_dir = "Long"
        placed: list[OrderSignal] = []
        host.place_order = lambda sig: placed.append(sig)

        host._maybe_converge_flatten()
        self.assertEqual(len(placed), 1)
        self.assertFalse(placed[0].market)


class TestHaltNoConsistentClear(unittest.TestCase):
    """Residual-hole hardening: under HALT, a live flatten is NEVER cleared by an
    'unchanged & consistent' broker read (which, under multi-minute report
    latency, is just the not-yet-reflected pre-flatten position). Clearing it
    would let convergence fire a SECOND flatten and over-flatten. Resolution
    happens only on a real reduction or an explicit Cancelled callback."""

    def test_consistent_read_during_halt_keeps_flatten_pending(self) -> None:
        host = make_host()
        host.position_qty = 1
        host.position_dir = "Long"
        arm_pending_exit(host, order_id="F1", exit_reason="stop_loss", qty=1)
        host._position_unconfirmed = True
        host._settling = True

        # Broker still reports the pre-flatten position (report latency) — looks
        # 'consistent' with the kernel but the flatten is genuinely in flight.
        resolved = host._apply_pending_broker_truth(1, "Long")

        self.assertFalse(resolved)  # keep settling, do NOT infer-clear
        self.assertTrue(host.is_pending)  # live flatten retained (single-flight)
        self.assertEqual(host.pending_order_id, "F1")

    def test_consistent_read_clears_when_not_halted(self) -> None:
        # Same read OUTSIDE halt → legacy behavior: clear and resume.
        host = make_host()
        host.position_qty = 1
        host.position_dir = "Long"
        arm_pending_exit(host, order_id="F1", exit_reason="take_profit", qty=1)

        resolved = host._apply_pending_broker_truth(1, "Long")

        self.assertTrue(resolved)
        self.assertFalse(host.is_pending)

    def test_halt_set_during_l3_infer_clear_keeps_pending(self) -> None:
        """TOCTOU: HALT raised after broker consistency check but before
        infer-clear must not drop a live flatten (30-lot residual-hole guard)."""
        host = make_host()
        host.position_qty = 1
        host.position_dir = "Long"
        arm_pending_exit(host, order_id="F1", exit_reason="stop_loss", qty=1)
        host._position_unconfirmed = False
        host._settling = True

        real_lock = host.lock
        acquire_count = {"n": 0}

        class CountingLock:
            def __enter__(self):
                acquire_count["n"] += 1
                if acquire_count["n"] == 2:
                    host._halt_position_unconfirmed(
                        "race: HALT between broker check and infer-clear",
                        clear_pending=False,
                    )
                return real_lock.__enter__()

            def __exit__(self, *exc):
                return real_lock.__exit__(*exc)

        host.lock = CountingLock()
        resolved = host._apply_pending_broker_truth(1, "Long")

        self.assertFalse(resolved)
        self.assertTrue(host.is_pending)
        self.assertEqual(host.pending_order_id, "F1")
        self.assertTrue(host._position_unconfirmed)


if __name__ == "__main__":
    unittest.main()
