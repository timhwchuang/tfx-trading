"""CapitalStore: atomic JSON persistence for progressive MDD."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from trading_engine.adapters.mock import MockOrderAdapter
from trading_engine.core.capital_store import CapitalStore
from trading_engine.core.order_events import FUTURES_DEAL, FUTURES_ORDER
from trading_engine.core.risk import CapitalRiskState
from trading_engine.core.runtime_config import RuntimeConfig
from trading_engine.core.types import OrderSignal
from trading_engine.engine import TradingEngine
from trading_engine.testing.defaults import default_test_settings
from trading_engine.testing.helpers import StubStrategy, make_host


def _order_new(order_id: str) -> dict:
    return {
        "operation": {"op_code": "00", "op_type": "New"},
        "status": {"status": "Submitted", "deal_quantity": 0},
        "trade_id": order_id,
    }


def _deal(order_id: str, *, action: str, price: str) -> dict:
    return {
        "price": price,
        "quantity": 1,
        "action": action,
        "trade_id": order_id,
    }


class TestCapitalStore(unittest.TestCase):
    def test_disabled_store_is_noop(self):
        store = CapitalStore(None)
        self.assertFalse(store.enabled)
        self.assertIsNone(store.load(product_code="TMFR1"))
        self.assertFalse(store.save(CapitalRiskState(), product_code="TMFR1"))

    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "capital_risk.json"
            store = CapitalStore(p)
            state = CapitalRiskState(
                realized_pnl=-40.0, equity_peak=100.0, capital_frozen=True
            )
            self.assertTrue(store.save(state, product_code="TMFR1"))
            self.assertTrue(p.is_file())
            loaded = store.load(product_code="TMFR1")
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.realized_pnl, -40.0)
            self.assertEqual(loaded.equity_peak, 100.0)
            self.assertTrue(loaded.capital_frozen)
            self.assertEqual(loaded.current_drawdown, 140.0)

    def test_product_mismatch_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "cap.json"
            store = CapitalStore(p)
            store.save(
                CapitalRiskState(realized_pnl=1.0, equity_peak=1.0),
                product_code="TMFR1",
            )
            loaded = store.load(product_code="TXFR1")
            self.assertIsNone(loaded)

    def test_empty_product_code_in_file_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "cap.json"
            p.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "product_code": "",
                        "realized_pnl": -10.0,
                        "equity_peak": 0.0,
                        "capital_frozen": True,
                    }
                ),
                encoding="utf-8",
            )
            store = CapitalStore(p)
            self.assertIsNone(store.load(product_code="TMFR1"))

    def test_corrupt_file_returns_none(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "cap.json"
            p.write_text("not-json{{{", encoding="utf-8")
            store = CapitalStore(p)
            self.assertIsNone(store.load(product_code="TMFR1"))

    def test_engine_load_on_construct_and_persist_on_clear(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "cap.json"
            store = CapitalStore(p)
            store.save(
                CapitalRiskState(
                    realized_pnl=-25.0, equity_peak=0.0, capital_frozen=True
                ),
                product_code="TMFR1",
            )
            host = make_host()
            host._capital_store = store
            host._load_capital_state()
            self.assertTrue(host.capital_frozen)
            self.assertEqual(host.realized_pnl, -25.0)
            # make_host default max_mdd=0 → sticky freeze must not block entry
            self.assertFalse(host.entry_blocked)

            host.clear_capital_risk()
            self.assertFalse(host.capital_frozen)
            raw = json.loads(p.read_text(encoding="utf-8"))
            self.assertFalse(raw["capital_frozen"])
            self.assertEqual(raw["realized_pnl"], 0.0)

    def test_sticky_freeze_ignored_when_mdd_gate_off(self):
        """max_mdd<=0 must not apply capital_frozen even if present on disk."""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "cap.json"
            store = CapitalStore(p)
            store.save(
                CapitalRiskState(
                    realized_pnl=-40.0, equity_peak=0.0, capital_frozen=True
                ),
                product_code="TMFR1",
            )
            cfg = RuntimeConfig(
                default_test_settings(), overlay={"max_mdd_points": 0.0}
            )
            api = MagicMock()
            host = TradingEngine(
                api=api,
                strategy=StubStrategy(),
                runtime_config=cfg,
                order_adapter=MockOrderAdapter(api),
                capital_store=store,
            )
            self.assertTrue(host.capital_frozen)  # book flag still loaded
            self.assertFalse(host._capital_gate_active())
            self.assertFalse(host.entry_blocked)

    def test_sticky_freeze_applies_when_mdd_gate_on(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "cap.json"
            store = CapitalStore(p)
            store.save(
                CapitalRiskState(
                    realized_pnl=-40.0, equity_peak=0.0, capital_frozen=True
                ),
                product_code="TMFR1",
            )
            cfg = RuntimeConfig(
                default_test_settings(), overlay={"max_mdd_points": 10.0}
            )
            api = MagicMock()
            host = TradingEngine(
                api=api,
                strategy=StubStrategy(),
                runtime_config=cfg,
                order_adapter=MockOrderAdapter(api),
                capital_store=store,
            )
            self.assertTrue(host.capital_frozen)
            self.assertTrue(host.entry_blocked)

    def test_load_re_eval_freezes_when_mdd_enabled(self):
        """Book with deep drawdown + newly enabled max_mdd freezes on load."""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "cap.json"
            store = CapitalStore(p)
            store.save(
                CapitalRiskState(
                    realized_pnl=-50.0, equity_peak=0.0, capital_frozen=False
                ),
                product_code="TMFR1",
            )
            base = default_test_settings()
            # frozen dataclass — replace via RuntimeConfig overlay
            cfg = RuntimeConfig(base, overlay={"max_mdd_points": 10.0})
            api = MagicMock()
            host = TradingEngine(
                api=api,
                strategy=StubStrategy(),
                runtime_config=cfg,
                order_adapter=MockOrderAdapter(api),
                capital_store=store,
            )
            self.assertTrue(host.capital_frozen)
            self.assertTrue(host.entry_blocked)
            raw = json.loads(p.read_text(encoding="utf-8"))
            self.assertTrue(raw["capital_frozen"])

    def test_exit_fill_persists_and_new_engine_reloads_freeze(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "cap.json"
            store = CapitalStore(p)
            base = default_test_settings()
            cfg = RuntimeConfig(base, overlay={"max_mdd_points": 10.0})
            api = MagicMock()
            host = TradingEngine(
                api=api,
                strategy=StubStrategy(),
                runtime_config=cfg,
                order_adapter=MockOrderAdapter(api),
                capital_store=store,
            )
            host._validate_order_signal = MagicMock(return_value=True)

            entry = OrderSignal(
                "Buy", 1, 18000.0, "entry", exchange_ts=100, signal_id="e1"
            )
            host._arm_pending(entry)
            host.handle_order_event(FUTURES_ORDER, _order_new("buy-1"))
            host.handle_order_event(
                FUTURES_DEAL, _deal("buy-1", action="Buy", price="18000")
            )
            exit_sig = OrderSignal(
                "Sell", 1, 17990.0, "exit", exchange_ts=200, signal_id="x1"
            )
            host._arm_pending(exit_sig)
            host.handle_order_event(FUTURES_ORDER, _order_new("sell-1"))
            host.handle_order_event(
                FUTURES_DEAL, _deal("sell-1", action="Sell", price="17990")
            )

            self.assertTrue(host.capital_frozen)
            self.assertTrue(p.is_file())
            raw = json.loads(p.read_text(encoding="utf-8"))
            self.assertTrue(raw["capital_frozen"])
            self.assertEqual(raw["realized_pnl"], -10.0)

            host2 = TradingEngine(
                api=MagicMock(),
                strategy=StubStrategy(),
                runtime_config=cfg,
                order_adapter=MockOrderAdapter(MagicMock()),
                capital_store=CapitalStore(p),
            )
            self.assertTrue(host2.capital_frozen)
            self.assertTrue(host2.entry_blocked)
            self.assertEqual(host2.realized_pnl, -10.0)


class TestResolveCapitalStatePath(unittest.TestCase):
    def test_relative_anchors_to_base_not_cwd(self):
        from config import resolve_capital_state_path

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old = os.getcwd()
            try:
                # CWD elsewhere must not change resolved path
                os.chdir(tempfile.gettempdir())
                resolved = resolve_capital_state_path(
                    "var/capital_risk.json", base_dir=root
                )
            finally:
                os.chdir(old)
            self.assertEqual(
                Path(resolved),
                (root / "var" / "capital_risk.json").resolve(),
            )

    def test_absolute_unchanged(self):
        from config import resolve_capital_state_path

        with tempfile.TemporaryDirectory() as td:
            abs_path = Path(td) / "cap.json"
            resolved = resolve_capital_state_path(str(abs_path))
            self.assertEqual(Path(resolved), abs_path.resolve())

    def test_empty_disabled(self):
        from config import resolve_capital_state_path

        self.assertEqual(resolve_capital_state_path(""), "")
        self.assertEqual(resolve_capital_state_path(None), "")


if __name__ == "__main__":
    unittest.main()
