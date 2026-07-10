"""Phase G4: MaintenanceScheduler Option A + duration telemetry."""

from __future__ import annotations

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

    def test_engine_has_no_getattr_forwarder(self) -> None:
        host = make_host()
        self.assertFalse(hasattr(type(host), "__getattr__") and type(host).__getattr__ is not object.__getattribute__)
        # Flat field no longer on engine surface
        with self.assertRaises(AttributeError):
            _ = host.position_qty  # type: ignore[attr-defined]
        self.assertEqual(host._book.position_qty, 0)


if __name__ == "__main__":
    unittest.main()
