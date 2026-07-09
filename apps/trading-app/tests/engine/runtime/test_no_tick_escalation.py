"""No-tick watchdog escalation to session relogin."""

from __future__ import annotations

import datetime
import unittest
from dataclasses import replace
from unittest.mock import MagicMock

from trading_engine.core.runtime_config import RuntimeConfig
from trading_engine.testing.defaults import default_test_settings
from trading_engine.testing.helpers import make_host


class TestNoTickEscalation(unittest.TestCase):
    def _host(self, *, escalate_after: int = 3) -> object:
        base = replace(
            default_test_settings(),
            no_tick_resubscribe_escalate_after=escalate_after,
        )
        host = make_host()
        host._cfg = RuntimeConfig(base)
        host.contract = MagicMock(code="TMFR1")
        host._api_connected = True
        host._last_tick_exchange_dt = datetime.datetime(2026, 6, 23, 10, 0, 0)
        host._wall = 1_000.0
        host._clock = lambda: host._wall
        host._last_tick_wall_time = host._wall - 120
        host._last_no_tick_resubscribe_wall = 0.0
        host._resubscribe_ticks = MagicMock()
        host._alerts = MagicMock()
        host._mark_disconnected = MagicMock(wraps=host._mark_disconnected)
        return host

    def test_escalates_after_threshold_resubscribes(self) -> None:
        host = self._host(escalate_after=3)
        telemetry = MagicMock()
        host._telemetry = telemetry

        for _ in range(3):
            host._check_no_tick_watchdog()
            host._wall += 61

        host._mark_disconnected.assert_called_once()
        telemetry.record_no_tick_escalation.assert_called_once()
        host._alerts.send.assert_called_once()
        self.assertEqual(host._no_tick_resubscribe_streak, 0)

    def test_below_threshold_only_resubscribes(self) -> None:
        host = self._host(escalate_after=3)

        host._check_no_tick_watchdog()

        host._resubscribe_ticks.assert_called_once()
        host._mark_disconnected.assert_not_called()
        self.assertEqual(host._no_tick_resubscribe_streak, 1)

    def test_resubscribe_failure_marks_disconnected_immediately(self) -> None:
        host = self._host()
        host._resubscribe_ticks.side_effect = RuntimeError("subscribe failed")

        host._check_no_tick_watchdog()

        host._mark_disconnected.assert_called_once()
        self.assertEqual(host._no_tick_resubscribe_streak, 0)

    def test_tick_resets_streak(self) -> None:
        host = self._host()
        host._no_tick_resubscribe_streak = 2
        dt = datetime.datetime(2026, 6, 23, 10, 0, 1)

        host._record_tick_arrival(1_700_000_000, dt, 1)

        self.assertEqual(host._no_tick_resubscribe_streak, 0)

    def test_reconnect_clears_no_tick_streak(self) -> None:
        host = self._host()
        host._api_connected = False
        host._no_tick_resubscribe_streak = 2
        host.sync_positions = MagicMock()

        host._on_reconnected()

        self.assertEqual(host._no_tick_resubscribe_streak, 0)
        self.assertTrue(host._api_connected)

    def test_reconnect_during_resubscribe_cancels_escalation(self) -> None:
        host = self._host(escalate_after=3)
        host._no_tick_resubscribe_streak = 2

        def resubscribe_then_reconnect() -> None:
            host._no_tick_resubscribe_streak = 0
            host._connected_reconnect_generation += 1

        host._resubscribe_ticks = MagicMock(side_effect=resubscribe_then_reconnect)

        host._check_no_tick_watchdog()

        host._mark_disconnected.assert_not_called()
        host._alerts.send.assert_not_called()

    def test_tick_during_escalation_cancels_disconnect(self) -> None:
        host = self._host(escalate_after=1)
        host._no_tick_resubscribe_streak = 0
        host._last_tick_wall_time = host._wall - 120

        def resubscribe_then_tick() -> None:
            host._last_tick_wall_time = host._wall

        host._resubscribe_ticks = MagicMock(side_effect=resubscribe_then_tick)

        host._check_no_tick_watchdog()

        host._mark_disconnected.assert_not_called()
        host._alerts.send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
