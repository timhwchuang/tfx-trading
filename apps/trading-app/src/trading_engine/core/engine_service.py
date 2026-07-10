"""Engine-owned service lifecycle (Phase G3).

TradingEngine acts as dispatcher/lifecycle owner: ``start()`` services in
order, ``stop()`` in reverse on shutdown. Services with nothing to do use
no-op defaults via :class:`NullEngineService` or empty methods.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EngineService(Protocol):
    """Unified start/stop surface for composed engine services."""

    def start(self) -> None:
        """Begin background work (threads, subscriptions). Idempotent preferred."""
        ...

    def stop(self) -> None:
        """Release resources. Must be idempotent."""
        ...


class NullEngineService:
    """No-op service for tests / placeholders."""

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None


__all__ = ["EngineService", "NullEngineService"]
