"""FT-002: structure vs trend filter mutual exclusion in RuntimeConfig overlay."""

from __future__ import annotations

import unittest

from trading_engine.core.runtime_config import RuntimeConfig
from trading_engine.testing.defaults import default_test_settings


class TestRegimeMutualExclusion(unittest.TestCase):
    def test_apply_overlay_rejects_both_filters(self):
        cfg = RuntimeConfig(default_test_settings())
        with self.assertRaises(ValueError):
            cfg.apply_overlay(
                {
                    "structure_filter_enabled": True,
                    "trend_filter_enabled": True,
                }
            )


if __name__ == "__main__":
    unittest.main()