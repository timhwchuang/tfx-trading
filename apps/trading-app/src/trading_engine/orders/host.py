"""OrderHost Protocol — surface the order pipeline may use (Phase G2)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from trading_engine.book import Book
from trading_engine.connectivity import ConnectivityState
from trading_engine.integrity import IntegrityState
from trading_engine.locking import DomainLock
from trading_engine.ticks import TickState


class OrderHost(Protocol):
    """Minimal host surface for order flight / place / callback / fill / settle."""

    lock: DomainLock
    api: Any
    contract: Any
    _cfg: Any
    _book: Book
    _link: ConnectivityState
    _integrity: IntegrityState
    _ticks: TickState
    _order_adapter: Any
    _alerts: Any
    _clock: Callable[[], float]
    strategy: Any
    _order_queue: Any
    _order_sync_mode: bool
    _order_worker_started: bool
    _raw_order_evt_dumped: set
    _archive: Any

    def _call_api(self, fn, *args, **kwargs): ...

    def _clear_pending(self, *, watch_late_fill: bool = False) -> None: ...

    def _make_signal_id(self, ts: int) -> str: ...

    def _enqueue_order(self, signal) -> None: ...

    def sync_positions(self, *, force_resync: bool = False) -> None: ...

    def reset_strategy_state(self) -> None: ...

    def _stage_critical_alert(self, msg: str) -> None: ...

    def _flush_staged_critical_alert(self) -> None: ...

    def _risk_gate(self, ts: int, dt) -> Any: ...

    def _market_snapshot(self, ts: int, price: float, dt) -> Any: ...

    def _position_snapshot(self) -> Any: ...

    def _active_session_windows(self, dt): ...


__all__ = ["OrderHost"]
