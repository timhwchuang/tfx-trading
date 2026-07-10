"""Assemble RiskGate for Strategy.evaluate (Phase E Wave 3).

Pure assembly from Book / Link / Integrity / Capital / session windows.
TradingEngine._risk_gate delegates here.
"""

from __future__ import annotations

import datetime
from typing import Any, Protocol

from trading_engine.core.types import RiskGate


class RiskGateHost(Protocol):
    """Minimal surface for build_risk_gate (implemented by TradingEngine)."""

    position_qty: int
    is_pending: bool
    exit_pending: bool
    last_exit_time: int
    consecutive_loss: int
    daily_pnl: float
    _api_connected: bool
    _settling: bool
    _position_unconfirmed: bool
    _capital: Any
    _cfg: Any
    _calendar: Any

    def _active_session_windows(self, dt: datetime.datetime): ...

    def is_trading_session(self, dt: datetime.datetime) -> bool: ...

    @property
    def entry_blocked(self) -> bool: ...

    def _is_reconnect_warmup_active(self, ts: int) -> bool: ...


def build_risk_gate(host: RiskGateHost, ts: int, dt: datetime.datetime) -> RiskGate:
    """Build the pre-computed RiskGate snapshot for one evaluate call."""
    windows = host._active_session_windows(dt)
    if windows is None:
        # Inter-session gap: if still holding, keep force_flatten sticky.
        after_flatten = host.position_qty > 0
        force_flatten = host.position_qty > 0
    else:
        start, end, flatten, force = windows
        after_flatten = host._calendar.is_at_or_after(
            dt, flatten, session_start=start, session_end=end
        )
        force_flatten = host._calendar.is_at_or_after(
            dt, force, session_start=start, session_end=end
        )
    return RiskGate(
        api_connected=host._api_connected,
        is_pending=host.is_pending,
        exit_pending=host.exit_pending,
        cooldown_active=ts - host.last_exit_time < host._cfg.cooldown_sec,
        in_trading_session=host.is_trading_session(dt),
        block_new_entry=host.entry_blocked,
        consecutive_loss=host.consecutive_loss,
        daily_pnl=host.daily_pnl,
        after_flatten_time=after_flatten,
        force_flatten=force_flatten,
        reconnect_warmup_active=host._is_reconnect_warmup_active(ts),
        settling=host._settling,
        position_unconfirmed=host._position_unconfirmed,
        capital_frozen=host._capital.capital_frozen,
        realized_pnl=host._capital.realized_pnl,
        equity_peak=host._capital.equity_peak,
        current_drawdown=host._capital.current_drawdown,
    )


__all__ = ["RiskGateHost", "build_risk_gate"]
