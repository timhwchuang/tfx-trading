"""Tests for FT-013 SuperTrend flip counterfactual."""

from __future__ import annotations

import datetime as dt
import unittest

from reporting.supertrend_flip_counterfactual import (
    Bar5m,
    FINGERPRINT_COOLDOWN_BARS,
    StfParams,
    SuperTrendSeries,
    _confirm_tick_allowed,
    _evaluate_fingerprint_gate,
    _evaluate_phase0_gate_params,
    _slippage_ratio_summary,
    compute_supertrend_v1,
    find_confirm_tick_long,
    find_confirm_tick_short,
    resample_1m_to_5m_closed,
    scan_stf_session,
    simulate_stf_long_entry,
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


def _bar5m(hour: int, minute: int, *, h: float, low: float, c: float) -> Bar5m:
    return Bar5m(
        ts=dt.datetime(2026, 4, 1, hour, minute, 0),
        open=c,
        high=h,
        low=low,
        close=c,
        volume=1000.0,
    )


def _dummy_session_1m(n: int = 35) -> list[KBarRecord]:
    return [
        _bar(8, 45 + i, o=100, h=101, low=99, c=100)
        for i in range(n)
        if 45 + i < 60
    ] + [
        _bar(9, i, o=100, h=101, low=99, c=100)
        for i in range(max(0, n - 15))
    ]


class TestResample5m(unittest.TestCase):
    def test_partial_bucket_excluded(self) -> None:
        bars = [_bar(9, 15 + m, o=100, h=101, low=99, c=100) for m in range(3)]
        partial_dt = dt.datetime(2026, 4, 1, 9, 17, 0)
        self.assertEqual(resample_1m_to_5m_closed(bars, partial_dt), [])

        closed_dt = dt.datetime(2026, 4, 1, 9, 20, 0)
        closed = resample_1m_to_5m_closed(bars, closed_dt)
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0].close, 100.0)


class TestSuperTrendV1(unittest.TestCase):
    def test_bar_zero_no_flip(self) -> None:
        bars = [
            _bar5m(9, 15, h=110, low=100, c=105),
            _bar5m(9, 20, h=112, low=101, c=111),
        ]
        st = compute_supertrend_v1(bars, atr_period=2, st_mult=3.0, min_atr_pts=25.0)
        self.assertFalse(st.flip_long[0])
        self.assertFalse(st.flip_short[0])

    def test_ratchet_line_matches_trend_side(self) -> None:
        bars = [
            _bar5m(9, 15, h=120, low=100, c=105),
            _bar5m(9, 20, h=130, low=102, c=125),
            _bar5m(9, 25, h=140, low=110, c=135),
            _bar5m(9, 30, h=145, low=115, c=120),
        ]
        st = compute_supertrend_v1(bars, atr_period=2, st_mult=3.0, min_atr_pts=25.0)
        for i in range(len(bars)):
            if st.trend[i] == 1:
                self.assertAlmostEqual(st.supertrend_line[i], st.final_lb[i])
            else:
                self.assertAlmostEqual(st.supertrend_line[i], st.final_ub[i])

    def test_sma_atr_floor_min_25(self) -> None:
        bars = [_bar5m(9, 15 + 5 * i, h=101, low=100, c=100.5) for i in range(4)]
        st = compute_supertrend_v1(bars, atr_period=2, st_mult=3.0, min_atr_pts=25.0)
        self.assertTrue(all(a >= 25.0 for a in st.atr))


class TestConfirmTick(unittest.TestCase):
    def test_long_waits_for_second_tick(self) -> None:
        arm_ts = 1000
        st_line = 100.0
        ticks = [(1000, 99.0, 1, 1), (1001, 101.0, 1, 1)]
        hit = find_confirm_tick_long(ticks, arm_ts, st_line)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit[0], 1001)
        self.assertEqual(hit[1], 101.0)

    def test_short_confirm_below_line(self) -> None:
        ticks = [(1000, 101.0, 1, 1), (1001, 99.0, 1, 1)]
        hit = find_confirm_tick_short(ticks, 1000, 100.0)
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit[1], 99.0)

    def test_session_boundaries_on_confirm_tick(self) -> None:
        ts_1144 = int(dt.datetime(2026, 4, 1, 11, 44, 0).timestamp())
        ts_1145 = int(dt.datetime(2026, 4, 1, 11, 45, 0).timestamp())
        ts_1200 = int(dt.datetime(2026, 4, 1, 12, 0, 0).timestamp())
        self.assertTrue(_confirm_tick_allowed(ts_1144))
        self.assertFalse(_confirm_tick_allowed(ts_1145))
        self.assertFalse(_confirm_tick_allowed(ts_1200))


class TestCooldown(unittest.TestCase):
    def test_second_flip_within_cooldown_ignored(self) -> None:
        day = dt.date(2026, 4, 1)
        bars_5m = [
            _bar5m(9, 15, h=100, low=100, c=100),
            _bar5m(9, 20, h=100, low=100, c=100),
            _bar5m(9, 25, h=100, low=100, c=100),
            _bar5m(9, 30, h=100, low=100, c=100),
            _bar5m(9, 35, h=100, low=100, c=100),
            _bar5m(9, 40, h=100, low=100, c=100),
            _bar5m(9, 45, h=100, low=100, c=100),
            _bar5m(9, 50, h=100, low=100, c=100),
        ]
        n = len(bars_5m)
        flip_long = [False] * n
        flip_long[2] = True
        flip_long[4] = True
        st = SuperTrendSeries(
            atr=[25.0] * n,
            final_ub=[110.0] * n,
            final_lb=[90.0] * n,
            trend=[1] * n,
            supertrend_line=[90.0] * n,
            flip_long=flip_long,
            flip_short=[False] * n,
        )
        arm2 = int(bars_5m[2].bucket_close.timestamp())
        arm4 = int(bars_5m[4].bucket_close.timestamp())
        ticks = [
            (arm2, 101.0, 1, 1),
            (arm4, 101.0, 1, 1),
        ]
        params = StfParams(
            atr_period=10,
            st_mult=3.0,
            cooldown_bars=FINGERPRINT_COOLDOWN_BARS,
            k_sl=1.0,
            tp_atr_k=2.0,
        )
        long_rows, _, funnel = scan_stf_session(
            _dummy_session_1m(),
            ticks,
            day,
            params,
            st_override=st,
            bars_5m_override=bars_5m,
        )
        self.assertEqual(funnel["flip_detected_long"], 2)
        self.assertEqual(funnel["entry"], 1)
        self.assertEqual(len(long_rows), 1)


class TestSimulateEntry(unittest.TestCase):
    def test_entry_fill_plus_slippage_and_barrier(self) -> None:
        params = StfParams(10, 3.0, 6, 1.0, 2.0)
        bar = _bar5m(9, 30, h=110, low=100, c=105)
        ticks = [(1000, 105.0, 1, 1), (1100, 130.0, 1, 1)]
        row = simulate_stf_long_entry(
            day=dt.date(2026, 4, 1),
            params=params,
            bar_idx=1,
            flip_bar=bar,
            entry_ts=1000,
            entry_price=105.0,
            atr_effective=25.0,
            ticks=ticks,
        )
        self.assertEqual(row["entry_fill"], 106.0)
        self.assertIn("net_atr_sim", row)
        self.assertIn("atr_barrier_sim", row)
        self.assertAlmostEqual(row["slippage_ratio"], 1.0 / 25.0, places=4)


class TestPayloadHelpers(unittest.TestCase):
    def test_slippage_ratio_summary(self) -> None:
        rows = [{"slippage_ratio": 0.04}, {"slippage_ratio": 0.08}]
        summary = _slippage_ratio_summary(rows)
        self.assertIn("slippage_ratio_p50", summary)
        self.assertIn("slippage_ratio_p90", summary)

    def test_fingerprint_gate_w30(self) -> None:
        post = {"n": 40, "forward": {"W1800": {"close_delta_median": 3.0}}}
        self.assertTrue(_evaluate_fingerprint_gate(post)["pass"])
        post_fail = {"n": 40, "forward": {"W1800": {"close_delta_median": -1.0}}}
        self.assertFalse(_evaluate_fingerprint_gate(post_fail)["pass"])

    def test_phase0_gate(self) -> None:
        summary = {
            "ap10_sm3p0_cd6_ksl1_tp2": {
                "atr_barrier_180s": {"n": 40, "gross_mean": 6.0, "net_mean": 1.0}
            }
        }
        self.assertTrue(_evaluate_phase0_gate_params(summary)["pass"])


class TestShortAppendix(unittest.TestCase):
    def test_short_rows_have_no_barrier_pnl(self) -> None:
        day = dt.date(2026, 4, 1)
        bars_5m = [_bar5m(9, 15 + 5 * i, h=100, low=100, c=100) for i in range(6)]
        n = len(bars_5m)
        flip_short = [False] * n
        flip_short[3] = True
        st = SuperTrendSeries(
            atr=[25.0] * n,
            final_ub=[100.0] * n,
            final_lb=[90.0] * n,
            trend=[-1] * n,
            supertrend_line=[100.0] * n,
            flip_long=[False] * n,
            flip_short=flip_short,
        )
        arm = int(bars_5m[3].bucket_close.timestamp())
        ticks = [(arm, 99.0, 1, 1)]
        params = StfParams(10, 3.0, 6, 1.0, 2.0)
        _, short_rows, funnel = scan_stf_session(
            _dummy_session_1m(),
            ticks,
            day,
            params,
            st_override=st,
            bars_5m_override=bars_5m,
        )
        self.assertEqual(funnel["flip_detected_short"], 1)
        self.assertEqual(len(short_rows), 1)
        self.assertTrue(short_rows[0]["appendix_only"])
        self.assertNotIn("gross_atr_sim", short_rows[0])


if __name__ == "__main__":
    unittest.main()
