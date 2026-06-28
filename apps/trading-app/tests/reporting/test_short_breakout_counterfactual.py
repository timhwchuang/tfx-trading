"""Tests for short breakout counterfactual."""

from __future__ import annotations

import datetime as dt
import unittest

from reporting.short_breakout_counterfactual import (
    BreakoutSignal,
    _evaluate_phase0_gate,
    _evaluate_phase0_gate_params,
    detect_breakout_signal,
    simulate_breakout_entry,
)
from storage.kbar_loader import KBarRecord


def _bar(
    hour: int,
    minute: int,
    *,
    o: float,
    h: float,
    low: float,
    c: float,
    vol: int = 200,
) -> KBarRecord:
    ts = dt.datetime(2026, 4, 1, hour, minute, 0)
    return KBarRecord(ts=ts, Open=o, High=h, Low=low, Close=c, Volume=vol)


class TestDetectBreakout(unittest.TestCase):
    def test_long_breakout_on_close_above_prior_high(self) -> None:
        bars = [
            _bar(9, 0, o=100, h=101, low=99, c=100, vol=100),
            _bar(9, 1, o=100, h=101, low=99, c=100, vol=100),
            _bar(9, 2, o=100, h=101, low=99, c=100, vol=100),
            _bar(9, 3, o=100, h=101, low=99, c=100, vol=100),
            _bar(9, 4, o=100, h=101, low=99, c=100, vol=100),
            _bar(9, 5, o=101, h=105, low=100, c=104, vol=300),
        ]
        skip = dt.time(8, 55)
        signal = detect_breakout_signal(
            bars,
            5,
            lookback_bars=5,
            breakout_atr_k=0.0,
            vol_p70=150.0,
            min_range_atr_k=0.1,
            skip_open_until=skip,
        )
        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.direction, "Long")

    def test_skips_low_volume(self) -> None:
        bars = [
            _bar(9, 0, o=100, h=101, low=99, c=100, vol=100),
            _bar(9, 1, o=100, h=101, low=99, c=100, vol=100),
            _bar(9, 2, o=101, h=105, low=100, c=104, vol=50),
        ]
        signal = detect_breakout_signal(
            bars,
            2,
            lookback_bars=2,
            breakout_atr_k=0.0,
            vol_p70=150.0,
            min_range_atr_k=0.1,
            skip_open_until=dt.time(8, 55),
        )
        self.assertIsNone(signal)

    def test_close_1h_only_skips_mid_session(self) -> None:
        bars = [
            _bar(9, 0, o=100, h=101, low=99, c=100, vol=100),
            _bar(9, 1, o=100, h=101, low=99, c=100, vol=100),
            _bar(9, 2, o=101, h=105, low=100, c=104, vol=300),
        ]
        signal = detect_breakout_signal(
            bars,
            2,
            lookback_bars=2,
            breakout_atr_k=0.0,
            vol_p70=150.0,
            min_range_atr_k=0.1,
            skip_open_until=dt.time(8, 55),
            close_1h_only=True,
        )
        self.assertIsNone(signal)

    def test_close_1h_only_allows_close_hour(self) -> None:
        bars = [
            _bar(12, 45, o=100, h=101, low=99, c=100, vol=100),
            _bar(12, 46, o=100, h=101, low=99, c=100, vol=100),
            _bar(12, 47, o=101, h=105, low=100, c=104, vol=300),
        ]
        signal = detect_breakout_signal(
            bars,
            2,
            lookback_bars=2,
            breakout_atr_k=0.0,
            vol_p70=150.0,
            min_range_atr_k=0.1,
            skip_open_until=dt.time(8, 55),
            close_1h_only=True,
        )
        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.session_bucket, "close_1h")


class TestSimulateEntry(unittest.TestCase):
    def test_simulate_produces_pnl_fields(self) -> None:
        signal = BreakoutSignal(
            day=dt.date(2026, 4, 1),
            bar_idx=5,
            direction="Long",
            entry_ts=1000,
            entry_price=100.0,
            atr=25.0,
            prior_high=99.0,
            prior_low=98.0,
            bar_volume=200,
            bar_range=5.0,
            session_bucket="mid",
            lookback_bars=5,
            breakout_atr_k=0.0,
        )
        ticks = [(1000, 100.0, 1, 1), (1100, 110.0, 1, 1)]
        row = simulate_breakout_entry(signal, ticks)
        self.assertIn("gross_atr_sim", row)
        self.assertIn("net_scalp", row)
        self.assertEqual(row["direction"], "Long")


class TestPhase0Gate(unittest.TestCase):
    def test_pass_when_bucket_qualifies(self) -> None:
        summary = {
            "lb10_bk0": {
                "mid": {
                    "atr_barrier_180s": {
                        "n": 40,
                        "gross_mean": 6.0,
                        "net_mean": 1.0,
                    }
                }
            }
        }
        gate = _evaluate_phase0_gate(summary)
        self.assertTrue(gate["pass"])
        self.assertIsNotNone(gate["best_passing"])


class TestPhase0GateParams(unittest.TestCase):
    def test_pass_on_param_summary(self) -> None:
        summary = {
            "lb10_bk0.1": {
                "atr_barrier_180s": {
                    "n": 67,
                    "gross_mean": 7.24,
                    "net_mean": 2.24,
                }
            }
        }
        gate = _evaluate_phase0_gate_params(summary)
        self.assertTrue(gate["pass"])


if __name__ == "__main__":
    unittest.main()
