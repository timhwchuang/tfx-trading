"""Phase G0: dual-lock contract (domain lock vs API lock)."""

from __future__ import annotations

import ast
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
        import threading

        domain = DomainLock()
        api = threading.RLock()
        with domain:
            with self.assertRaises(LockOrderError):
                with api_critical_section(domain, api):
                    pass


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
        # API after release
        host._call_api(lambda: None)
        with host.lock:
            self.assertEqual(host._book.position_qty, _qty)


class TestLockOrderSourceAudit(unittest.TestCase):
    """Static-ish audit: no function body should nest _call_api inside ``with self.lock``.

    Heuristic AST walk — not a full dataflow analysis. Catches the common
    anti-pattern of broker I/O under domain lock in the same ``with`` block.
    """

    def test_no_call_api_inside_self_lock_with_block(self) -> None:
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
                    if isinstance(child, ast.Call) and _is_call_api(child):
                        rel = path.relative_to(_ENGINE_SRC)
                        violations.append(f"{rel}:{child.lineno} _call_api under with self.lock")
        self.assertEqual(
            violations,
            [],
            "Phase G0: release domain lock before broker I/O:\n" + "\n".join(violations),
        )


def _is_self_lock_ctx(item: ast.withitem) -> bool:
    ctx = item.context_expr
    # with self.lock:
    if isinstance(ctx, ast.Attribute) and ctx.attr == "lock":
        if isinstance(ctx.value, ast.Name) and ctx.value.id == "self":
            return True
    return False


def _is_call_api(call: ast.Call) -> bool:
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr == "_call_api":
        return True
    return False


if __name__ == "__main__":
    unittest.main()
