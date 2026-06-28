"""Tests for FT-016 gap drive continuation counterfactual."""

from __future__ import annotations

import datetime as dt
import unittest

from reporting.gap_drive_continuation_counterfactual import (
    FINGERPRINT_GAP_K_ATR,
    FINGERPRINT_RETRACE_MAX_FRAC,
    GdcParams,
    MIN_GAP_PTS,
    _evaluate_fingerprint_gate,
    _open_0845,
    _retrace_ok,
    detect_gdc_signal,
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


def _fp() -> GdcParams:
    return GdcParams(FINGERPRINT_GAP_K_ATR, FINGERPRINT_RETRACE_MAX_FRAC, 1.0, 2.0)


class TestRetrace(unittest.TestCase):
    def test_gap_up_retrace_fail(self) -> None:
        bars = [_bar(9, 15 + m, o=100, h=102, low=50, c=101) for m in range(30)]
        self.assertFalse(
            _retrace_ok(gap_pts=100, open_0845=100, drive_bars=bars, retrace_max_frac=0.40)
        )

    def test_gap_up_retrace_ok(self) -> None:
        bars = [_bar(9, 15 + m, o=100, h=102, low=70, c=101) for m in range(30)]
        self.assertTrue(
            _retrace_ok(gap_pts=100, open_0845=100, drive_bars=bars, retrace_max_frac=0.40)
        )


class TestDetectSignal(unittest.TestCase):
    def test_flat_gap_skipped(self) -> None:
        day = dt.date(2026, 4, 1)
        bars = [_bar(8, 45, o=100, h=101, low=99, c=100)]
        sig, flags = detect_gdc_signal(bars, [], params=_fp(), day=day, prior_close=100.0)
        self.assertIsNone(sig)
        self.assertFalse(flags["gap_qualify"])


class TestGateHelpers(unittest.TestCase):
    def test_fingerprint_g3s(self) -> None:
        post = {"n": 16, "forward": {"W1800": {"close_delta_median": 2.0}}}
        self.assertTrue(_evaluate_fingerprint_gate(post)["pass"])


class TestOpen0845(unittest.TestCase):
    def test_finds_open_at_0846_edge(self) -> None:
        bars = [_bar(8, 46, o=123, h=124, low=122, c=123)]
        self.assertEqual(_open_0845(bars), 123.0)


if __name__ == "__main__":
    unittest.main()
