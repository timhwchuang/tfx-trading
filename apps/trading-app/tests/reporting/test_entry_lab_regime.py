"""Tests for entry_lab_regime lookahead guard."""

from __future__ import annotations

import datetime as dt
import unittest

from reporting.entry_lab_regime import compute_alignment, regime_snapshot_for_entry
from storage.kbar_loader import KBarRecord


def _bar(h: int, m: int, o: float, hi: float, lo: float, c: float) -> KBarRecord:
    ts = dt.datetime(2025, 6, 2, h, m)
    return KBarRecord(ts=ts, Open=o, High=hi, Low=lo, Close=c, Volume=100)


class TestEntryLabRegime(unittest.TestCase):
    def test_structure_uses_only_closed_bars_as_of_entry(self) -> None:
        bars = [
            _bar(8, 45, 100, 105, 99, 104),
            _bar(8, 46, 104, 108, 103, 107),
            _bar(8, 47, 107, 110, 106, 109),
        ]
        entry_ts = int(bars[1].ts.timestamp())
        snap = regime_snapshot_for_entry(bars, entry_ts=entry_ts, atr=10.0)
        self.assertIn("structure_bias", snap)
        self.assertIn(snap["trend_dir"], ("Long", "Short", "Flat"))

    def test_alignment_flat_trend_is_neutral(self) -> None:
        row = {"direction": "Long"}
        regime = {"trend_dir": "Flat", "structure_bias": "Neutral"}
        al = compute_alignment(row, regime)
        self.assertEqual(al["r1"], "neutral")

    def test_enrich_uses_multi_day_kbar_range(self) -> None:
        from unittest.mock import patch

        from reporting.entry_lab_regime import enrich_rows_with_regime

        rows = [{"day": "2025-06-02", "ts": 1748822400, "direction": "Long", "atr": 10.0}]
        with patch("reporting.entry_lab_regime.iter_kbars_in_range", return_value=[]) as mock_iter:
            enrich_rows_with_regime(rows, code="TMFR1", cache_dir="/tmp/cache")
        args = mock_iter.call_args[0]
        self.assertEqual(args[0], "TMFR1")
        self.assertEqual(args[2], dt.date(2025, 6, 2))
        self.assertLessEqual(args[1], dt.date(2025, 5, 26))

    def test_alignment_counter_trend(self) -> None:
        row = {"direction": "Long"}
        regime = {
            "trend_dir": "Short",
            "structure_bias": "Short",
            "in_discount": False,
            "in_premium": True,
        }
        al = compute_alignment(row, regime)
        self.assertEqual(al["r1"], "counter_trend")


if __name__ == "__main__":
    unittest.main()
