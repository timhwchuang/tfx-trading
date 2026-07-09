"""Tests for FT-003 volatility baseline."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from reporting.volatility_baseline import (
    atr_series_from_bars,
    build_baseline_payload,
    compute_kbar_month_stats,
    inject_markdown_section,
    load_kbar_rows,
    preserve_markdown_section,
    threshold_percentile,
)


class TestVolatilityBaseline(unittest.TestCase):
    def test_load_kbar_rows_range_and_volume(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "TMFR1_kbars_2026-01-02.csv"
            with p.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["ts", "Open", "High", "Low", "Close", "Volume"])
                w.writerow(["2026-01-02T08:46:00", 100.0, 110.0, 90.0, 105.0, 10])
                w.writerow(["2026-01-02T08:47:00", 105.0, 120.0, 100.0, 115.0, 12])
            rows = load_kbar_rows(p)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0][3], 20.0)
            self.assertEqual(rows[0][4], 10.0)

    def test_atr_series_constant_range(self):
        bars = [(110.0, 95.0, 100.0, 15.0, 1.0)] * 5
        atrs = atr_series_from_bars(bars, period=2)
        self.assertEqual(len(atrs), 3)
        self.assertAlmostEqual(atrs[-1], 15.0)

    def test_atr_series_matches_engine_last_window(self):
        bars = [
            (110.0, 95.0, 100.0, 15.0, 1.0),
            (112.0, 97.0, 105.0, 15.0, 1.0),
            (115.0, 100.0, 110.0, 15.0, 1.0),
            (118.0, 103.0, 115.0, 15.0, 1.0),
        ]
        period = 2
        trs = []
        for i in range(1, len(bars)):
            h, l = bars[i][0], bars[i][1]
            prev_c = bars[i - 1][2]
            trs.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
        expected = sum(trs[-period:]) / period
        self.assertAlmostEqual(atr_series_from_bars(bars, period=period)[-1], expected)

    def test_compute_kbar_month_stats_ratios_and_volume(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "TMFR1_kbars_2026-01-02.csv"
            with p.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["ts", "Open", "High", "Low", "Close", "Volume"])
                for i in range(25):
                    base = 100.0 + i
                    w.writerow(
                        [
                            f"2026-01-02T08:{46+i:02d}:00",
                            base,
                            base + 10,
                            base - 5,
                            base + 2,
                            100,
                        ]
                    )
            stats = compute_kbar_month_stats(
                [p], stop_points=6, trail_points=8, tp_points=20, atr_period=20
            )
            self.assertIn("2026-01", stats)
            month = stats["2026-01"]
            ratios = month["ratios"]
            self.assertGreater(ratios["stop_ratio"], 0)
            self.assertEqual(month["volume_1m"]["count"], 25)

    def test_threshold_percentile(self):
        samples = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        self.assertEqual(threshold_percentile(5, samples), 50.0)
        self.assertEqual(threshold_percentile(150, samples), 100.0)

    def test_build_payload_threshold_coverage(self):
        tick_months = {
            "2026-01": {
                "role": "train_or_diagnostic",
                "vol_1s": {"p50": 3},
                "spread": {"p50": 2},
                "_vol_1s_samples": [1, 2, 3, 4, 5],
            }
        }
        payload = build_baseline_payload(
            code="TMFR1",
            from_date="2026-01-01",
            to_date="2026-01-31",
            config={"momentum_vol_1s": 3, "exhaustion_vol": 2, "hard_stop_points": 6},
            kbar_months={},
            tick_months=tick_months,
        )
        tc = payload["threshold_coverage"]
        self.assertEqual(tc["momentum_vol_1s"]["pct_samples_lte"], 60.0)
        self.assertEqual(tc["momentum_vol_1s"]["pct_samples_gte"], 60.0)
        self.assertEqual(payload["atr_method"], "sma_tr")
        self.assertEqual(payload["months_role"]["2026-01"], "train_or_diagnostic")
        month = payload["tick_months"]["2026-01"]
        self.assertIn("threshold_coverage", month)
        self.assertEqual(month["threshold_coverage"]["momentum_vol_1s_pct_gte"], 60.0)

    def test_inject_markdown_section_no_duplicate_divider(self):
        base = "## D. 出場診斷（P0 — baseline valid）\n\nplaceholder\n\n---\n\n## E. tail\n"
        preserved = preserve_markdown_section(base, "D. 出場診斷（P0 — baseline valid）")
        self.assertIsNotNone(preserved)
        merged = inject_markdown_section(base, "D. 出場診斷（P0 — baseline valid）", preserved + "\n\nextra")
        self.assertEqual(merged.count("\n---\n"), 1)


if __name__ == "__main__":
    unittest.main()
