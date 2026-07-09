"""Tests for FT-014 morning VWAP hold pullback counterfactual."""

from __future__ import annotations

import datetime as dt
import unittest

from reporting.morning_vwap_hold_pullback_counterfactual import (
    DEFAULT_MIN_ATR,
    FINGERPRINT_HOLD_MIN_BARS,
    FINGERPRINT_VWAP_SLOPE_BARS,
    MvhpParams,
    _bar_close_time,
    _evaluate_fingerprint_gate,
    _evaluate_phase0_gate_params,
    _hold_bar_ok,
    _in_entry_window,
    _touch_bar_ok,
    _vwap_slope_ok,
    detect_mvhp_signal,
    scan_mvhp_session,
    simulate_mvhp_entry,
)
from reporting.vwap_trend_pullback_counterfactual import BarCtx, _build_bar_contexts
from storage.kbar_loader import KBarRecord


def _bar(hour: int, minute: int, *, o: float, h: float, low: float, c: float, vol: int = 200) -> KBarRecord:
    return KBarRecord(
        ts=dt.datetime(2026, 4, 1, hour, minute, 0),
        Open=o,
        High=h,
        Low=low,
        Close=c,
        Volume=vol,
    )


def _fp_params() -> MvhpParams:
    return MvhpParams(
        hold_min_bars=FINGERPRINT_HOLD_MIN_BARS,
        touch_buf_k=0.10,
        pullback_vol_ratio_max=0.85,
        vwap_slope_bars=FINGERPRINT_VWAP_SLOPE_BARS,
        k_sl=1.0,
        tp_atr_k=2.0,
    )


class TestEntryWindow(unittest.TestCase):
    def test_0915_close_in_1030_out(self) -> None:
        self.assertTrue(_in_entry_window(_bar(9, 14, o=100, h=101, low=99, c=100)))
        self.assertFalse(_in_entry_window(_bar(10, 29, o=100, h=101, low=99, c=100)))


class TestHoldAndTouch(unittest.TestCase):
    def test_vwap_slope_three_bars(self) -> None:
        vwaps = [100.0, 100.5, 101.0, 101.5]
        self.assertFalse(_vwap_slope_ok(vwaps, 1, 3))
        self.assertTrue(_vwap_slope_ok(vwaps, 3, 3))

    def test_deep_wick_touch_close_above_buffer(self) -> None:
        ctx = BarCtx(
            idx=0,
            ts=1000,
            close=101.0,
            high=102.0,
            low=99.0,
            volume=100.0,
            session_vwap=100.0,
            atr=25.0,
        )
        self.assertTrue(_touch_bar_ok(ctx, touch_buf_k=0.10))

    def test_hold_requires_close_above_vwap(self) -> None:
        ctx = BarCtx(0, 1000, 99.0, 100.0, 98.0, 100.0, 100.0, 25.0)
        self.assertFalse(_hold_bar_ok(ctx, [100.0], vwap_slope_bars=2, min_atr=25.0))


class TestDetectSignal(unittest.TestCase):
    def _drive_then_touch_bars(self) -> list[KBarRecord]:
        bars: list[KBarRecord] = []
        for m in range(15):
            h = 9
            minute = 14 + m
            if minute >= 60:
                h = 10
                minute -= 60
            vol = 300 if m < 10 else 150
            px = 100 + m * 0.3
            bars.append(
                _bar(
                    h,
                    minute,
                    o=px,
                    h=px + 0.5,
                    low=px - 0.2 if m < 10 else px - 2.5,
                    c=px + 0.1 if m < 10 else px - 0.5,
                    vol=vol,
                )
            )
        return bars

    def test_hold_insufficient_no_entry(self) -> None:
        bars = [_bar(9, 14 + m, o=101, h=102, low=100, c=101, vol=200) for m in range(5)]
        contexts = _build_bar_contexts(bars)
        sig, flags = detect_mvhp_signal(contexts, bars, params=_fp_params())
        self.assertIsNone(sig)
        self.assertFalse(flags["hold_pass"])

    def test_second_touch_ignored_via_scan(self) -> None:
        params = MvhpParams(3, 0.10, 0.85, 2, 1.0, 2.0)
        bars = []
        for m in range(8):
            bars.append(_bar(9, 15 + m, o=102, h=103, low=101.5, c=102, vol=250))
        bars.append(_bar(9, 23, o=101, h=101.5, low=100.0, c=100.5, vol=100))
        bars.append(_bar(9, 24, o=100.5, h=101.0, low=100.0, c=100.8, vol=100))
        ticks = [(int(bars[-2].ts.timestamp()) + 60, 100.5, 1, 1)]
        rows, funnel = scan_mvhp_session(bars, params=params, ticks=ticks)
        self.assertLessEqual(len(rows), 1)


class TestSimulateEntry(unittest.TestCase):
    def test_barrier_exit_fields(self) -> None:
        from reporting.morning_vwap_hold_pullback_counterfactual import MvhpSignal

        sig = MvhpSignal(
            day=dt.date(2026, 4, 1),
            params=_fp_params(),
            entry_ts=1000,
            entry_price=100.0,
            atr=25.0,
            session_vwap=99.0,
            hold_bars=10,
            hold_start_idx=0,
        )
        ticks = [(1000, 100.0, 1, 1), (1600, 110.0, 1, 1)]
        row = simulate_mvhp_entry(sig, ticks)
        self.assertEqual(row["entry_price"], 100.0)
        self.assertIn("net_atr_sim", row)
        self.assertEqual(row["exit_variant"], "atr_barrier_900s")


class TestGateHelpers(unittest.TestCase):
    def test_fingerprint_gate(self) -> None:
        post = {"n": 40, "forward": {"W1800": {"close_delta_median": 2.0}}}
        self.assertTrue(_evaluate_fingerprint_gate(post)["pass"])

    def test_phase0_gate(self) -> None:
        summary = {
            "hm10_tb0p1_vr0p85_vs3_ksl1_tp2": {
                "atr_barrier_900s": {"n": 40, "gross_mean": 6.0, "net_mean": 1.0}
            }
        }
        self.assertTrue(_evaluate_phase0_gate_params(summary)["pass"])


if __name__ == "__main__":
    unittest.main()
