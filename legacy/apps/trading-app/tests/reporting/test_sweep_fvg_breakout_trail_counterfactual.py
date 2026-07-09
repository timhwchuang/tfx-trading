"""Tests for FT-019 sweep FVG breakout trail counterfactual."""

from __future__ import annotations

import datetime as dt
import unittest
from unittest.mock import patch

from reporting.sweep_fvg_breakout_trail_counterfactual import (
    EXIT_VARIANT,
    FINGERPRINT_WINDOW_SEC,
    MIN_RISK_PTS,
    SfbtParams,
    SfbtSignal,
    _evaluate_fingerprint_gate,
    _exit_diagnostics,
    _in_entry_window_ts,
    _price_in_fvg,
    detect_sfbt_signal,
    scan_sfbt_session,
    simulate_sfbt_entry,
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


def _fp() -> SfbtParams:
    return SfbtParams(45, 0.25, 120, 3, 6, 1.0, 2.0, 1.5, 0.5, 4.0)


def _ts(h: int, m: int, s: int = 0) -> int:
    return int(dt.datetime(2026, 4, 1, h, m, s).timestamp())


class TestHelpers(unittest.TestCase):
    def test_entry_window(self) -> None:
        self.assertTrue(_in_entry_window_ts(_ts(10, 0)))
        self.assertFalse(_in_entry_window_ts(_ts(12, 30)))

    def test_fvg_zone_inclusive(self) -> None:
        self.assertTrue(_price_in_fvg(100.0, 99.0, 101.0))
        self.assertFalse(_price_in_fvg(102.0, 99.0, 101.0))


class TestFingerprintGate(unittest.TestCase):
    def test_w900_pass(self) -> None:
        post = {"n": 16, "forward": {f"W{FINGERPRINT_WINDOW_SEC}": {"close_delta_median": 2.0}}}
        gate = _evaluate_fingerprint_gate(post)
        self.assertTrue(gate["pass"])
        self.assertEqual(gate["fingerprint_window_sec"], 900)

    def test_w900_direction_fail(self) -> None:
        post = {"n": 20, "forward": {f"W{FINGERPRINT_WINDOW_SEC}": {"close_delta_median": -1.0}}}
        gate = _evaluate_fingerprint_gate(post)
        self.assertFalse(gate["pass"])
        self.assertFalse(gate["direction_ok"])

    def test_w900_n_fail(self) -> None:
        post = {"n": 10, "forward": {f"W{FINGERPRINT_WINDOW_SEC}": {"close_delta_median": 3.0}}}
        gate = _evaluate_fingerprint_gate(post)
        self.assertFalse(gate["pass"])
        self.assertTrue(gate["direction_ok"])
        self.assertFalse(gate["n_ok"])


class TestScanSfbtSession(unittest.TestCase):
    def test_no_session_bars(self) -> None:
        rows, funnel = scan_sfbt_session([], params=_fp(), day=dt.date(2026, 4, 1), ticks=[])
        self.assertEqual(rows, [])
        self.assertEqual(funnel["days_with_session"], 0)

    @patch("reporting.sweep_fvg_breakout_trail_counterfactual.detect_sfbt_signal")
    def test_long_entry_completes_trail(self, mock_detect) -> None:
        day = dt.date(2026, 4, 1)
        bars = [
            _bar(9, 13, o=100, h=102, low=99, c=101),
            _bar(9, 14, o=101, h=103, low=100, c=102),
        ]
        entry_ts = _ts(10, 0)
        signal = SfbtSignal(
            day=day,
            params=_fp(),
            direction="Long",
            entry_ts=entry_ts,
            entry_price=110.0,
            atr=25.0,
            fvg_low=100.0,
            fvg_high=105.0,
            fvg_mid=102.5,
            sweep_ts=_ts(9, 30),
            reclaim_ts=_ts(9, 35),
            swing_low=98.0,
        )
        mock_detect.return_value = (
            signal,
            {
                "sweep_signal": True,
                "reclaim_ok": True,
                "fvg_active": True,
                "breakout_signal": True,
            },
        )
        ticks = [(entry_ts, 110.0, 1, 1), (entry_ts + 60, 111.0, 1, 1)]
        rows, funnel = scan_sfbt_session(bars, params=_fp(), day=day, ticks=ticks)
        self.assertEqual(funnel["entry"], 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["direction"], "Long")
        self.assertEqual(rows[0]["exit_variant"], EXIT_VARIANT)
        self.assertIn("fvg_mid_trail_sim", rows[0])

    @patch("reporting.sweep_fvg_breakout_trail_counterfactual.detect_sfbt_signal")
    def test_no_sweep_no_entry(self, mock_detect) -> None:
        day = dt.date(2026, 4, 1)
        bars = [
            _bar(9, 13, o=100, h=102, low=99, c=101),
            _bar(9, 14, o=101, h=103, low=100, c=102),
        ]
        mock_detect.return_value = (
            None,
            {
                "sweep_signal": False,
                "reclaim_ok": False,
                "fvg_active": False,
                "breakout_signal": False,
            },
        )
        rows, funnel = scan_sfbt_session(bars, params=_fp(), day=day, ticks=[(_ts(10, 0), 100.0, 1, 1)])
        self.assertEqual(rows, [])
        self.assertEqual(funnel["sweep_signal"], 0)
        self.assertEqual(funnel["entry"], 0)

    @patch("reporting.sweep_fvg_breakout_trail_counterfactual.detect_sfbt_signal")
    def test_funnel_six_stages(self, mock_detect) -> None:
        day = dt.date(2026, 4, 1)
        bars = [
            _bar(9, 13, o=100, h=102, low=99, c=101),
            _bar(9, 14, o=101, h=103, low=100, c=102),
        ]
        mock_detect.return_value = (
            None,
            {
                "sweep_signal": True,
                "reclaim_ok": True,
                "fvg_active": True,
                "breakout_signal": True,
            },
        )
        _, funnel = scan_sfbt_session(bars, params=_fp(), day=day, ticks=[(_ts(10, 0), 100.0, 1, 1)])
        self.assertEqual(funnel["sweep_signal"], 1)
        self.assertEqual(funnel["reclaim_ok"], 1)
        self.assertEqual(funnel["fvg_active"], 1)
        self.assertEqual(funnel["breakout_signal"], 1)
        self.assertEqual(funnel["entry"], 0)


class TestDetectSfbtSignal(unittest.TestCase):
    @patch("reporting.sweep_fvg_breakout_trail_counterfactual._qualifying_bullish_fvg")
    @patch("reporting.sweep_fvg_breakout_trail_counterfactual._swing_pool")
    def test_breakout_after_1230_blocked(self, mock_pool, mock_fvg) -> None:
        mock_pool.return_value = [(_ts(9, 16), 100.0)]
        mock_fvg.return_value = {
            "fvg_low": 100.0,
            "fvg_high": 105.0,
            "fvg_mid": 102.5,
            "created_ts": _ts(9, 20),
        }
        bars = [
            _bar(9, 13, o=100, h=102, low=99, c=101),
            _bar(9, 14, o=101, h=103, low=100, c=102),
        ]
        ticks = [
            (_ts(9, 17), 93.0, 1, 1),
            (_ts(9, 18), 101.0, 1, 1),
            (_ts(12, 30), 106.0, 1, 1),
        ]
        signal, flags = detect_sfbt_signal(bars, ticks, params=_fp(), day=dt.date(2026, 4, 1), atr=25.0)
        self.assertIsNone(signal)
        self.assertFalse(flags["breakout_signal"])

    @patch("reporting.sweep_fvg_breakout_trail_counterfactual._qualifying_bullish_fvg")
    @patch("reporting.sweep_fvg_breakout_trail_counterfactual._swing_pool")
    def test_risk_unit_too_small_skips_entry(self, mock_pool, mock_fvg) -> None:
        mock_pool.return_value = [(_ts(9, 16), 100.0)]
        mock_fvg.return_value = {
            "fvg_low": 100.0,
            "fvg_high": 105.0,
            "fvg_mid": 104.0,
            "created_ts": _ts(9, 20),
        }
        bars = [
            _bar(9, 13, o=100, h=102, low=99, c=101),
            _bar(9, 14, o=101, h=103, low=100, c=102),
        ]
        ticks = [
            (_ts(9, 17), 93.0, 1, 1),
            (_ts(9, 18), 101.0, 1, 1),
            (_ts(10, 0), 106.0, 1, 1),
        ]
        signal, flags = detect_sfbt_signal(bars, ticks, params=_fp(), day=dt.date(2026, 4, 1), atr=25.0)
        self.assertIsNone(signal)
        self.assertTrue(flags["breakout_signal"])
        self.assertLess(106.0 - 104.0, MIN_RISK_PTS)

    @patch("reporting.sweep_fvg_breakout_trail_counterfactual._qualifying_bullish_fvg")
    @patch("reporting.sweep_fvg_breakout_trail_counterfactual._swing_pool")
    def test_zone_touch_not_entry(self, mock_pool, mock_fvg) -> None:
        mock_pool.return_value = [(_ts(9, 16), 100.0)]
        mock_fvg.return_value = {
            "fvg_low": 100.0,
            "fvg_high": 105.0,
            "fvg_mid": 102.5,
            "created_ts": _ts(9, 20),
        }
        bars = [
            _bar(9, 13, o=100, h=102, low=99, c=101),
            _bar(9, 14, o=101, h=103, low=100, c=102),
        ]
        ticks = [
            (_ts(9, 17), 93.0, 1, 1),
            (_ts(9, 18), 101.0, 1, 1),
            (_ts(10, 0), 103.0, 1, 1),
        ]
        signal, _ = detect_sfbt_signal(bars, ticks, params=_fp(), day=dt.date(2026, 4, 1), atr=25.0)
        self.assertIsNone(signal)

    @patch("reporting.sweep_fvg_breakout_trail_counterfactual._qualifying_bullish_fvg")
    @patch("reporting.sweep_fvg_breakout_trail_counterfactual._swing_pool")
    def test_second_breakout_ignored_after_entry(self, mock_pool, mock_fvg) -> None:
        mock_pool.return_value = [(_ts(9, 16), 100.0)]
        mock_fvg.return_value = {
            "fvg_low": 100.0,
            "fvg_high": 105.0,
            "fvg_mid": 102.5,
            "created_ts": _ts(9, 20),
        }
        bars = [
            _bar(9, 13, o=100, h=102, low=99, c=101),
            _bar(9, 14, o=101, h=103, low=100, c=102),
        ]
        ticks = [
            (_ts(9, 17), 93.0, 1, 1),
            (_ts(9, 18), 101.0, 1, 1),
            (_ts(10, 0), 111.0, 1, 1),
            (_ts(10, 5), 115.0, 1, 1),
        ]
        signal, _ = detect_sfbt_signal(bars, ticks, params=_fp(), day=dt.date(2026, 4, 1), atr=25.0)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.entry_ts, _ts(10, 0))
        self.assertEqual(signal.entry_price, 111.0)


class TestExitDiagnostics(unittest.TestCase):
    def test_exit_gap_and_pct_hit_2r(self) -> None:
        rows = [
            {
                "gross_atr_sim": 5.0,
                "atr": 10.0,
                "risk_unit": 5.0,
                "fvg_mid_trail_sim": {"mfe": 20.0},
            },
            {
                "gross_atr_sim": 3.0,
                "atr": 10.0,
                "risk_unit": 4.0,
                "fvg_mid_trail_sim": {"mfe": 8.0},
            },
        ]
        diag = _exit_diagnostics(rows)
        self.assertEqual(diag["exit_gap"], 10.0)
        self.assertEqual(diag["pct_hit_2R"], 1.0)


class TestLongOnly(unittest.TestCase):
    def test_signal_direction_long(self) -> None:
        signal = SfbtSignal(
            day=dt.date(2026, 4, 1),
            params=_fp(),
            direction="Long",
            entry_ts=_ts(10, 0),
            entry_price=110.0,
            atr=25.0,
            fvg_low=100.0,
            fvg_high=105.0,
            fvg_mid=102.5,
            sweep_ts=_ts(9, 30),
            reclaim_ts=_ts(9, 35),
            swing_low=98.0,
        )
        row = simulate_sfbt_entry(signal, [(signal.entry_ts, 110.0, 1, 1)])
        self.assertEqual(row["direction"], "Long")


if __name__ == "__main__":
    unittest.main()
