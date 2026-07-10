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

    def test_apply_entry_and_exit_leg(self):
        b = Book()
        b.apply_entry_fill(1, 18000.0, "Long", exchange_ts=1_000)
        self.assertEqual(b.position_qty, 1)
        self.assertEqual(b.position_dir, "Long")
        self.assertEqual(b.entry_price, 18000.0)
        self.assertEqual(b.trailing_peak, 18000.0)  # legacy seed
        self.assertEqual(b.entry_exchange_ts, 1_000)
        leg_qty, leg_pnl = b.apply_exit_leg(18010.0, 1)
        self.assertEqual(leg_qty, 1)
        self.assertEqual(leg_pnl, 10.0)
        self.assertEqual(b.position_qty, 0)
        self.assertEqual(b.daily_pnl, 10.0)
        snap = b.to_position_snapshot()
        self.assertFalse(snap.has_position)
        self.assertEqual(snap.qty, 0)

    def test_adopt_broker_position(self):
        b = Book()
        b.apply_entry_fill(1, 18000.0, "Long", exchange_ts=1)
        b.trailing_peak = 18050.0
        before, after = b.adopt_broker_position(
            1, "Long", 18005.0, preserve_peak=True
        )
        self.assertEqual((before, after), (1, 1))
        self.assertEqual(b.trailing_peak, 18050.0)
        self.assertEqual(b.entry_price, 18005.0)
        b.adopt_broker_position(0, "Flat")
        self.assertEqual(b.position_qty, 0)
        self.assertEqual(b.trailing_peak, 0.0)

    def test_set_qty_dir_flat_clears_metadata(self):
        b = Book()
        b.apply_entry_fill(1, 18000.0, "Long", exchange_ts=99)
        b.ticks_since_entry = 5
        b.set_qty_dir(0, "Flat")
        self.assertEqual(b.position_qty, 0)
        self.assertEqual(b.entry_price, 0.0)
        self.assertEqual(b.entry_exchange_ts, 0)
        self.assertEqual(b.ticks_since_entry, 0)

    def test_note_tick_while_held(self):
        b = Book()
        b.note_tick_while_held()
        self.assertEqual(b.ticks_since_entry, 0)
        b.apply_entry_fill(1, 18000.0, "Long", exchange_ts=1)
        b.note_tick_while_held()
        self.assertEqual(b.ticks_since_entry, 1)

    def test_engine_forwards_book_fields(self):
        host = make_host()
        host._book.position_qty = 1
        host._book.position_dir = "Long"
        self.assertEqual(host._book.position_qty, 1)
        self.assertTrue(host.has_position)
        host._book.is_pending = True
        host._book.pending_intent = "entry"
        self.assertTrue(host._book.is_pending)
        host._book.reset_day_ops()
        host._book.block_new_entry = True
        host._book.reset_day_ops()
        self.assertFalse(host._book.block_new_entry)
        snap = host._position_snapshot()
        self.assertTrue(snap.has_position)
        self.assertEqual(snap.qty, 1)


if __name__ == "__main__":
    unittest.main()
