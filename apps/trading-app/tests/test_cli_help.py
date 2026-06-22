"""Tests for cli_help catalog."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from cli_help import (
    CATALOG,
    _SRC_DIR,
    _subprocess_env,
    format_catalog,
    main,
    parse_spec_cli_modules,
    run_module_help,
)


class TestCliHelp(unittest.TestCase):
    def test_catalog_lists_core_modules(self):
        modules = {e.module for e in CATALOG}
        self.assertIn("reporting", modules)
        self.assertIn("sweep.pilot_gate_check", modules)
        self.assertIn("reporting.uat_evidence_export", modules)
        self.assertIn("backfilldata", modules)

    def test_catalog_matches_spec_cli_table(self):
        catalog_modules = {e.module for e in CATALOG}
        self.assertEqual(catalog_modules, parse_spec_cli_modules())

    def test_parse_spec_cli_modules_cli_section_only(self):
        import tempfile
        from pathlib import Path

        spec = (
            "## CLI (from `src/`)\n\n"
            "| Command | Purpose |\n"
            "|---------|--------|\n"
            "| `python -m live` | Live |\n"
            "| `python -m backtest` | Backtest |\n\n"
            "## Integration contracts\n\n"
            "Prose `python -m fake.prose_module` must not be counted.\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(spec)
            path = Path(f.name)
        try:
            self.assertEqual(parse_spec_cli_modules(path), frozenset({"live", "backtest"}))
        finally:
            path.unlink()

    def test_format_catalog_mentions_help(self):
        text = format_catalog()
        self.assertIn("python -m reporting --help", text)
        self.assertIn("cli_help", text)

    def test_main_unknown_module(self):
        self.assertEqual(main(["no-such-module"]), 1)

    def test_main_prints_catalog(self):
        self.assertEqual(main([]), 0)

    def test_subprocess_env_includes_src_and_siblings(self):
        env = _subprocess_env()
        parts = env["PYTHONPATH"].split(os.pathsep)
        self.assertIn(str(_SRC_DIR), parts)
        monorepo = _SRC_DIR.parent.parent.parent
        engine_src = monorepo / "packages/trading-engine/src"
        if engine_src.is_dir():
            self.assertIn(str(engine_src), parts)

    @patch("cli_help.subprocess.run")
    def test_delegate_calls_subprocess_with_cwd_and_env(self, mock_run):
        mock_run.return_value.returncode = 0
        self.assertEqual(run_module_help("reporting"), 0)
        mock_run.assert_called_once()
        _args, kwargs = mock_run.call_args
        self.assertEqual(kwargs["cwd"], _SRC_DIR)
        env = kwargs["env"]
        self.assertIn(str(_SRC_DIR), env["PYTHONPATH"].split(os.pathsep))

    def test_main_reporting_delegate(self):
        self.assertEqual(main(["reporting"]), 0)

    def test_live_help_without_shioaji_import(self):
        sys.modules.pop("live.__main__", None)
        mods_before = set(sys.modules)
        from live.__main__ import main as live_main

        self.assertNotIn("shioaji", set(sys.modules) - mods_before)
        with self.assertRaises(SystemExit) as ctx:
            live_main(["--help"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertNotIn("shioaji", set(sys.modules) - mods_before)


if __name__ == "__main__":
    unittest.main()