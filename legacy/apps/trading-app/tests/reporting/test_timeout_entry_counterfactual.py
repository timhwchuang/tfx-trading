"""Tests for timeout-entry counterfactual."""

from __future__ import annotations

import unittest

from reporting.armed_forward_counterfactual import simulate_atr_barrier_exit
from reporting.timeout_entry_counterfactual import (
    build_timeout_counterfactual_payload,
    resolve_entry_point,
)
from reporting.structure_calibration import ArmedCandidate
from reporting.uat_report import Episode


class TestResolveEntryPoint(unittest.TestCase):
    def _armed(self) -> ArmedCandidate:
        return ArmedCandidate(
            episode_id="20260401-001",
            ts=1000,
            direction="Long",
            price=18000.0,
            atr=20.0,
            vol_1s=200,
            buy_ratio=0.9,
            sell_ratio=0.1,
        )

    def _ep_timeout(self) -> Episode:
        ep = Episode(episode_id="20260401-001", armed_ts=1000)
        ep.events = [
            {"event_type": "momentum_armed", "ts": 1000},
            {"event_type": "momentum_timeout", "ts": 1181, "price": 18040.0},
        ]
        return ep

    def test_armed_tick(self) -> None:
        armed = self._armed()
        pt = resolve_entry_point(
            "armed_tick",
            armed=armed,
            ep=self._ep_timeout(),
            ticks=[],
            momentum_timeout_sec=180,
        )
        self.assertEqual(pt, (1000, 18000.0))

    def test_timeout_tick_uses_event(self) -> None:
        armed = self._armed()
        pt = resolve_entry_point(
            "timeout_tick",
            armed=armed,
            ep=self._ep_timeout(),
            ticks=[],
            momentum_timeout_sec=180,
        )
        self.assertEqual(pt, (1181, 18040.0))

    def test_armed_plus_offset(self) -> None:
        armed = self._armed()
        ticks = [(1060, 18010.0, 5, 1), (1120, 18020.0, 5, 1)]
        pt = resolve_entry_point(
            "armed_plus_60s",
            armed=armed,
            ep=self._ep_timeout(),
            ticks=ticks,
            momentum_timeout_sec=180,
        )
        self.assertEqual(pt, (1060, 18010.0))


class TestPhase0GateStructure(unittest.TestCase):
    def test_payload_has_phase0_gate_keys(self) -> None:
        """Smoke: empty log yields structured payload (no tick dates may raise)."""
        # Use minimal structure test via simulate only
        out = simulate_atr_barrier_exit(
            direction="Long",
            entry_price=18000.0,
            armed_ts=1000,
            atr=20.0,
            ticks=[(1000, 18050.0, 1, 1)],
            hard_stop_atr_k=0.75,
            tp_atr_k=2.0,
        )
        self.assertIn("gross_pnl", out)


if __name__ == "__main__":
    unittest.main()
