"""FT-003: holdout date sealing for sweep/backtest."""

from __future__ import annotations

import datetime
import os
import unittest
from unittest.mock import patch

from sweep.holdout_guard import assert_dates_unsealed


class TestHoldoutGuard(unittest.TestCase):
    def test_blocks_may_dates_by_default(self):
        with self.assertRaises(RuntimeError) as ctx:
            assert_dates_unsealed([datetime.date(2026, 5, 15)])
        self.assertIn("holdout dates sealed", str(ctx.exception))

    def test_allows_april_dates(self):
        assert_dates_unsealed([datetime.date(2026, 4, 1), datetime.date(2026, 3, 2)])

    def test_unseal_env_allows_may(self):
        with patch.dict(os.environ, {"FT003_HOLDOUT_UNSEAL": "1"}):
            assert_dates_unsealed([datetime.date(2026, 5, 15)])


if __name__ == "__main__":
    unittest.main()
