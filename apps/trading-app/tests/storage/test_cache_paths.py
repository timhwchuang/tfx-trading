"""P1: single canonical tick_cache path for storage loaders."""

from __future__ import annotations

import unittest

from storage.cache_paths import (
    DEFAULT_REPORTS_DIR,
    DEFAULT_TICK_CACHE_DIR,
    _MONOREPO_ROOT,
)
from storage.tick_loader import DEFAULT_CACHE_DIR


class TestCachePathsUnified(unittest.TestCase):
    def test_tick_loader_and_cache_paths_match(self):
        self.assertEqual(DEFAULT_CACHE_DIR, DEFAULT_TICK_CACHE_DIR)
        self.assertTrue(DEFAULT_TICK_CACHE_DIR.name == "tick_cache")
        self.assertTrue(DEFAULT_TICK_CACHE_DIR.is_absolute())
        self.assertEqual(DEFAULT_TICK_CACHE_DIR.parent, _MONOREPO_ROOT)
        self.assertEqual(DEFAULT_REPORTS_DIR.parent, _MONOREPO_ROOT)


if __name__ == "__main__":
    unittest.main()
