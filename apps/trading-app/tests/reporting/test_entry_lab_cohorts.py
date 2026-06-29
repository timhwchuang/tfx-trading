"""Tests for entry_lab_cohorts."""

from __future__ import annotations

import unittest

from reporting.entry_lab_cohorts import (
    attach_derived,
    bootstrap_median_ci,
    filter_intersection_matrix,
    sample_tier,
    summarize_cohort,
)


def _row(w30: float, gross: float, net: float | None = None) -> dict:
    return {
        "post_entry_forward": {
            "W300": {"close_delta": w30 + 1},
            "W900": {"close_delta": w30},
            "W1800": {"close_delta": w30},
        },
        "gross_atr_sim": gross,
        "net_atr_sim": net if net is not None else gross - 5,
        "atr_barrier_sim": {"mfe": gross + 10, "mae": 5, "exit_reason": "tp"},
    }


class TestEntryLabCohorts(unittest.TestCase):
    def test_sample_tier(self) -> None:
        self.assertEqual(sample_tier(35), "descriptive_ci")
        self.assertEqual(sample_tier(20), "descriptive_only")
        self.assertEqual(sample_tier(12), "hypothesis_only")

    def test_summarize_cohort_bootstrap(self) -> None:
        rows = [_row(2.0, 3.0) for _ in range(40)]
        attach_derived(rows)
        s = summarize_cohort(rows)
        self.assertEqual(s["n"], 40)
        self.assertEqual(s["tier"], "descriptive_ci")
        self.assertIn("w30_bootstrap_ci", s["path"])

    def test_bootstrap_reproducible(self) -> None:
        vals = [1.0, 2.0, 3.0, 4.0, 5.0]
        a = bootstrap_median_ci(vals, n_resamples=500, seed=42)
        b = bootstrap_median_ci(vals, n_resamples=500, seed=42)
        self.assertEqual(a, b)

    def test_intersection_jaccard(self) -> None:
        filters = {
            "a": {("2025-01-02", 100)},
            "b": {("2025-01-02", 100)},
        }
        m = filter_intersection_matrix(filters)
        self.assertEqual(m["jaccard"]["a"]["b"], 1.0)


if __name__ == "__main__":
    unittest.main()
