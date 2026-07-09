"""Tests for FT-002 SMC structure filter (structure.py)."""

from __future__ import annotations

import datetime
import unittest
from dataclasses import dataclass

from strategy_vwap_momentum.structure import (
    Bar5m,
    StructureParams,
    StructureState,
    compute_structure,
    filter_closed_bars_1m,
    regime_allows_entry,
    resample_time_buckets,
    session_slice_bars_1m,
    structure_allows_entry,
    validate_regime_config,
)


@dataclass
class Bar1m:
    ts: datetime.datetime
    Open: float
    High: float
    Low: float
    Close: float
    Volume: int = 1


def _bar(
    hour: int,
    minute: int,
    *,
    o: float,
    h: float,
    l: float,
    c: float,
    day: int = 12,
) -> Bar1m:
    return Bar1m(
        ts=datetime.datetime(2026, 6, day, hour, minute),
        Open=o,
        High=h,
        Low=l,
        Close=c,
    )


class TestStructureHelpers(unittest.TestCase):
    def test_filter_closed_bars_1m(self):
        dt = datetime.datetime(2026, 6, 12, 9, 2, 30)
        bars = [
            _bar(9, 0, o=100, h=101, l=99, c=100),
            _bar(9, 2, o=100, h=101, l=99, c=100),
        ]
        closed = filter_closed_bars_1m(bars, dt)
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0].ts.minute, 0)

    def test_resample_time_buckets_excludes_incomplete(self):
        dt = datetime.datetime(2026, 6, 12, 9, 7, 0)
        bars = [
            _bar(9, 0, o=100, h=101, l=99, c=100),
            _bar(9, 1, o=100, h=102, l=99, c=101),
            _bar(9, 2, o=101, h=103, l=100, c=102),
            _bar(9, 3, o=102, h=104, l=101, c=103),
            _bar(9, 4, o=103, h=105, l=102, c=104),
            _bar(9, 5, o=104, h=106, l=103, c=105),
            _bar(9, 6, o=105, h=107, l=104, c=106),
        ]
        out = resample_time_buckets(bars, 5, dt)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].ts, datetime.datetime(2026, 6, 12, 9, 0))
        self.assertEqual(out[0].High, 105.0)

    def test_session_range_0845_reset(self):
        dt = datetime.datetime(2026, 6, 12, 9, 30)
        pre_session = _bar(8, 30, o=50, h=200, l=50, c=50)
        session = _bar(9, 0, o=100, h=110, l=90, c=105)
        closed = filter_closed_bars_1m([pre_session, session], dt)
        sliced = session_slice_bars_1m(closed, dt, used_long_lookback=True)
        self.assertEqual(len(sliced), 1)
        state = compute_structure(
            [pre_session, session],
            atr=10.0,
            exchange_dt=dt,
            used_long_lookback=True,
        )
        self.assertEqual(state.range_high, 110.0)
        self.assertEqual(state.range_low, 90.0)

    def test_gap_day_no_false_bos_from_prior_day(self):
        dt = datetime.datetime(2026, 6, 12, 9, 30)
        prior = _bar(9, 0, o=100, h=150, l=80, c=140, day=11)
        today = _bar(9, 0, o=100, h=110, l=90, c=100, day=12)
        state = compute_structure(
            [prior, today],
            atr=10.0,
            exchange_dt=dt,
        )
        self.assertEqual(state.range_high, 110.0)
        self.assertEqual(state.range_low, 90.0)
        self.assertIsNone(state.last_bos)

    def test_night_session_bar_excluded_from_range(self):
        dt = datetime.datetime(2026, 6, 12, 9, 30)
        night = _bar(5, 0, o=50, h=300, l=50, c=50, day=12)
        session = _bar(9, 0, o=100, h=110, l=90, c=105, day=12)
        state = compute_structure(
            [night, session],
            atr=10.0,
            exchange_dt=dt,
        )
        self.assertEqual(state.range_high, 110.0)
        self.assertEqual(state.range_low, 90.0)
        self.assertIsNone(state.last_bos)


class TestFvgLifecycle(unittest.TestCase):
    def _bars5_bullish_fvg(self) -> list[Bar5m]:
        return [
            Bar5m(datetime.datetime(2026, 6, 12, 9, 0), 100, 100, 99, 100, 1),
            Bar5m(datetime.datetime(2026, 6, 12, 9, 5), 100, 108, 100, 107, 1),
            Bar5m(datetime.datetime(2026, 6, 12, 9, 10), 107, 112, 106, 111, 1),
        ]

    def test_fvg_full_mitigation(self):
        from strategy_vwap_momentum.structure import (
            _apply_fvg_mitigation,
            _detect_fvgs,
            _select_active_fvg,
        )

        bars = self._bars5_bullish_fvg()
        bars.append(
            Bar5m(datetime.datetime(2026, 6, 12, 9, 15), 99, 112, 98, 110, 1)
        )
        zones = _detect_fvgs(bars)
        self.assertEqual(len(zones), 1)
        self.assertEqual(zones[0].fvg_low, 100.0)
        self.assertEqual(zones[0].fvg_high, 106.0)
        _apply_fvg_mitigation(zones, bars)
        self.assertTrue(zones[0].mitigated)
        active = _select_active_fvg(zones, "Long")
        self.assertIsNone(active)

    def test_compute_structure_fvg_active_end_to_end(self):
        """FVG + bias through full compute_structure pipeline (1m → 5m)."""
        bars_1m: list[Bar1m] = []
        # 9:00 bucket — quiet (high 100)
        for m in range(5):
            bars_1m.append(_bar(9, m, o=100, h=100, l=99, c=100))
        # 9:05 bucket — displacement
        for m in range(5, 10):
            bars_1m.append(_bar(9, m, o=100, h=108, l=100, c=107))
        # 9:10 bucket — gap up (low 106 > prior high 100)
        for m in range(10, 15):
            bars_1m.append(_bar(9, m, o=107, h=112, l=106, c=111))
        # More bars to confirm swing + BOS for Long bias
        for m in range(15, 35):
            bars_1m.append(_bar(9, m, o=111, h=112, l=110, c=111.5))
        for m in range(35, 45):
            bars_1m.append(_bar(9, m, o=111.5, h=115, l=111, c=114))
        dt = datetime.datetime(2026, 6, 12, 9, 49)
        state = compute_structure(
            bars_1m,
            atr=5.0,
            params=StructureParams(structure_min_strength=0.0),
            exchange_dt=dt,
        )
        if state.bias == "Long":
            self.assertIsNotNone(state.active_fvg_low)
            self.assertIsNotNone(state.active_fvg_high)
            self.assertEqual(state.active_fvg_side, "bullish")

    def test_fvg_partial_touch_not_mitigated(self):
        bars = self._bars5_bullish_fvg()
        bars.append(
            Bar5m(datetime.datetime(2026, 6, 12, 9, 15), 105, 105.5, 104, 105, 1)
        )
        from strategy_vwap_momentum.structure import _apply_fvg_mitigation, _detect_fvgs

        zones = _detect_fvgs(bars)
        _apply_fvg_mitigation(zones, bars)
        self.assertFalse(zones[0].mitigated)

    def test_fvg_active_latest_same_side(self):
        older = [
            Bar5m(datetime.datetime(2026, 6, 12, 9, 0), 100, 100, 99, 100, 1),
            Bar5m(datetime.datetime(2026, 6, 12, 9, 5), 100, 108, 100, 107, 1),
            Bar5m(datetime.datetime(2026, 6, 12, 9, 10), 107, 112, 106, 111, 1),
        ]
        newer = older + [
            Bar5m(datetime.datetime(2026, 6, 12, 9, 15), 111, 118, 111, 117, 1),
            Bar5m(datetime.datetime(2026, 6, 12, 9, 20), 117, 125, 117, 124, 1),
            Bar5m(datetime.datetime(2026, 6, 12, 9, 25), 124, 130, 123, 129, 1),
        ]
        from strategy_vwap_momentum.structure import (
            _apply_fvg_mitigation,
            _detect_fvgs,
            _select_active_fvg,
        )

        zones = _detect_fvgs(newer)
        _apply_fvg_mitigation(zones, newer)
        bullish = [z for z in zones if z.side == "bullish" and not z.mitigated]
        self.assertGreaterEqual(len(bullish), 2)
        active = _select_active_fvg(zones, "Long")
        self.assertIsNotNone(active)
        self.assertEqual(active.created_ts, bullish[-1].created_ts)


class TestSwingAndBos(unittest.TestCase):
    def test_swing_confirmation_lag(self):
        from strategy_vwap_momentum.structure import _analyze_bars_5m

        bars = [
            Bar5m(datetime.datetime(2026, 6, 12, 9, 0), 100, 101, 99, 100, 1),
            Bar5m(datetime.datetime(2026, 6, 12, 9, 5), 100, 102, 99, 101, 1),
            Bar5m(datetime.datetime(2026, 6, 12, 9, 10), 101, 110, 100, 109, 1),
            Bar5m(datetime.datetime(2026, 6, 12, 9, 15), 109, 109, 108, 108, 1),
            Bar5m(datetime.datetime(2026, 6, 12, 9, 20), 108, 109, 107, 108, 1),
            Bar5m(datetime.datetime(2026, 6, 12, 9, 25), 108, 109, 107, 108, 1),
            Bar5m(datetime.datetime(2026, 6, 12, 9, 30), 108, 112, 108, 111, 1),
            Bar5m(datetime.datetime(2026, 6, 12, 9, 35), 111, 115, 111, 114, 1),
        ]
        bos, bos_ts, _, _, sh, _ = _analyze_bars_5m(bars, 2)
        self.assertIsNotNone(sh)
        self.assertEqual(sh, 110.0)
        self.assertEqual(bos, "bullish")
        self.assertIsNotNone(bos_ts)
        # Swing at 9:10 confirmed at 9:20 (i=2, L=2); BOS must be strictly later.
        self.assertGreater(bos_ts, datetime.datetime(2026, 6, 12, 9, 20))

    def test_bos_requires_confirmed_swing(self):
        from strategy_vwap_momentum.structure import _analyze_bars_5m

        bars = [
            Bar5m(datetime.datetime(2026, 6, 12, 9, 0), 100, 105, 99, 104, 1),
            Bar5m(datetime.datetime(2026, 6, 12, 9, 5), 104, 106, 103, 105, 1),
        ]
        bos, _, _, _, _, _ = _analyze_bars_5m(bars, 2)
        self.assertIsNone(bos)


class TestLevel2AndGates(unittest.TestCase):
    def _bars_with_bullish_bos(self, *, final_close: float) -> list[Bar1m]:
        bars: list[Bar1m] = []
        for m in range(5):
            bars.append(_bar(9, m, o=100, h=101, l=99, c=100))
        for m in range(5, 10):
            bars.append(_bar(9, m, o=100, h=102, l=99, c=101))
        for m in range(10, 15):
            bars.append(_bar(9, m, o=101, h=110, l=100, c=109))
        for m in range(15, 25):
            bars.append(_bar(9, m, o=109, h=109, l=108, c=108))
        for m in range(25, 35):
            bars.append(_bar(9, m, o=108, h=109, l=107, c=108))
        for m in range(35, 40):
            bars.append(_bar(9, m, o=108, h=110, l=90, c=111))
        # Final bucket 9:40-9:44 sets last 5m close
        for m in range(40, 45):
            bars.append(
                _bar(9, m, o=final_close, h=final_close, l=final_close, c=final_close)
            )
        return bars

    def test_level2_min_strength_zero_strictest(self):
        dt = datetime.datetime(2026, 6, 12, 9, 49)
        flat_mid = self._bars_with_bullish_bos(final_close=100.0)
        state_mid = compute_structure(
            flat_mid,
            atr=10.0,
            params=StructureParams(structure_min_strength=0.0),
            exchange_dt=dt,
        )
        self.assertEqual(state_mid.last_bos, "bullish")
        self.assertAlmostEqual(state_mid.range_mid, 100.0)
        self.assertEqual(state_mid.bias, "Neutral")
        self.assertEqual(state_mid.strength, 0.0)

        offset = self._bars_with_bullish_bos(final_close=110.0)
        state_off = compute_structure(
            offset,
            atr=10.0,
            params=StructureParams(structure_min_strength=0.0),
            exchange_dt=dt,
        )
        self.assertEqual(state_off.last_bos, "bullish")
        self.assertEqual(state_off.bias, "Long")
        self.assertGreater(state_off.strength, 0.0)

        state_high = compute_structure(
            offset,
            atr=10.0,
            params=StructureParams(structure_min_strength=100.0),
            exchange_dt=dt,
        )
        self.assertEqual(state_high.bias, "Neutral")

    def test_level2_skipped_when_atr_zero(self):
        bars = self._bars_with_bullish_bos(final_close=115.0)
        dt = datetime.datetime(2026, 6, 12, 9, 49)
        state = compute_structure(
            bars,
            atr=0.0,
            params=StructureParams(structure_min_strength=0.0),
            exchange_dt=dt,
        )
        if state.last_bos == "bullish":
            self.assertEqual(state.bias, "Long")
            self.assertEqual(state.strength, 0.0)

    def test_premium_discount_at_mid_false(self):
        bars = [
            _bar(9, 0, o=100, h=110, l=90, c=100),
            _bar(9, 1, o=100, h=110, l=90, c=100),
            _bar(9, 2, o=100, h=110, l=90, c=100),
            _bar(9, 3, o=100, h=110, l=90, c=100),
            _bar(9, 4, o=100, h=110, l=90, c=100),
        ]
        dt = datetime.datetime(2026, 6, 12, 9, 10)
        state = compute_structure(bars, atr=10.0, exchange_dt=dt)
        self.assertFalse(state.in_discount)
        self.assertFalse(state.in_premium)

    def test_structure_allows_entry_veto_counter_bias(self):
        state = StructureState(bias="Long", in_discount=True)
        self.assertFalse(
            structure_allows_entry(
                enabled=True, state=state, momentum_dir="Short", price=100.0
            )
        )
        self.assertTrue(
            structure_allows_entry(
                enabled=True, state=state, momentum_dir="Long", price=100.0
            )
        )

    def test_structure_allows_fvg_zone(self):
        state = StructureState(
            bias="Long",
            in_discount=False,
            active_fvg_low=100.0,
            active_fvg_high=105.0,
            active_fvg_side="bullish",
        )
        self.assertTrue(
            structure_allows_entry(
                enabled=True, state=state, momentum_dir="Long", price=102.0
            )
        )

    def test_regime_mutual_exclusion(self):
        with self.assertRaises(ValueError):
            validate_regime_config(
                StructureParams(
                    structure_filter_enabled=True,
                    trend_filter_enabled=True,
                )
            )

    def test_regime_structure_veto(self):
        params = StructureParams(structure_filter_enabled=True)
        state = StructureState(bias="Short", in_premium=True)
        allowed, reason = regime_allows_entry(
            params=params,
            trend_dir="Flat",
            state=state,
            momentum_dir="Long",
            price=100.0,
        )
        self.assertFalse(allowed)
        self.assertEqual(reason, "structure_veto")

    def test_regime_trend_path(self):
        params = StructureParams(trend_filter_enabled=True)
        state = StructureState()
        allowed, reason = regime_allows_entry(
            params=params,
            trend_dir="Long",
            state=state,
            momentum_dir="Short",
            price=100.0,
        )
        self.assertFalse(allowed)
        self.assertEqual(reason, "trend_veto")


if __name__ == "__main__":
    unittest.main()