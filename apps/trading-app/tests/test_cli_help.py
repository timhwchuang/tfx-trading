"""Tests for cli_help catalog."""

from __future__ import annotations

import unittest

from cli_help import CATALOG, format_catalog, main


class TestCliHelp(unittest.TestCase):
    def test_catalog_lists_core_modules(self):
        modules = {e.module for e in CATALOG}
        self.assertIn("reporting", modules)
        self.assertIn("sweep.pilot_gate_check", modules)
        self.assertIn("reporting.uat_evidence_export", modules)

    def test_format_catalog_mentions_help(self):
        text = format_catalog()
        self.assertIn("python -m reporting --help", text)
        self.assertIn("cli_help", text)

    def test_main_unknown_module(self):
        self.assertEqual(main(["no-such-module"]), 1)

    def test_main_prints_catalog(self):
        self.assertEqual(main([]), 0)


if __name__ == "__main__":
    unittest.main()