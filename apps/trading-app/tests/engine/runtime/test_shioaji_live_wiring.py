"""P0-1: ShioajiLiveBootstrap re-attachable trade report channel."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from trading_engine.adapters.shioaji_live import ShioajiLiveBootstrap


def _make_engine() -> MagicMock:
    engine = MagicMock()
    # _api_lock must be a usable context manager.
    engine._api_lock = MagicMock()
    engine._api_lock.__enter__ = MagicMock(return_value=None)
    engine._api_lock.__exit__ = MagicMock(return_value=False)
    return engine


class TestShioajiLiveWiring(unittest.TestCase):
    def test_attach_registers_both_resubscribe_hooks(self):
        engine = _make_engine()
        boot = ShioajiLiveBootstrap(engine)

        boot.attach()

        self.assertEqual(engine._resubscribe_ticks, boot.subscribe_tick)
        self.assertEqual(engine._resubscribe_trade, boot.resubscribe_trade)

    def test_resubscribe_trade_reattaches_order_callback(self):
        engine = _make_engine()
        engine.api.futopt_account = MagicMock()
        boot = ShioajiLiveBootstrap(engine)

        boot.resubscribe_trade()

        engine.api.subscribe_trade.assert_called_once_with(engine.api.futopt_account)
        engine.api.set_order_callback.assert_called_once_with(engine.handle_order_event)

    def test_resubscribe_trade_without_account_raises(self):
        engine = _make_engine()
        engine.api.futopt_account = None
        boot = ShioajiLiveBootstrap(engine)

        with self.assertRaises(RuntimeError):
            boot.resubscribe_trade()

        engine.api.subscribe_trade.assert_not_called()
        engine.api.set_order_callback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
