"""Book state owner: position + flight, engine forwarding."""

from __future__ import annotations

import unittest

from trading_engine.book import Book
from trading_engine.testing.helpers import make_host


class TestBook(unittest.TestCase):
    def test_clear_flight_and_position(self):
        b = Book()
        b.position_qty = 1
        b.position_dir = "Long"
        b.entry_price = 18000.0
        b.is_pending = True
        b.pending_intent = "exit"
        b.pending_order_id = "x1"
        b.clear_flight()
        self.assertFalse(b.is_pending)
        self.assertIsNone(b.pending_order_id)
        b.clear_position()
        self.assertEqual(b.position_qty, 0)
        self.assertEqual(b.position_dir, "Flat")

    def test_engine_forwards_book_fields(self):
        host = make_host()
        host.position_qty = 1
        host.position_dir = "Long"
        self.assertEqual(host._book.position_qty, 1)
        self.assertTrue(host.has_position)
        host.is_pending = True
        host.pending_intent = "entry"
        self.assertTrue(host._book.is_pending)
        host._book.reset_day_ops()
        host.block_new_entry = True
        host._book.reset_day_ops()
        self.assertFalse(host.block_new_entry)


if __name__ == "__main__":
    unittest.main()
