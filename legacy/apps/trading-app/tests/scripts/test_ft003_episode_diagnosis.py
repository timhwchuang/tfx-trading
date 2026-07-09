"""Tests for FT-003 entry diagnosis markdown merge."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from reporting.entry_funnel import merge_entry_into_markdown


class TestEntryDiagnosisMerge(unittest.TestCase):
    def test_merge_appends_multiple_agents(self) -> None:
        template = """# Test

## C. 進場漏斗（P0 — baseline valid log + tick）

（由 `ft003_episode_diagnosis.py` 填入）

---

## D. tail
"""
        with tempfile.TemporaryDirectory() as tmp:
            md = Path(tmp) / "VOLATILITY_BASELINE.md"
            md.write_text(template, encoding="utf-8")
            merge_entry_into_markdown(
                md,
                "**Agent / log / 區間**：`agent-a` / `a.log` / 2026-04-01～2026-04-30\n\n### C.1\n",
                agent="agent-a",
            )
            merge_entry_into_markdown(
                md,
                "**Agent / log / 區間**：`agent-b` / `b.log` / 2026-04-01～2026-04-30\n\n### C.1\n",
                agent="agent-b",
            )
            text = md.read_text(encoding="utf-8")
            self.assertIn("agent-a", text)
            self.assertIn("agent-b", text)
            self.assertEqual(text.count("**Agent / log / 區間**："), 2)

    def test_merge_inserts_section_when_missing(self) -> None:
        template = """## B. vol

---

## D. 出場診斷（P0 — baseline valid）

（由 `ft003_exit_diagnosis.py` 填入）

---

## E. tail
"""
        with tempfile.TemporaryDirectory() as tmp:
            md = Path(tmp) / "VOLATILITY_BASELINE.md"
            md.write_text(template, encoding="utf-8")
            merge_entry_into_markdown(
                md,
                "**Agent / log / 區間**：`agent-a` / `a.log` / 2026-04-01～2026-04-30\n",
                agent="agent-a",
            )
            text = md.read_text(encoding="utf-8")
            self.assertIn("## C. 進場漏斗", text)
            self.assertIn("agent-a", text)

    def test_merge_replaces_same_agent(self) -> None:
        template = """## C. 進場漏斗（P0 — baseline valid log + tick）

**Agent / log / 區間**：`agent-a` / `old.log` / 2026-04-01～2026-04-30

---

## D.
"""
        with tempfile.TemporaryDirectory() as tmp:
            md = Path(tmp) / "VOLATILITY_BASELINE.md"
            md.write_text(template, encoding="utf-8")
            merge_entry_into_markdown(
                md,
                "**Agent / log / 區間**：`agent-a` / `new.log` / 2026-04-01～2026-04-30\n",
                agent="agent-a",
            )
            text = md.read_text(encoding="utf-8")
            self.assertIn("new.log", text)
            self.assertNotIn("old.log", text)


if __name__ == "__main__":
    unittest.main()
