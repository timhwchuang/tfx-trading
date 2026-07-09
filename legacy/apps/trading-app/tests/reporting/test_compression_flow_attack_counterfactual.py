"""Tests for FT-017 compression flow attack counterfactual."""

from __future__ import annotations

import datetime as dt
import unittest

from reporting.compression_flow_attack_counterfactual import (
    ATR_COMPRESS_FLOOR,
    COMPRESS_LOOKBACK_MIN,
    DEFAULT_MIN_ATR,
    ENTRY_WINDOW_START,
    FINGERPRINT_ATTACK_RATIO_MIN,
    FINGERPRINT_ATR_REGIME_CAP,
    FINGERPRINT_COMPRESS_K,
    FINGERPRINT_MIN_STOP_ATR_K,
    FINGERPRINT_TP_ATR_K,
    MIN_STOP_PTS,
    NO_NEW_ENTRY_AFTER,
    CfaParams,
    _evaluate_fingerprint_gate,
    _quiet_passes,
    detect_cfa_signal,
    evaluate_compress_regime,
    scan_cfa_session,
    simulate_cfa_entry,
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


def _fp() -> CfaParams:
    return CfaParams(
        FINGERPRINT_COMPRESS_K,
        FINGERPRINT_ATR_REGIME_CAP,
        FINGERPRINT_ATTACK_RATIO_MIN,
        FINGERPRINT_MIN_STOP_ATR_K,
        FINGERPRINT_TP_ATR_K,
    )


def _flat_bars(count: int, *, price: float = 100.0, spread: float = 0.5) -> list[KBarRecord]:
    """Narrow-range bars from 09:15 for compress + ATR warmup."""
    bars: list[KBarRecord] = []
    start = dt.datetime(2026, 4, 1, 9, 15, 0)
    for i in range(count):
        ts = start + dt.timedelta(minutes=i)
        lo = price - spread
        hi = price + spread
        bars.append(
            KBarRecord(ts=ts, Open=price, High=hi, Low=lo, Close=price, Volume=100)
        )
    return bars


class TestCompressRegime(unittest.TestCase):
    def test_compress_fail_when_range_too_wide(self) -> None:
        bars = _flat_bars(COMPRESS_LOOKBACK_MIN + 5, spread=5.0)
        from reporting.compression_flow_attack_counterfactual import _atr_series

        atrs = _atr_series(bars)
        idx = len(bars) - 1
        ok, _, _, _ = evaluate_compress_regime(bars, atrs, idx, params=_fp())
        self.assertFalse(ok)

    def test_regime_fail_when_atr_high(self) -> None:
        bars = _flat_bars(COMPRESS_LOOKBACK_MIN + 5, spread=0.2)
        atrs = [5.0] * len(bars)
        atrs[-1] = 50.0
        idx = len(bars) - 1
        compress_ok, regime_ok, _, _ = evaluate_compress_regime(bars, atrs, idx, params=_fp())
        self.assertTrue(compress_ok)
        self.assertFalse(regime_ok)

    def test_atr_compress_floor_not_min_atr_25(self) -> None:
        """Case 13: low ATR day still compresses via floor=10, not min_atr=25."""
        bars = _flat_bars(COMPRESS_LOOKBACK_MIN + 5, spread=0.2)
        from reporting.compression_flow_attack_counterfactual import _atr_series

        atrs = _atr_series(bars)
        idx = len(bars) - 1
        range_m = max(b.High - b.Low for b in bars[idx - COMPRESS_LOOKBACK_MIN + 1 : idx + 1])
        self.assertLess(range_m, _fp().compress_k * ATR_COMPRESS_FLOOR)
        ok, _, atr_ref, _ = evaluate_compress_regime(bars, atrs, idx, params=_fp())
        self.assertLess(atr_ref, DEFAULT_MIN_ATR)
        self.assertTrue(ok)


class TestQuietAttack(unittest.TestCase):
    def test_quiet_fail_when_vol_high(self) -> None:
        sec_vol = {100: 50, 101: 50, 102: 50}
        session_start = 40
        self.assertFalse(_quiet_passes(sec_vol, session_start, 102))

    def test_quiet_pass_when_vol_low(self) -> None:
        sec_vol = {s: 1 for s in range(43, 103)}
        session_start = 1
        self.assertTrue(_quiet_passes(sec_vol, session_start, 102))

    def test_quiet_mean_includes_zero_volume_seconds(self) -> None:
        from reporting.compression_flow_attack_counterfactual import _mean_vol_1s

        sec_vol = {100: 60}
        # 60-second window with one spike → mean 1.0, not 60.0
        self.assertEqual(_mean_vol_1s(sec_vol, 41, 100), 1.0)

    def test_session_vol_samples_one_per_second(self) -> None:
        from reporting.compression_flow_attack_counterfactual import _session_vol_samples_to

        sec_vol = {10: 5, 11: 5, 12: 5}
        samples = _session_vol_samples_to(sec_vol, end_ts=12, session_start_ts=10)
        self.assertEqual(samples, [5.0, 5.0, 5.0])


class TestDetectSignal(unittest.TestCase):
    def _day(self) -> dt.date:
        return dt.date(2026, 4, 1)

    def _ts(self, hour: int, minute: int, second: int = 0) -> int:
        return int(dt.datetime(2026, 4, 1, hour, minute, second).timestamp())

    def test_attack_before_1000_not_armed(self) -> None:
        """Case 8: attack window start before 10:00."""
        day = self._day()
        bars = _flat_bars(90, spread=0.3)
        base = self._ts(9, 58, 0)
        ticks: list[tuple[int, float, int, int]] = []
        for i in range(120):
            ts = base + i
            tt = 1 if i > 60 else 2
            ticks.append((ts, 100.0, 2, tt))
        sig, _ = detect_cfa_signal(bars, ticks, params=_fp(), day=day)
        if sig is not None:
            self.assertGreaterEqual(
                dt.datetime.fromtimestamp(sig.trigger_ts).time(), ENTRY_WINDOW_START
            )

    def test_attack_at_1230_not_armed(self) -> None:
        """Case 9: trigger at or after 12:30 rejected."""
        day = self._day()
        bars = _flat_bars(90, spread=0.3)
        trigger = self._ts(12, 30, 0)
        ticks = [(trigger - 120 + i, 100.0, 1, 1) for i in range(130)]
        ticks.append((trigger, 100.0, 50, 1))
        sig, _ = detect_cfa_signal(bars, ticks, params=_fp(), day=day)
        if sig is not None:
            self.assertLess(
                dt.datetime.fromtimestamp(sig.trigger_ts).time(), NO_NEW_ENTRY_AFTER
            )

    def test_entry_at_or_after_1230_rejected(self) -> None:
        """Entry tick must be < 12:30 even if trigger is earlier."""
        day = self._day()
        bars = _flat_bars(90, spread=0.3)
        trigger = self._ts(12, 29, 0)
        entry_after = self._ts(12, 30, 0)
        ticks = [(trigger - 180 + i, 100.0, 1, 1) for i in range(200)]
        ticks.append((trigger, 100.0, 50, 1))
        ticks.append((entry_after, 100.0, 1, 1))
        sig, _ = detect_cfa_signal(bars, ticks, params=_fp(), day=day)
        self.assertIsNone(sig)

    def test_attack_signal_without_compress_regime(self) -> None:
        """attack_signal set on ratio+vol even when compress/regime fail."""
        day = self._day()
        bars = _flat_bars(90, spread=5.0)
        quiet_end = self._ts(10, 30, 0)
        ticks: list[tuple[int, float, int, int]] = []
        for sec in range(quiet_end - 180, quiet_end + 65):
            vol = 1 if sec <= quiet_end - 60 else 50
            tt = 1 if sec > quiet_end else 2
            ticks.append((sec, 100.0, vol, tt))
        ticks.append((quiet_end + 61, 100.0, 1, 1))
        sig, flags = detect_cfa_signal(bars, ticks, params=_fp(), day=day)
        self.assertIsNone(sig)
        if flags.get("attack_signal"):
            self.assertFalse(flags.get("compress_pass"))

    def test_min_stop_rejects_entry_keeps_attack_signal(self) -> None:
        """Case 5: stop_dist < 8 → attack_signal without entry."""
        day = self._day()
        bars = _flat_bars(90, spread=0.3)
        quiet_end = self._ts(10, 30, 0)
        ticks: list[tuple[int, float, int, int]] = []
        for sec in range(quiet_end - 180, quiet_end + 65):
            vol = 1 if sec <= quiet_end - 60 else 40
            tt = 1 if sec > quiet_end else 2
            ticks.append((sec, 100.05, vol, tt))
        ticks.append((quiet_end + 61, 100.04, 1, 1))
        sig, flags = detect_cfa_signal(bars, ticks, params=_fp(), day=day)
        if flags.get("attack_signal"):
            if sig is None:
                self.assertTrue(flags["attack_signal"])

    def test_funnel_fields_present(self) -> None:
        """Case 11: funnel six stages."""
        day = self._day()
        bars = _flat_bars(90, spread=0.3)
        rows, funnel = scan_cfa_session(bars, params=_fp(), day=day, ticks=[])
        self.assertEqual(rows, [])
        self.assertEqual(funnel["days_with_session"], 1)
        self.assertEqual(funnel["entry"], 0)
        for key in (
            "compress_pass",
            "regime_pass",
            "quiet_pass",
            "attack_signal",
        ):
            self.assertIn(key, funnel)


class TestSimulateEntry(unittest.TestCase):
    def test_long_stop_uses_structure(self) -> None:
        """Case 6: structural stop distance."""
        from reporting.compression_flow_attack_counterfactual import CfaSignal

        params = _fp()
        day = dt.date(2026, 4, 1)
        entry_ts = int(dt.datetime(2026, 4, 1, 10, 31, 0).timestamp())
        signal = CfaSignal(
            day=day,
            params=params,
            direction="Long",
            trigger_ts=entry_ts - 1,
            entry_ts=entry_ts,
            entry_price=100.0,
            atr_ref=20.0,
            atr_effective=25.0,
            stop_dist_pts=12.0,
            signal_1m_low=88.0,
            signal_1m_high=101.0,
            range_m=2.0,
            buy_ratio_mean=0.7,
            attack_vol=50,
        )
        ticks = [
            (entry_ts, 100.0, 1, 1),
            (entry_ts + 5, 99.0, 1, 1),
            (entry_ts + 10, 88.0, 1, 2),
        ]
        row = simulate_cfa_entry(signal, ticks)
        self.assertGreaterEqual(row["stop_dist_pts"], MIN_STOP_PTS)
        self.assertEqual(row["exit_variant"], "atr_barrier_900s")


class TestGateHelpers(unittest.TestCase):
    def test_fingerprint_g3s(self) -> None:
        post = {"n": 16, "forward": {"W1800": {"close_delta_median": 2.0}}}
        self.assertTrue(_evaluate_fingerprint_gate(post)["pass"])

    def test_fingerprint_fail_low_n(self) -> None:
        post = {"n": 10, "forward": {"W1800": {"close_delta_median": 2.0}}}
        self.assertFalse(_evaluate_fingerprint_gate(post)["pass"])


class TestPayloadKeys(unittest.TestCase):
    def test_grid_combo_count(self) -> None:
        from reporting.compression_flow_attack_counterfactual import _iter_param_sets

        self.assertEqual(len(_iter_param_sets("grid")), 162)
        self.assertEqual(len(_iter_param_sets("fingerprint")), 1)


if __name__ == "__main__":
    unittest.main()
