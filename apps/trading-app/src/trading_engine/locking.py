"""Phase G0: dual-lock contract for TradingEngine.

Lock hierarchy (strict)
-----------------------
1. **Domain lock** (``self.lock`` / :class:`DomainLock`)
   Owns Book, Link, Integrity, Tick, and staged domain mutations.
   Held on the ``on_tick`` hot path — **no broker I/O** while held.

2. **API lock** (``self._api_lock`` RLock)
   Serializes Shioaji mutable ops only (place / list / login / Contracts …).
   Avoids PyO3 ``PyBorrowMutError`` on live Trade objects.

**Never** acquire the API lock while the **current thread** holds the domain
lock. That ordering causes lock inversion with ``on_tick`` and background
maintenance (timeout / reconcile / session WD).

Allowed patterns
----------------
* API outside domain lock → ``with self.lock:`` mutate domain.
* Brief domain lock (snapshot) → release → API → re-acquire domain and
  re-validate ownership (e.g. ``_still_own_pending``).

Entry points
------------
* Prefer :meth:`TradingEngine._call_api` for all broker mutable calls.
* Direct ``with self._api_lock`` must call :func:`assert_api_entry_allowed`
  first (or use :func:`api_critical_section`).
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from types import TracebackType
from typing import TypeVar

T = TypeVar("T")


class LockOrderError(RuntimeError):
    """Domain lock held by current thread while entering API critical section."""


class DomainLock:
    """``threading.Lock`` wrapper with per-thread hold depth for G0 checks.

    Supports the same ``with lock:`` / ``acquire`` / ``release`` surface as
    ``threading.Lock`` so existing call sites stay unchanged.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._local = threading.local()

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        if timeout is None or timeout < 0:
            ok = self._lock.acquire(blocking)
        else:
            ok = self._lock.acquire(blocking, timeout)
        if ok:
            self._local.depth = getattr(self._local, "depth", 0) + 1
        return ok

    def release(self) -> None:
        depth = getattr(self._local, "depth", 0)
        if depth <= 0:
            raise RuntimeError("DomainLock.release() without matching acquire")
        self._local.depth = depth - 1
        self._lock.release()

    def __enter__(self) -> DomainLock:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()

    def held_by_current_thread(self) -> bool:
        return getattr(self._local, "depth", 0) > 0

    def locked(self) -> bool:
        """True if any thread holds the lock (compat with ``threading.Lock``)."""
        return self._lock.locked()


def assert_api_entry_allowed(domain_lock: DomainLock) -> None:
    """Raise :class:`LockOrderError` if current thread holds the domain lock."""
    if domain_lock.held_by_current_thread():
        raise LockOrderError(
            "must not acquire _api_lock while holding domain lock (self.lock); "
            "release domain lock before broker I/O (Phase G0)"
        )


@contextmanager
def api_critical_section(
    domain_lock: DomainLock,
    api_lock: threading.RLock,
) -> Iterator[None]:
    """Enter API lock only after G0 domain-lock check passes."""
    assert_api_entry_allowed(domain_lock)
    with api_lock:
        yield


__all__ = [
    "DomainLock",
    "LockOrderError",
    "api_critical_section",
    "assert_api_entry_allowed",
]
