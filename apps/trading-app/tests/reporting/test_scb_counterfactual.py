"""Tests for SCB counterfactual."""

from __future__ import annotations

import datetime as dt
import unittest

from reporting.orb_counterfactual import compute_opening_range
from reporting.scb_counterfactual import (
    BarCtx,
    _in_entry_window,
    _param_key,
    _vwap_slope_ok,
)
from storage.kbar_loader import KBarRecord


def _bar(hour: int, minute: int, *, o: float, h: float, low: float, c: float, vol: float = 200) -> KBarRecord:
    return KBarRecord(
        ts=dt.datetime(2025, 6, 2, hour, minute, 0),
        Open=o,
        High=h,
        Low=low,
        Close=c,
        Volume=vol,
    )


class TestScbWindows(unittest.TestCase):
    def test_morning_in_window(self) -> None:
        self.assertTrue(_in_entry_window(dt.time(9, 0)))

    def test_lunch_blocked(self) -> None:
        self.assertFalse(_in_entry_window(dt.time(12, 0)))

    def test_close_window(self) -> None:
        self.assertTrue(_in_entry_window(dt.time(13, 10)))


class TestScbParamKey(unittest.TestCase):
    def test_rm30(self) -> None:
        self.assertEqual(_param_key(30), "rm30")


class TestVwapSlope(unittest.TestCase):
    def test_strict_increase(self) -> None:
        contexts = [
            BarCtx(0, 0, dt.time(8, 45), 100, 100, 100, 100, 100.0, 25),
            BarCtx(1, 0, dt.time(8, 46), 100, 100, 100, 100, 100.5, 25),
            BarCtx(2, 0, dt.time(8, 47), 100, 100, 100, 100, 101.0, 25),
        ]
        self.assertTrue(_vwap_slope_ok(contexts, 2))


if __name__ == "__main__":
    unittest.main()
