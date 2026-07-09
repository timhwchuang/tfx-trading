"""Tests for async logging flush/drain."""

from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path

from trading_engine.logging_setup import flush_async_logging, setup_async_logging, shutdown_async_logging


class TestLoggingSetup(unittest.TestCase):
    def tearDown(self) -> None:
        shutdown_async_logging()

    def test_flush_async_logging_writes_queued_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "async.log"
            setup_async_logging(level="INFO", log_file=str(path))
            logging.getLogger("trading_engine").info("queued-marker")
            flush_async_logging()
            self.assertIn("queued-marker", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
