"""Tests for date slice resolution."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from reporting.date_slices import (
    DateRange,
    artifact_paths,
    day_in_date_range,
    resolve_date_range,
)


class TestDateSlices(unittest.TestCase):
    def test_default_uat_2m(self) -> None:
        r = resolve_date_range()
        self.assertEqual(r.label, "UAT_2m")
        self.assertEqual(r.from_date, "2026-05-01")
        self.assertEqual(r.to_date, "2026-06-30")

    def test_months_single(self) -> None:
        r = resolve_date_range(months=["2026-03"])
        self.assertEqual(r.label, "2026-03")
        self.assertEqual(r.from_date, "2026-03-01")
        self.assertEqual(r.to_date, "2026-03-31")
        self.assertEqual(r.months, ("2026-03",))

    def test_months_multi_label(self) -> None:
        r = resolve_date_range(months=["2025-11", "2026-03"])
        self.assertEqual(r.label, "months_2025-11_2026-03")
        self.assertEqual(r.from_date, "2025-11-01")
        self.assertEqual(r.to_date, "2026-03-31")

    def test_custom_from_to(self) -> None:
        r = resolve_date_range(from_date="2026-06-01", to_date="2026-06-15")
        self.assertTrue(r.label.startswith("custom_"))

    def test_from_without_to_raises(self) -> None:
        with self.assertRaises(ValueError):
            resolve_date_range(from_date="2026-06-01")

    def test_spot_check_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            cache = Path(d)
            for day in ("2026-03-01", "2026-04-01", "2025-11-01"):
                (cache / f"TMFR1_{day}.csv").write_text("x", encoding="utf-8")
            # Need min_days (15) files per month for spot pool — use 16 days for one month
            for i in range(1, 17):
                (cache / f"TMFR1_2026-03-{i:02d}.csv").write_text("x", encoding="utf-8")
            for i in range(1, 17):
                (cache / f"TMFR1_2026-04-{i:02d}.csv").write_text("x", encoding="utf-8")
            r1 = resolve_date_range(spot_check=1, spot_seed=7, cache_dir=cache)
            r2 = resolve_date_range(spot_check=1, spot_seed=7, cache_dir=cache)
            self.assertEqual(r1.months, r2.months)

    def test_day_in_date_range_months(self) -> None:
        dr = DateRange("x", "2025-05-01", "2026-02-28", months=("2025-05", "2026-02"))
        self.assertTrue(day_in_date_range("2025-05-08", dr))
        self.assertFalse(day_in_date_range("2025-12-01", dr))
        self.assertTrue(day_in_date_range("2026-02-25", dr))

    def test_artifact_paths(self) -> None:
        paths = artifact_paths(Path("/r"), Path("/l"), "UAT_2m")
        self.assertEqual(paths["execution_parity_json"].name, "execution_parity_UAT_2m.json")


if __name__ == "__main__":
    unittest.main()
