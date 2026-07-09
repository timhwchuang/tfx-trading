"""Tests for order error classification and session watchdog."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from trading_engine.core.types import OrderSignal
from trading_engine.engine import AtrRefreshResult, ReconnectOutcome
from trading_engine.order_errors import (
    OrderErrorCategory,
    classify_order_error,
    should_retry_order,
)
from trading_engine.testing.helpers import arm_pending_exit, make_host


class TestOrderErrors(unittest.TestCase):
    def test_classify_retryable_timeout(self):
        self.assertEqual(
            classify_order_error(TimeoutError("connection timed out")),
            OrderErrorCategory.RETRYABLE,
        )

    def test_classify_fatal_balance(self):
        self.assertEqual(
            classify_order_error(RuntimeError("insufficient margin balance")),
            OrderErrorCategory.FATAL,
        )

    def test_exit_retry_policy(self):
        self.assertTrue(
            should_retry_order(
                intent="exit",
                category=OrderErrorCategory.RETRYABLE,
                attempt=0,
                max_retries=3,
            )
        )
        self.assertFalse(
            should_retry_order(
                intent="entry",
                category=OrderErrorCategory.RETRYABLE,
                attempt=0,
                max_retries=3,
            )
        )


class TestLiveGuards(unittest.TestCase):
    def test_entry_failure_clears_pending(self):
        host = make_host()
        host.contract = MagicMock(code="TXFR1")
        host.api.futopt_account = MagicMock()
        host.api.place_order.side_effect = TimeoutError("timeout")
        host.is_pending = True
        host.pending_intent = "entry"

        host.place_order(OrderSignal("Buy", 1, 18000.0, "entry", exchange_ts=100))
        self.assertFalse(host.is_pending)

    def test_exit_failure_keeps_pending_and_schedules_retry(self):
        host = make_host()
        host.contract = MagicMock(code="TXFR1")
        host.api.futopt_account = MagicMock()
        host.api.place_order.side_effect = TimeoutError("timeout")
        arm_pending_exit(host)

        host.place_order(OrderSignal("Sell", 1, 18000.0, "exit", exchange_ts=200))
        self.assertTrue(host.is_pending)
        self.assertGreater(host._exit_order_retry_at, 0)

    def test_session_watchdog_triggers_relogin(self):
        host = make_host()
        host._api_connected = False
        host._disconnect_since = host._clock() - 60
        host._session_relogin_attempts = 0
        host._next_relogin_at = 0
        host.contract = MagicMock(code="TXFR1")
        host.api.login = MagicMock()
        host._on_reconnected = MagicMock()

        host._check_session_watchdog()
        host.api.login.assert_called_once()
        host._on_reconnected.assert_called_once()

    def test_session_watchdog_unhealthy_reconnect_increments_attempts(self):
        host = make_host()
        host._api_connected = False
        host._disconnect_since = host._clock() - 60
        host._session_relogin_attempts = 0
        host._next_relogin_at = 0
        host.contract = MagicMock(code="TXFR1")
        host.api.login = MagicMock()
        host.sync_positions = MagicMock()
        host._resubscribe_ticks = MagicMock()
        host.refresh_atr = MagicMock(return_value=AtrRefreshResult(False, True))
        host._alerts = MagicMock()

        host._check_session_watchdog()

        host.api.login.assert_called_once()
        self.assertEqual(host._session_relogin_attempts, 1)
        self.assertGreater(host._next_relogin_at, 0)
        self.assertFalse(host._api_connected)
        host._alerts.send.assert_called()

    def test_session_watchdog_stale_reconnect_does_not_increment_attempts(self):
        host = make_host()
        host._api_connected = False
        host._disconnect_since = host._clock() - 60
        host._session_relogin_attempts = 0
        host._next_relogin_at = 0
        host.contract = MagicMock(code="TXFR1")
        host.api.login = MagicMock()
        host._on_reconnected = MagicMock(return_value=ReconnectOutcome.STALE)

        host._check_session_watchdog()

        host.api.login.assert_called_once()
        self.assertEqual(host._session_relogin_attempts, 0)

    def test_session_watchdog_stale_reconnect_applies_short_backoff(self):
        host = make_host()
        host._api_connected = False
        host._disconnect_since = host._clock() - 60
        host._session_relogin_attempts = 0
        host._next_relogin_at = 0
        host.contract = MagicMock(code="TXFR1")
        host.api.login = MagicMock()
        host._on_reconnected = MagicMock(return_value=ReconnectOutcome.STALE)
        now = host._clock()

        host._check_session_watchdog()

        host.api.login.assert_called_once()
        self.assertEqual(host._session_relogin_attempts, 0)
        self.assertGreater(host._next_relogin_at, now)

    def test_session_watchdog_skips_reconnect_when_already_connected(self):
        host = make_host()
        host._api_connected = False
        host._disconnect_since = host._clock() - 60
        host._session_relogin_attempts = 0
        host._next_relogin_at = 0
        host.contract = MagicMock(code="TXFR1")

        def login_then_connected(*_args, **_kwargs):
            host._api_connected = True

        host.api.login = MagicMock(side_effect=login_then_connected)
        host._on_reconnected = MagicMock()

        host._check_session_watchdog()

        host.api.login.assert_called_once()
        host._on_reconnected.assert_not_called()


if __name__ == "__main__":
    unittest.main()
