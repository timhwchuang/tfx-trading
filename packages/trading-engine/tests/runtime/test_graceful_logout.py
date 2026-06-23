"""Graceful shutdown when API session is already dead."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from trading_engine.testing.helpers import make_host


class TestGracefulLogout(unittest.TestCase):
    def test_run_logout_session_error_does_not_raise(self) -> None:
        host = make_host()
        host.contract = MagicMock(code="TMFR1")
        host._order_sync_mode = True
        host.api.logout = MagicMock(
            side_effect=RuntimeError(
                "logout: Shioaji error Session error code: NotReady "
                "SessionNotEstablished"
            )
        )

        with (
            patch("trading_engine.engine.time.sleep", side_effect=KeyboardInterrupt),
            patch.object(host, "_start_order_worker"),
            patch("trading_engine.engine.threading.Thread"),
            patch("trading_engine.engine.shutdown_async_logging"),
        ):
            host.run()

        host.api.logout.assert_called_once()


if __name__ == "__main__":
    unittest.main()
