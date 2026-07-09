"""Validation helpers: audit parsing, hashing, fill comparison."""

from __future__ import annotations

import datetime
import logging
import unittest
from unittest.mock import patch

from trading_engine.testing.defaults import default_runtime_config
from trading_engine.testing.helpers import StubStrategy

from trading_backtest.engine import BacktestEngine
from trading_backtest.loader import ReplayTick
from trading_backtest.validation import (
    AuditCaptureHandler,
    capture_backtest_audits,
    compare_fill_audits,
    format_fill_comparison,
    hash_audit_records,
    parse_audit_lines,
    parse_fill_audits,
    slippage_vs_limit_pts,
)


class TestValidationParsing(unittest.TestCase):
    def test_parse_fill_audits_from_log_lines(self):
        text = """
10:00:00 [INFO] FILL_AUDIT {"intent":"entry","direction":"Buy","fill_price":18000.5,"limit_price":18003.0}
10:00:01 [INFO] SIGNAL_AUDIT {"intent":"exit","direction":"Sell","price":18010.0}
10:00:02 [INFO] FILL_AUDIT {"intent":"exit","direction":"Sell","fill_price":18008.0,"limit_price":18007.0}
"""
        fills = parse_fill_audits(text)
        self.assertEqual(len(fills), 2)
        self.assertEqual(fills[0]["intent"], "entry")
        self.assertAlmostEqual(slippage_vs_limit_pts(fills[0]), -2.5)

    def test_hash_is_stable_for_same_payloads(self):
        records = [
            ("FILL_AUDIT", '{"intent":"entry","fill_price":1.0}'),
            ("DAILY_SUMMARY", '{"date":"2026-06-12"}'),
        ]
        h1 = hash_audit_records(records)
        h2 = hash_audit_records(records)
        self.assertEqual(h1, h2)

    def test_compare_fill_audits_warns_on_count_mismatch(self):
        bt = [{"direction": "Buy", "fill_price": 18000.0, "limit_price": 18003.0}]
        ref = []
        report = compare_fill_audits(bt, ref)
        self.assertEqual(report.count_delta, 1)
        self.assertTrue(any("reference log has zero" in w for w in report.warnings))
        text = format_fill_comparison(report)
        self.assertIn("backtest fills:  1", text)


class TestCaptureBacktestAudits(unittest.TestCase):
    def test_capture_audits_during_replay(self):
        ticks = [
            ReplayTick(datetime.datetime(2026, 6, 12, 9, 0, 0), 18000.0, 1, 0),
        ]
        engine = BacktestEngine(
            "TXFR1",
            [datetime.date(2026, 6, 12)],
            StubStrategy(),
            runtime_config=default_runtime_config(),
        )
        with patch("trading_backtest.loader.iter_replay_ticks", return_value=iter(ticks)):
            records = capture_backtest_audits(engine)
        labels = {label for label, _ in records}
        self.assertIn("DAILY_SUMMARY", labels)

    def test_audit_capture_handler_parses_prefix(self):
        handler = AuditCaptureHandler()
        record = logging.LogRecord(
            name="trading_engine",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg='FILL_AUDIT {"intent":"entry"}',
            args=(),
            exc_info=None,
        )
        handler.emit(record)
        self.assertEqual(handler.records, [("FILL_AUDIT", '{"intent":"entry"}')])

    def test_parse_audit_lines_ignores_non_audit(self):
        text = 'noise line\n10:00 [INFO] DAILY_SUMMARY {"date":"2026-06-12"}\n'
        records = parse_audit_lines(text)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0][0], "DAILY_SUMMARY")


if __name__ == "__main__":
    unittest.main()
