"""Classify Shioaji / broker API session failures (no shioaji import in core)."""

from __future__ import annotations

import re

_SESSION_ERROR_PATTERNS = (
    r"sessionnotestablished",
    r"notready",
    r"session error",
    r"unable to wait for session",
    r"shioajiconnectionerror",
)


def is_api_session_error(exc: BaseException) -> bool:
    """True when the exception indicates Solace/MQ session is not usable."""
    text = f"{type(exc).__name__} {exc}".lower()
    for pattern in _SESSION_ERROR_PATTERNS:
        if re.search(pattern, text):
            return True
    return False


__all__ = ["is_api_session_error"]
