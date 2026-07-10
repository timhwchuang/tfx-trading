"""Unit tests for CapitalService (Host MDD policy impl)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from trading_engine.capital import CapitalService
from trading_engine.core.capital_store import CapitalStore
from trading_engine.core.risk import CapitalRiskState


class TestCapitalService(unittest.TestCase):
    def test_load_gate_off_keeps_flag_does_not_block(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "cap.json"
            store = CapitalStore(p)
            store.save(
                CapitalRiskState(
                    realized_pnl=-25.0, equity_peak=0.0, capital_frozen=True
                ),
                product_code="TMFR1",
            )
            svc = CapitalService(store, product_code="TMFR1", max_mdd_points=0.0)
            alerts = svc.load()
            self.assertEqual(alerts, [])
            self.assertTrue(svc.capital_frozen)
            self.assertFalse(svc.gate_active())
            self.assertFalse(svc.blocks_entry())

    def test_on_exit_fill_freezes_and_persists(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "cap.json"
            store = CapitalStore(p)
            svc = CapitalService(store, product_code="TMFR1", max_mdd_points=10.0)
            svc.load()
            evt = svc.on_exit_fill(-12.0)
            self.assertTrue(evt.newly_frozen)
            self.assertIsNotNone(evt.freeze_alert)
            self.assertTrue(evt.persist_ok)
            self.assertTrue(svc.blocks_entry())
            raw = json.loads(p.read_text(encoding="utf-8"))
            self.assertTrue(raw["capital_frozen"])
            self.assertEqual(raw["realized_pnl"], -12.0)

    def test_clear_unfreezes(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "cap.json"
            store = CapitalStore(p)
            svc = CapitalService(store, product_code="TMFR1", max_mdd_points=10.0)
            svc.on_exit_fill(-20.0)
            self.assertTrue(svc.capital_frozen)
            ok, _alert = svc.clear()
            self.assertTrue(ok)
            self.assertFalse(svc.capital_frozen)
            self.assertEqual(svc.realized_pnl, 0.0)


if __name__ == "__main__":
    unittest.main()
