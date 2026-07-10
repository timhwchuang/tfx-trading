"""Background maintenance scheduler (Phase G4 Option A).

Single thread, per-job ``next_due`` + soft time budget. Isolates slow broker
jobs from starving watchdogs without multi-thread lock contention on the
``on_tick`` hot path.

Duration telemetry: log WARNING when a job exceeds ``budget_ms`` (default 100).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from trading_engine.logging_setup import get_logger

logger = get_logger()

# Soft budget for ops early-warning (not a hard kill).
DEFAULT_JOB_BUDGET_MS = 100.0


@dataclass(frozen=True)
class Job:
    """One maintenance unit with its own cadence."""

    name: str
    interval_sec: float
    fn: Callable[[], None]
    budget_ms: float = DEFAULT_JOB_BUDGET_MS


@dataclass
class JobStats:
    last_duration_ms: float = 0.0
    over_budget_count: int = 0
    run_count: int = 0
    error_count: int = 0


class MaintenanceScheduler:
    """Option A: single background thread, independent job due times."""

    def __init__(
        self,
        jobs: list[Job],
        *,
        clock: Callable[[], float] | None = None,
        sleep_fn: Callable[[float], None] | None = None,
        poll_sec: float = 0.05,
    ) -> None:
        self._jobs = list(jobs)
        self._clock = clock if clock is not None else time.time
        self._sleep = sleep_fn if sleep_fn is not None else time.sleep
        self._poll_sec = max(0.01, float(poll_sec))
        self._next_due: dict[str, float] = {j.name: 0.0 for j in self._jobs}
        self._stats: dict[str, JobStats] = {j.name: JobStats() for j in self._jobs}
        self._running = False
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    @property
    def stats(self) -> dict[str, JobStats]:
        return self._stats

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._stop.clear()
        now = self._clock()
        for job in self._jobs:
            # First due immediately so cadence matches pre-G4 1s loop intent.
            self._next_due[job.name] = now
        self._thread = threading.Thread(
            target=self._loop,
            name="maintenance-scheduler",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Idempotent stop; joins the worker briefly."""
        if not self._running and self._thread is None:
            return
        self._running = False
        self._stop.set()
        t = self._thread
        self._thread = None
        if t is not None and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=2.0)

    def run_once(self) -> None:
        """Execute all due jobs once (tests / sync mode)."""
        now = self._clock()
        for job in self._jobs:
            if now + 1e-9 >= self._next_due.get(job.name, 0.0):
                self._run_job(job, now)

    def _loop(self) -> None:
        while self._running and not self._stop.is_set():
            try:
                self.run_once()
            except BaseException as e:
                # Scheduler itself must not die; per-job already isolates errors.
                logger.error("維運排程器嚴重異常: %s", e)
            self._sleep(self._poll_sec)

    def _run_job(self, job: Job, now: float) -> None:
        t0 = time.perf_counter()
        try:
            job.fn()
        except BaseException as e:
            st = self._stats[job.name]
            st.error_count += 1
            logger.error("維運 Job 異常 | job=%s err=%s", job.name, e)
        finally:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            st = self._stats[job.name]
            st.last_duration_ms = elapsed_ms
            st.run_count += 1
            # Schedule next due from wall clock after completion (skip/defer style).
            self._next_due[job.name] = self._clock() + max(0.0, job.interval_sec)
            if elapsed_ms > job.budget_ms:
                st.over_budget_count += 1
                logger.warning(
                    "維運 Job 逾時預算 | job=%s duration_ms=%.1f budget_ms=%.1f",
                    job.name,
                    elapsed_ms,
                    job.budget_ms,
                )


def default_engine_jobs(engine: Any) -> list[Job]:
    """Preserve pre-Wave-2 / G4 job inventory and ~1s cadence."""
    return [
        Job("pending_timeout", 1.0, engine._check_pending_timeout),
        Job("settle_reconcile", 1.0, engine._settle_via_reconcile),
        Job("converge_flatten", 1.0, engine._maybe_converge_flatten),
        Job("emergency_market_flatten", 1.0, engine._maybe_emergency_market_flatten),
        Job("exit_order_retry", 1.0, engine._check_exit_order_retry),
        Job("session_watchdog", 1.0, engine._check_session_watchdog),
        Job("no_tick_watchdog", 1.0, engine._check_no_tick_watchdog),
        Job("position_reconcile", 1.0, engine._check_position_reconcile),
        Job("late_cleared_deals", 1.0, engine._reconcile_recent_cleared_deals),
        Job("tick_type_summary", 1.0, engine._maybe_log_tick_type_summary),
    ]


__all__ = [
    "DEFAULT_JOB_BUDGET_MS",
    "Job",
    "JobStats",
    "MaintenanceScheduler",
    "default_engine_jobs",
]
