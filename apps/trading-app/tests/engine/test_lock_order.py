"""Phase G0: dual-lock contract (domain lock vs API lock)."""

from __future__ import annotations

import ast
import threading
import unittest
from pathlib import Path

from trading_engine.locking import (
    DomainLock,
    LockOrderError,
    api_critical_section,
    assert_api_entry_allowed,
)
from trading_engine.testing.helpers import make_host

_ENGINE_SRC = Path(__file__).resolve().parents[2] / "src" / "trading_engine"

# Methods that perform broker I/O (must not be called under ``with self.lock``).
_API_ENTRY_METHODS = frozenset(
    {
        "_call_api",
        "sync_positions",
        "read_broker_position",
        "login",
        "activate_ca",
        "place_order",
    }
)


class TestDomainLock(unittest.TestCase):
    def test_held_by_current_thread_tracks_depth(self) -> None:
        lock = DomainLock()
        self.assertFalse(lock.held_by_current_thread())
        with lock:
            self.assertTrue(lock.held_by_current_thread())
            self.assertTrue(lock.locked())
        self.assertFalse(lock.held_by_current_thread())
        self.assertFalse(lock.locked())

    def test_assert_api_entry_raises_when_domain_held(self) -> None:
        lock = DomainLock()
        with lock:
            with self.assertRaises(LockOrderError):
                assert_api_entry_allowed(lock)

    def test_assert_api_entry_ok_when_released(self) -> None:
        lock = DomainLock()
        with lock:
            pass
        assert_api_entry_allowed(lock)  # no raise

    def test_api_critical_section_blocks_under_domain_lock(self) -> None:
        domain = DomainLock()
        api = threading.RLock()
        with domain:
            with self.assertRaises(LockOrderError):
                with api_critical_section(domain, api):
                    pass

    def test_other_thread_domain_hold_does_not_block_api_entry(self) -> None:
        """G0 checks current thread only — peer holding domain is fine."""
        domain = DomainLock()
        ready = threading.Event()
        release = threading.Event()

        def holder() -> None:
            with domain:
                ready.set()
                release.wait(timeout=2.0)

        t = threading.Thread(target=holder)
        t.start()
        self.assertTrue(ready.wait(timeout=2.0))
        assert_api_entry_allowed(domain)  # this thread does not hold domain
        release.set()
        t.join(timeout=2.0)


class TestEngineCallApiLockOrder(unittest.TestCase):
    def test_call_api_raises_while_holding_domain_lock(self) -> None:
        host = make_host()
        with host.lock:
            with self.assertRaises(LockOrderError):
                host._call_api(lambda: 1)

    def test_call_api_ok_outside_domain_lock(self) -> None:
        host = make_host()
        self.assertEqual(host._call_api(lambda: 42), 42)

    def test_call_api_after_snapshot_release_ok(self) -> None:
        """Canonical pattern: brief domain snapshot → API → re-lock."""
        host = make_host()
        with host.lock:
            _qty = host._book.position_qty
        host._call_api(lambda: None)
        with host.lock:
            self.assertEqual(host._book.position_qty, _qty)

    def test_flat_attr_write_rejected(self) -> None:
        host = make_host()
        with self.assertRaises(AttributeError):
            host.position_qty = 1  # type: ignore[attr-defined]
        with self.assertRaises(AttributeError):
            host._api_connected = False  # type: ignore[attr-defined]
        self.assertEqual(host._book.position_qty, 0)
        self.assertTrue(host._link._api_connected)


class TestLockOrderSourceAudit(unittest.TestCase):
    """Heuristic AST audit — not full dataflow.

    Flags broker I/O nested under ``with self.lock``:
    - ``self._call_api(...)`` / denylisted helpers
    - ``with self._api_lock``
    - ``api_critical_section(...)``
    """

    def test_no_api_entry_inside_self_lock_with_block(self) -> None:
        violations: list[str] = []
        for path in sorted(_ENGINE_SRC.rglob("*.py")):
            if path.name == "locking.py":
                continue
            src = path.read_text(encoding="utf-8")
            try:
                tree = ast.parse(src, filename=str(path))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.With):
                    continue
                if not any(_is_self_lock_ctx(item) for item in node.items):
                    continue
                for child in ast.walk(node):
                    if isinstance(child, ast.Call) and _is_forbidden_api_call(child):
                        rel = path.relative_to(_ENGINE_SRC)
                        violations.append(
                            f"{rel}:{child.lineno} API entry under with self.lock"
                        )
                    if isinstance(child, ast.With) and child is not node:
                        if any(_is_api_lock_ctx(item) for item in child.items):
                            rel = path.relative_to(_ENGINE_SRC)
                            violations.append(
                                f"{rel}:{child.lineno} with _api_lock under with self.lock"
                            )
        self.assertEqual(
            violations,
            [],
            "Phase G0: release domain lock before broker I/O:\n" + "\n".join(violations),
        )


def _is_self_lock_ctx(item: ast.withitem) -> bool:
    ctx = item.context_expr
    if isinstance(ctx, ast.Attribute) and ctx.attr == "lock":
        if isinstance(ctx.value, ast.Name) and ctx.value.id == "self":
            return True
    return False


def _is_api_lock_ctx(item: ast.withitem) -> bool:
    ctx = item.context_expr
    if isinstance(ctx, ast.Attribute) and ctx.attr == "_api_lock":
        return True
    if isinstance(ctx, ast.Call):
        func = ctx.func
        if isinstance(func, ast.Name) and func.id == "api_critical_section":
            return True
        if isinstance(func, ast.Attribute) and func.attr == "api_critical_section":
            return True
        if isinstance(func, ast.Attribute) and func.attr == "_api_section":
            return True
    return False


def _is_forbidden_api_call(call: ast.Call) -> bool:
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr in _API_ENTRY_METHODS:
        return True
    if isinstance(func, ast.Name) and func.id == "api_critical_section":
        return True
    return False


if __name__ == "__main__":
    unittest.main()
