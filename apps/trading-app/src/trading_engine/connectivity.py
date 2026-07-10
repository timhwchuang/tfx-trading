"""Link / connectivity state: broker session health, reconnect, warmup.

Owned by TradingEngine as ``_link``. Access explicitly via ``self._link.*``
(Phase G1 — no engine attribute forwarders).

Behavior (disconnect / reconnect / session watchdog) lives in
``connectivity_ops.ConnectivityOpsMixin``.
"""

from __future__ import annotations

from dataclasses import dataclass

LINK_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "_api_connected",
        "_disconnect_since",
        "_disconnect_count_today",
        "_reconnect_warmup_until_ts",
        "_pending_reconnect_warmup",
        "_session_relogin_attempts",
        "_next_relogin_at",
        "_reconnect_generation",
        "_connected_reconnect_generation",
    }
)


@dataclass
class ConnectivityState:
    """Broker link + reconnect bookkeeping (not capital, not position)."""

    _api_connected: bool = True
    _disconnect_since: float = 0.0
    _disconnect_count_today: int = 0
    _reconnect_warmup_until_ts: int = 0
    _pending_reconnect_warmup: bool = False
    _session_relogin_attempts: int = 0
    _next_relogin_at: float = 0.0
    _reconnect_generation: int = 0
    _connected_reconnect_generation: int = 0

    def reset_day_ops(self) -> None:
        """Trading-day rollover: daily disconnect budget only."""
        self._disconnect_count_today = 0


__all__ = ["ConnectivityState", "LINK_FIELD_NAMES"]
