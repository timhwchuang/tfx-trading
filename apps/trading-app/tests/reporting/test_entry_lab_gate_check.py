"""Tests for corpus gate check."""

from __future__ import annotations

import unittest

from reporting.entry_lab_config import SLUGS, baseline_path
from reporting.entry_lab_export import run_gate_check


class TestEntryLabGateCheck(unittest.TestCase):
    def test_gate_check_pass_when_n_matches(self) -> None:
        spec = SLUGS["gdc"]
        gate = run_gate_check(
            spec,
            "train",
            exported_n=79,
            baseline_path=baseline_path(spec, "train"),
        )
        self.assertEqual(gate["expected_n"], 79)
        self.assertTrue(gate["pass"])

    def test_gate_check_fail_on_mismatch(self) -> None:
        spec = SLUGS["gdc"]
        gate = run_gate_check(
            spec,
            "train",
            exported_n=78,
            baseline_path=baseline_path(spec, "train"),
        )
        self.assertFalse(gate["pass"])


if __name__ == "__main__":
    unittest.main()
