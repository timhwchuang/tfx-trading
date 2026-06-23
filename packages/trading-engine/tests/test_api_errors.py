"""Tests for api_errors.is_api_session_error."""

from __future__ import annotations

import unittest

from trading_engine.api_errors import is_api_session_error


class TestApiSessionErrors(unittest.TestCase):
    def test_session_not_established(self) -> None:
        exc = RuntimeError(
            'Shioaji error Session error SolClient send request api/v1/data/kbars, '
            'code: NotReady, Error ErrorInfo { sub_code: SubCode(SessionNotEstablished), '
            'error_str: "Unable to wait for session \'(c0,s1)_sinopac\' to be established" }'
        )
        self.assertTrue(is_api_session_error(exc))

    def test_shioaji_connection_error_class_name(self) -> None:
        class ShioajiConnectionError(Exception):
            pass

        self.assertTrue(is_api_session_error(ShioajiConnectionError("logout failed")))

    def test_generic_kbars_error_not_session(self) -> None:
        self.assertFalse(is_api_session_error(RuntimeError("kbars empty response")))

    def test_timeout_not_session(self) -> None:
        self.assertFalse(is_api_session_error(TimeoutError("connection timed out")))


if __name__ == "__main__":
    unittest.main()
