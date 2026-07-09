"""FT-003: sweep overlay key normalization and read paths (A/B class)."""

from __future__ import annotations

import unittest

from trading_engine.core.runtime_config import RuntimeConfig
from trading_engine.testing.defaults import default_test_settings


class TestOverlayKeys(unittest.TestCase):
    def test_a_class_min_atr_threshold_via_live_get(self):
        cfg = RuntimeConfig(default_test_settings())
        saved = cfg.apply_overlay({"min_atr_threshold": 36.0})
        try:
            self.assertEqual(
                cfg.live_get("MIN_ATR_THRESHOLD", cfg.min_atr_threshold),
                36.0,
            )
        finally:
            cfg.restore_overlay(saved)

    def test_b_class_ioc_slippage_via_getattr(self):
        cfg = RuntimeConfig(default_test_settings())
        base = cfg.ioc_slippage_points
        saved = cfg.apply_overlay({"ioc_slippage_points": 5})
        try:
            self.assertEqual(cfg.ioc_slippage_points, 5)
            self.assertEqual(cfg.pending_timeout_sec, cfg._base.pending_timeout_sec)
        finally:
            cfg.restore_overlay(saved)
        self.assertEqual(cfg.ioc_slippage_points, base)

    def test_b_class_momentum_vol_1s_via_getattr(self):
        cfg = RuntimeConfig(default_test_settings())
        saved = cfg.apply_overlay({"momentum_vol_1s": 200})
        try:
            self.assertEqual(cfg.momentum_vol_1s, 200)
        finally:
            cfg.restore_overlay(saved)

    def test_apply_overlay_rejects_unknown_key(self):
        cfg = RuntimeConfig(default_test_settings())
        with self.assertRaises(ValueError) as ctx:
            cfg.apply_overlay({"not_a_real_param": 1})
        self.assertIn("unknown overlay key", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
