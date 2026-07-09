"""Tests for ORB counterfactual."""

from __future__ import annotations

import datetime as dt
import unittest

from reporting.orb_counterfactual import (
    compute_opening_range,
    detect_orb_signal,
    simulate_orb_entry,
    _evaluate_phase0_gate_params,
)
from storage.kbar_loader import KBarRecord


def _bar(hour: int, minute: int, *, o: float, h: float, low: float, c: float) -> KBarRecord:
    return KBarRecord(
        ts=dt.datetime(2026, 4, 1, hour, minute, 0),
        Open=o,
        High=h,
        Low=low,
        Close=c,
        Volume=200,
    )


def _range_bars_15() -> list[KBarRecord]:
    """15 one-minute bars 08:45–08:59, range 100–102."""
    bars: list[KBarRecord] = []
    for m in range(15):
        bars.append(_bar(8, 45 + m, o=101, h=102, low=100, c=101))
    return bars


class TestOpeningRange(unittest.TestCase):
    def test_computes_range_width(self) -> None:
        bars = _range_bars_15()
        opening = compute_opening_range(bars, 15, min_range_atr_k=0.01)
        self.assertIsNotNone(opening)
        assert opening is not None
        self.assertEqual(opening.range_high, 102.0)
        self.assertEqual(opening.range_low, 100.0)
        self.assertEqual(opening.range_width, 2.0)

    def test_skips_narrow_range(self) -> None:
        bars = [_bar(8, 45 + m, o=100, h=100.2, low=100, c=100.1) for m in range(15)]
        self.assertIsNone(compute_opening_range(bars, 15, min_range_atr_k=0.5))


class TestOrbSignal(unittest.TestCase):
    def test_first_long_break_after_range(self) -> None:
        bars = _range_bars_15()
        bars.append(_bar(9, 0, o=102, h=104, low=101, c=103))
        opening = compute_opening_range(bars[:15], 15, min_range_atr_k=0.01)
        assert opening is not None
        signal = detect_orb_signal(bars, opening, buffer_atr_k=0.0)
        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.direction, "Long")

    def test_no_break_stays_flat(self) -> None:
        bars = _range_bars_15()
        bars.append(_bar(9, 0, o=101, h=101.5, low=100.5, c=101))
        opening = compute_opening_range(bars[:15], 15, min_range_atr_k=0.01)
        assert opening is not None
        self.assertIsNone(detect_orb_signal(bars, opening, buffer_atr_k=0.0))


class TestSimulateEntry(unittest.TestCase):
    def test_produces_pnl(self) -> None:
        from reporting.orb_counterfactual import OrbSignal

        signal = OrbSignal(
            day=dt.date(2026, 4, 1),
            range_minutes=15,
            buffer_atr_k=0.0,
            direction="Long",
            entry_ts=1000,
            entry_price=103.0,
            atr=25.0,
            range_high=102.0,
            range_low=100.0,
            range_width=2.0,
        )
        ticks = [(1000, 103.0, 1, 1), (1100, 110.0, 1, 1)]
        row = simulate_orb_entry(signal, ticks)
        self.assertIn("net_atr_sim", row)


class TestPhase0Gate(unittest.TestCase):
    def test_pass_on_param(self) -> None:
        summary = {
            "rm15_bk0": {
                "atr_barrier_180s": {"n": 40, "gross_mean": 6.0, "net_mean": 1.0}
            }
        }
        self.assertTrue(_evaluate_phase0_gate_params(summary)["pass"])


if __name__ == "__main__":
    unittest.main()
