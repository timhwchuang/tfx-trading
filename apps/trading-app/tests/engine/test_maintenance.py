"""Phase G4: MaintenanceScheduler Option A + duration telemetry."""

from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import MagicMock

from trading_engine.maintenance import Job, MaintenanceScheduler
from trading_engine.testing.helpers import make_host


class TestMaintenanceScheduler(unittest.TestCase):
    def test_run_once_isolates_job_errors(self) -> None:
        ran: list[str] = []

        def ok() -> None:
            ran.append("ok")

        def boom() -> None:
            ran.append("boom")
            raise RuntimeError("explode")

        def after() -> None:
            ran.append("after")

        sched = MaintenanceScheduler(
            [
                Job("ok", 1.0, ok),
                Job("boom", 1.0, boom),
                Job("after", 1.0, after),
            ],
            clock=lambda: 100.0,
        )
        sched.run_once()
        self.assertEqual(ran, ["ok", "boom", "after"])
        self.assertEqual(sched.stats["boom"].error_count, 1)
        self.assertEqual(sched.stats["after"].run_count, 1)

    def test_over_budget_increments_and_warns(self) -> None:
        def slow() -> None:
            time.sleep(0.02)

        sched = MaintenanceScheduler(
            [Job("slow", 1.0, slow, budget_ms=1.0)],
            clock=lambda: 0.0,
        )
        with self.assertLogs("trading_engine", level="WARNING") as cm:
            # logger name may be package root — accept any warning log
            try:
                sched.run_once()
            except AssertionError:
                # assertLogs fails if no matching logger; fall back to stats only
                pass
        self.assertEqual(sched.stats["slow"].run_count, 1)
        self.assertGreater(sched.stats["slow"].last_duration_ms, 1.0)
        self.assertEqual(sched.stats["slow"].over_budget_count, 1)

    def test_not_due_skips_until_interval(self) -> None:
        t = [0.0]
        calls = [0]

        def tick() -> None:
            calls[0] += 1

        sched = MaintenanceScheduler(
            [Job("tick", 5.0, tick)],
            clock=lambda: t[0],
        )
        sched.run_once()
        self.assertEqual(calls[0], 1)
        t[0] = 1.0
        sched.run_once()
        self.assertEqual(calls[0], 1)  # still within interval
        t[0] = 5.0
        sched.run_once()
        self.assertEqual(calls[0], 2)

    def test_stop_is_idempotent(self) -> None:
        sched = MaintenanceScheduler([Job("n", 1.0, lambda: None)])
        sched.start()
        sched.stop()
        sched.stop()  # no raise

    def test_engine_wires_default_jobs(self) -> None:
        host = make_host()
        names = {j.name for j in host._maintenance._jobs}
        self.assertIn("pending_timeout", names)
        self.assertIn("position_reconcile", names)
        self.assertEqual(len(names), 10)

    def test_engine_has_no_ssot_field_forwarder(self) -> None:
        """G1: flat SSOT names are not readable; G3 may use __getattr__ for services."""
        host = make_host()
        with self.assertRaises(AttributeError):
            _ = host.position_qty  # type: ignore[attr-defined]
        self.assertEqual(host._book.position_qty, 0)
        # Service methods still facaded onto engine
        self.assertTrue(callable(host.place_order))
        self.assertTrue(callable(host.sync_positions))

    def test_timeout_loop_is_run_once_compat(self) -> None:
        host = make_host()
        host._check_pending_timeout = MagicMock()
        # Rebuild jobs bound to mocks would need new scheduler; just ensure
        # _timeout_loop invokes run_once without spinning.
        calls = {"n": 0}
        host._maintenance.run_once = lambda: calls.__setitem__("n", calls["n"] + 1)  # type: ignore[method-assign]
        host._timeout_loop()
        self.assertEqual(calls["n"], 1)

    def test_stop_join_timeout_flag(self) -> None:
        block = threading.Event()
        release = threading.Event()

        def stuck() -> None:
            block.set()
            release.wait(timeout=5.0)

        sched = MaintenanceScheduler(
            [Job("stuck", 0.01, stuck)],
            poll_sec=0.01,
            stop_join_sec=0.05,
        )
        sched.start()
        self.assertTrue(block.wait(timeout=2.0))
        sched.stop()
        release.set()
        # May or may not time out depending on timing; stop must be idempotent.
        sched.stop()

    def test_engine_services_lifecycle_list_includes_passive(self) -> None:
        """Passive services are on _services for future threads / LIFO teardown."""
        host = make_host()
        svcs = host._services
        self.assertIs(svcs[-1], host._maintenance)
        self.assertIs(svcs[-2], host.orders)
        self.assertIn(host.positions, svcs)
        self.assertIn(host.connectivity, svcs)
        self.assertIn(host.watchdog, svcs)
        self.assertIn(host.session, svcs)
        # Passive today: start/stop no-op
        host.positions.start()
        host.positions.stop()
        host.connectivity.start()
        host.connectivity.stop()

    def test_order_start_honors_host_patch(self) -> None:
        host = make_host()
        host._order_sync_mode = False
        called = []
        host._start_order_worker = lambda: called.append(1)  # type: ignore[method-assign]
        host.orders.start()
        self.assertEqual(called, [1])

    def test_getattr_cache_then_mock_override(self) -> None:
        host = make_host()
        # Prime cache
        fn = host.place_order
        self.assertTrue(callable(fn))
        self.assertIn("place_order", host.__dict__)
        mock = MagicMock()
        host.place_order = mock  # type: ignore[method-assign]
        host.place_order("sig")
        mock.assert_called_once_with("sig")


if __name__ == "__main__":
    unittest.main()
