"""Tests for regime VWAP stretch fade counterfactual."""

from __future__ import annotations

import datetime as dt
import unittest

from reporting.regime_vwap_stretch_fade_counterfactual import (
    EXIT_VARIANT,
    RegimeTickSnapshot,
    _evaluate_phase0_gate,
    build_day_rv_by_bar_time,
    compute_rv_recent_at_bar,
    morning_fade_window_for_ts,
    regime_ok,
    regime_pct_at_bar_time,
    simulate_regime_stretch_fade_entries,
)
from storage.kbar_loader import KBarRecord


def _bar(ts: dt.datetime, close: float) -> KBarRecord:
    return KBarRecord(
        ts=ts,
        Open=close,
        High=close + 1,
        Low=close - 1,
        Close=close,
        Volume=100,
    )


class TestMorningWindow(unittest.TestCase):
    def test_before_0900_out(self) -> None:
        ts = int(dt.datetime(2026, 4, 1, 8, 59, 0).timestamp())
        self.assertFalse(morning_fade_window_for_ts(ts))

    def test_0900_in(self) -> None:
        ts = int(dt.datetime(2026, 4, 1, 9, 0, 0).timestamp())
        self.assertTrue(morning_fade_window_for_ts(ts))

    def test_1030_out(self) -> None:
        ts = int(dt.datetime(2026, 4, 1, 10, 30, 0).timestamp())
        self.assertFalse(morning_fade_window_for_ts(ts))


class TestRegimePct(unittest.TestCase):
    def test_insufficient_history(self) -> None:
        pct = regime_pct_at_bar_time(0.01, dt.time(9, 15), [], {})
        self.assertIsNone(pct)

    def test_causal_uses_prior_days_only(self) -> None:
        t = dt.time(9, 15)
        prior_days = [dt.date(2026, 3, d) for d in range(24, 29)]
        rv_index = {day: {t: 0.02} for day in prior_days}
        rv_index[dt.date(2026, 4, 1)] = {t: 0.01}
        pct = regime_pct_at_bar_time(0.025, t, prior_days, rv_index)
        self.assertIsNotNone(pct)
        self.assertEqual(pct, 0.0)

    def test_regime_ok_threshold(self) -> None:
        self.assertTrue(regime_ok(20.0, 30))
        self.assertFalse(regime_ok(40.0, 30))
        self.assertFalse(regime_ok(None, 30))


class TestRvRecent(unittest.TestCase):
    def test_needs_window_bars(self) -> None:
        base = dt.datetime(2026, 4, 1, 8, 45)
        bars = [_bar(base + dt.timedelta(minutes=i), 18000.0 + i) for i in range(10)]
        self.assertIsNone(compute_rv_recent_at_bar(bars, 5, window=30))

    def test_uses_completed_bars_only(self) -> None:
        base = dt.datetime(2026, 4, 1, 8, 45)
        bars = [_bar(base + dt.timedelta(minutes=i), 18000.0 + i * 0.5) for i in range(35)]
        rv_at_31 = compute_rv_recent_at_bar(bars, 31, window=30)
        self.assertIsNotNone(rv_at_31)

    def test_build_day_map(self) -> None:
        base = dt.datetime(2026, 4, 1, 8, 45)
        bars = [_bar(base + dt.timedelta(minutes=i), 18000.0 + i * 0.5) for i in range(40)]
        m = build_day_rv_by_bar_time(bars, window=30)
        self.assertGreater(len(m), 0)


class TestSimulateEntries(unittest.TestCase):
    def test_regime_blocks_entry(self) -> None:
        snaps = [
            RegimeTickSnapshot(1000, 18050.0, 18000.0, 25.0, 2.0, True, 50.0, dt.time(9, 5)),
        ]
        ticks = [(1000, 18050.0, 1, 1), (1100, 18000.0, 1, 1)]
        rows = simulate_regime_stretch_fade_entries(
            snaps, ticks, stretch_k=1.5, vol_pct_max=30
        )
        self.assertEqual(len(rows), 0)

    def test_regime_allows_entry(self) -> None:
        snaps = [
            RegimeTickSnapshot(1000, 18050.0, 18000.0, 25.0, 2.0, True, 20.0, dt.time(9, 5)),
            RegimeTickSnapshot(1061, 18050.0, 18000.0, 25.0, 2.0, True, 20.0, dt.time(9, 6)),
        ]
        ticks = [(1000, 18050.0, 1, 1), (1100, 18000.0, 1, 1)]
        rows = simulate_regime_stretch_fade_entries(
            snaps, ticks, stretch_k=1.5, vol_pct_max=30, cooldown_sec=60
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["direction"], "Short")

    def test_outside_morning_no_entry(self) -> None:
        snaps = [
            RegimeTickSnapshot(1000, 18050.0, 18000.0, 25.0, 2.0, False, 10.0, dt.time(11, 0)),
        ]
        ticks = [(1000, 18050.0, 1, 1)]
        rows = simulate_regime_stretch_fade_entries(
            snaps, ticks, stretch_k=1.5, vol_pct_max=30
        )
        self.assertEqual(len(rows), 0)


class TestPhase0Gate(unittest.TestCase):
    def test_pass_selects_best_net(self) -> None:
        summary = {
            "k2p30": {EXIT_VARIANT: {"n": 40, "gross_mean": 6.0, "net_mean": 1.0, "gross_median": 0.0}},
            "k2p25": {EXIT_VARIANT: {"n": 50, "gross_mean": 7.0, "net_mean": 2.0, "gross_median": 1.0}},
        }
        rows = {
            "k2p30": [
                {"ts": 1, "direction": "Long", "gross_atr_sim": 1.0, "net_atr_sim": 1.0},
                {"ts": 2, "direction": "Short", "gross_atr_sim": 1.0, "net_atr_sim": 1.0},
            ] * 20,
            "k2p25": [
                {"ts": 1, "direction": "Long", "gross_atr_sim": 2.0, "net_atr_sim": 2.0},
                {"ts": 2, "direction": "Short", "gross_atr_sim": 1.0, "net_atr_sim": 1.0},
            ] * 25,
        }
        gate = _evaluate_phase0_gate(summary, rows)
        self.assertTrue(gate["pass"])
        self.assertEqual(gate["best_passing"]["param"], "k2p25")


if __name__ == "__main__":
    unittest.main()
