"""Tests for deprecated kbar_cache/ migration helpers."""

from __future__ import annotations

import datetime
import tempfile
import time
import unittest
from pathlib import Path

from storage.kbar_loader import KBarRecord, kbar_path, save_kbars_csv
from storage.legacy_cache_migrate import (
    LEGACY_KBAR_CACHE_DIR,
    _should_copy_legacy,
    ensure_legacy_kbars_migrated,
    legacy_kbar_cache_present,
    migrate_legacy_kbar_cache,
)


class TestLegacyCacheMigrate(unittest.TestCase):
    def test_migrate_copies_newer_legacy_files(self):
        day = datetime.date(2026, 6, 22)
        bar = KBarRecord(
            ts=datetime.datetime(2026, 6, 22, 9, 0),
            Open=100.0,
            High=101.0,
            Low=99.0,
            Close=100.5,
            Volume=10,
        )
        with tempfile.TemporaryDirectory() as legacy_root, tempfile.TemporaryDirectory() as tick_root:
            legacy = Path(legacy_root) / "kbar_cache"
            tick = Path(tick_root)
            legacy.mkdir()
            save_kbars_csv([bar], legacy / "TMFR1_kbars_2026-06-22.csv")

            original = LEGACY_KBAR_CACHE_DIR
            try:
                import storage.legacy_cache_migrate as mod

                mod.LEGACY_KBAR_CACHE_DIR = legacy
                self.assertTrue(legacy_kbar_cache_present())
                n = migrate_legacy_kbar_cache(tick)
                self.assertEqual(n, 1)
                self.assertTrue(kbar_path(tick, "TMFR1", day).is_file())
            finally:
                mod.LEGACY_KBAR_CACHE_DIR = original

    def test_should_copy_legacy_skips_larger_but_older_destination(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            src = root / "legacy.csv"
            dst = root / "tick.csv"
            src.write_text("x" * 500, encoding="utf-8")
            dst.write_text("y", encoding="utf-8")
            now = time.time()
            Path(dst).touch()
            time.sleep(0.02)
            Path(src).touch()
            # dst is newer (touched last after sleep setup - fix order)
            # Make dst newer explicitly
            past = now - 100
            import os

            os.utime(src, (past, past))
            os.utime(dst, (now, now))
            self.assertFalse(_should_copy_legacy(src, dst))

    def test_ensure_legacy_kbars_migrated_auto_copies(self):
        day = datetime.date(2026, 6, 22)
        bar = KBarRecord(
            ts=datetime.datetime(2026, 6, 22, 9, 0),
            Open=1.0,
            High=1.0,
            Low=1.0,
            Close=1.0,
            Volume=1,
        )
        with tempfile.TemporaryDirectory() as legacy_root, tempfile.TemporaryDirectory() as tick_root:
            legacy = Path(legacy_root) / "kbar_cache"
            tick = Path(tick_root)
            legacy.mkdir()
            save_kbars_csv([bar], legacy / "TMFR1_kbars_2026-06-22.csv")

            import storage.legacy_cache_migrate as mod

            original = LEGACY_KBAR_CACHE_DIR
            try:
                mod.LEGACY_KBAR_CACHE_DIR = legacy
                n = ensure_legacy_kbars_migrated(tick)
                self.assertEqual(n, 1)
                self.assertTrue(kbar_path(tick, "TMFR1", day).is_file())
            finally:
                mod.LEGACY_KBAR_CACHE_DIR = original


if __name__ == "__main__":
    unittest.main()
