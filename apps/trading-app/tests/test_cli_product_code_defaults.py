"""CLI --code defaults must follow config.product_code (微台 TMFR1)."""

from __future__ import annotations

import unittest

import config
from backtest.__main__ import build_parser as backtest_build_parser
from config import DEFAULT_PRODUCT_CODE, PRODUCT_CODE, settings
from reporting.calibration_cli import build_parser as calibration_build_parser
from reporting.structure_calibration_cli import (
    build_parser as structure_calibration_build_parser,
)
from sweep.determinism_check import build_parser as determinism_build_parser


class TestCliProductCodeDefaults(unittest.TestCase):
    def test_config_exports_default_product_code(self):
        self.assertIn("DEFAULT_PRODUCT_CODE", config.__all__)
        self.assertIn("PRODUCT_CODE", config.__all__)
        self.assertEqual(config.DEFAULT_PRODUCT_CODE, "TMFR1")
        self.assertEqual(PRODUCT_CODE, settings.product_code)

    def test_cli_code_defaults_match_product_code(self):
        cases = [
            (
                "backtest",
                backtest_build_parser(),
                ["--dates-from-cache"],
            ),
            (
                "calibration_cli",
                calibration_build_parser(),
                ["logs/uat.log", "--dates", "2026-06-22"],
            ),
            (
                "structure_calibration_cli",
                structure_calibration_build_parser(),
                ["logs/uat.log", "--dates", "2026-06-22"],
            ),
            (
                "determinism_check",
                determinism_build_parser(),
                ["--date", "2026-06-22"],
            ),
        ]
        for name, parser, argv in cases:
            with self.subTest(cli=name):
                args = parser.parse_args(argv)
                self.assertEqual(args.code, PRODUCT_CODE)


if __name__ == "__main__":
    unittest.main()
