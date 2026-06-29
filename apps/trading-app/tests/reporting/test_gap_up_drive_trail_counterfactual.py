"""Tests for FT-018 gap up drive trail counterfactual."""

from __future__ import annotations

import datetime as dt
import unittest
from unittest.mock import patch

from reporting.gap_drive_continuation_counterfactual import (
    FINGERPRINT_GAP_K_ATR,
    FINGERPRINT_RETRACE_MAX_FRAC,
    GdcParams,
    GdcSignal,
    detect_gdc_signal,
)
from reporting.gap_up_drive_trail_counterfactual import (
    FINGERPRINT_WINDOW_SEC,
    GudtParams,
    _evaluate_fingerprint_gate,
    _exit_diagnostics,
    scan_gudt_session,
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


def _fp_gudt() -> GudtParams:
    return GudtParams(1.0, 0.40, 1.0, 1.0, 2.0, 0.5, 4.0)


def _fp_gdc() -> GdcParams:
    return GdcParams(FINGERPRINT_GAP_K_ATR, FINGERPRINT_RETRACE_MAX_FRAC, 1.0, 2.0)


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
        self.assertTrue(gate["n_ok"])

    def test_w900_n_fail(self) -> None:
        post = {"n": 10, "forward": {f"W{FINGERPRINT_WINDOW_SEC}": {"close_delta_median": 3.0}}}
        gate = _evaluate_fingerprint_gate(post)
        self.assertFalse(gate["pass"])
        self.assertTrue(gate["direction_ok"])
        self.assertFalse(gate["n_ok"])


class TestScanGudtSession(unittest.TestCase):
    def test_gap_down_skipped(self) -> None:
        day = dt.date(2026, 4, 1)
        bars = [_bar(8, 45, o=90, h=91, low=89, c=90)]
        rows, funnel = scan_gudt_session(
            bars,
            params=_fp_gudt(),
            day=day,
            prior_close=100.0,
            ticks=[],
        )
        self.assertEqual(rows, [])
        self.assertEqual(funnel["gap_qualify_up"], 0)

    def test_flat_gap_skipped(self) -> None:
        day = dt.date(2026, 4, 1)
        bars = [_bar(8, 45, o=100, h=101, low=99, c=100)]
        rows, funnel = scan_gudt_session(
            bars,
            params=_fp_gudt(),
            day=day,
            prior_close=100.0,
            ticks=[],
        )
        self.assertEqual(rows, [])
        self.assertEqual(funnel["entry"], 0)

    @patch("reporting.gap_up_drive_trail_counterfactual.detect_gdc_signal")
    def test_long_only_accepts_long_signal(self, mock_detect) -> None:
        day = dt.date(2026, 4, 1)
        bars = [
            _bar(8, 45, o=150, h=151, low=149, c=150),
            _bar(9, 13, o=150, h=152, low=149, c=151),
        ]
        signal = GdcSignal(
            day=day,
            params=_fp_gdc(),
            direction="Long",
            entry_ts=int(dt.datetime(2026, 4, 1, 9, 50).timestamp()),
            entry_price=105.0,
            atr=25.0,
            gap_pts=50.0,
            open_0845=150.0,
            prior_close=100.0,
            drive_high=104.0,
            drive_low=98.0,
        )
        mock_detect.return_value = (signal, {"retrace_ok": True, "break_signal": True})
        entry_ts = signal.entry_ts
        ticks = [
            (entry_ts, 105.0, 1, 1),
            (entry_ts + 60, 106.0, 1, 1),
        ]
        rows, funnel = scan_gudt_session(
            bars,
            params=_fp_gudt(),
            day=day,
            prior_close=100.0,
            ticks=ticks,
        )
        self.assertEqual(funnel["entry"], 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["direction"], "Long")
        self.assertEqual(rows[0]["exit_variant"], "atr_trail_skew_900s")

    @patch("reporting.gap_up_drive_trail_counterfactual.detect_gdc_signal")
    def test_short_signal_rejected(self, mock_detect) -> None:
        day = dt.date(2026, 4, 1)
        bars = [
            _bar(8, 45, o=100, h=101, low=99, c=100),
            _bar(9, 14, o=100, h=102, low=99, c=101),
        ]
        signal = GdcSignal(
            day=day,
            params=_fp_gdc(),
            direction="Short",
            entry_ts=int(dt.datetime(2026, 4, 1, 9, 50).timestamp()),
            entry_price=95.0,
            atr=25.0,
            gap_pts=-50.0,
            open_0845=50.0,
            prior_close=100.0,
            drive_high=102.0,
            drive_low=90.0,
        )
        mock_detect.return_value = (signal, {"retrace_ok": True, "break_signal": True})
        rows, funnel = scan_gudt_session(
            bars,
            params=_fp_gudt(),
            day=day,
            prior_close=100.0,
            ticks=[(signal.entry_ts, 95.0, 1, 1)],
        )
        self.assertEqual(rows, [])
        self.assertEqual(funnel["entry"], 0)


class TestExitDiagnostics(unittest.TestCase):
    def test_exit_gap_computed(self) -> None:
        rows = [
            {
                "gross_atr_sim": 5.0,
                "atr": 10.0,
                "atr_trail_sim": {"mfe": 20.0},
            },
            {
                "gross_atr_sim": 3.0,
                "atr": 10.0,
                "atr_trail_sim": {"mfe": 16.0},
            },
        ]
        diag = _exit_diagnostics(rows)
        self.assertEqual(diag["exit_gap"], 14.0)
        self.assertEqual(diag["pct_mfe_ge_1atr"], 1.0)


class TestEntryReuse(unittest.TestCase):
    def test_detect_gdc_long_only_subset(self) -> None:
        day = dt.date(2026, 4, 1)
        bars = [_bar(8, 45, o=100, h=101, low=99, c=100)]
        sig, _ = detect_gdc_signal(bars, [], params=_fp_gdc(), day=day, prior_close=100.0)
        self.assertIsNone(sig)


if __name__ == "__main__":
    unittest.main()
