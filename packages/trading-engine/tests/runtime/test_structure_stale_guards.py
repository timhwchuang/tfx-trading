"""FT-002 Phase 3: structure_stale gate (mirrors atr_stale)."""

from __future__ import annotations

import datetime
import unittest
from dataclasses import replace
from unittest.mock import MagicMock

from trading_engine.core.runtime_config import RuntimeConfig
from trading_engine.testing.defaults import default_test_settings
from trading_engine.testing.helpers import make_host


class TestStructureStaleGuards(unittest.TestCase):
    def _host_with_cfg(self, **overrides):
        base = replace(default_test_settings(), **overrides)
        host = make_host()
        host._cfg = RuntimeConfig(base)
        return host

    def test_structure_stale_off_when_filter_disabled(self):
        host = self._host_with_cfg(structure_filter_enabled=False)
        host.indicators.last_structure_refresh = 0.0
        self.assertFalse(host._is_structure_stale(5000))

    def test_structure_stale_when_never_refreshed_or_too_old(self):
        host = self._host_with_cfg(structure_filter_enabled=True)
        host.indicators.last_structure_refresh = 0.0
        self.assertTrue(host._is_structure_stale(5000))

        host.indicators.last_structure_refresh = 1000.0
        self.assertFalse(host._is_structure_stale(1500))
        self.assertTrue(host._is_structure_stale(2000))

    def test_risk_gate_exposes_structure_stale(self):
        host = self._host_with_cfg(structure_filter_enabled=True)
        host.indicators.last_structure_refresh = 1000.0
        dt = datetime.datetime(2026, 6, 10, 10, 0, 0)
        self.assertFalse(host._risk_gate(1500, dt).structure_stale)
        self.assertTrue(host._risk_gate(1700, dt).structure_stale)

    def test_failed_structure_refresh_keeps_success_ts(self):
        host = self._host_with_cfg(structure_filter_enabled=True)
        host.contract = MagicMock(code="TXFR1")
        host.api.kbars = MagicMock(side_effect=RuntimeError("kbars down"))
        host.last_tick_exchange_ts = 1000
        host.indicators.last_structure_refresh = 500.0
        host.indicators.last_atr_refresh = 500.0

        host._atr_refresh_in_flight = True
        host.refresh_atr()

        self.assertEqual(host.indicators.last_structure_refresh, 500.0)
        self.assertFalse(host._atr_refresh_in_flight)


if __name__ == "__main__":
    unittest.main()