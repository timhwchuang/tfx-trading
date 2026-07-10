"""Host-bound service helpers (Phase G3).

Mixin callables are installed on the service as ``types.MethodType(fn, host)``
so ``self`` inside pipeline methods is the TradingEngine host (locks, Book,
test doubles like ``host.place_order = mock`` keep working).
"""

from __future__ import annotations

import types
from typing import Any


def bind_mixin_methods(service: Any, host: Any, *mixin_classes: type) -> None:
    """Install public callables from mixin classes onto ``service``, bound to ``host``."""
    for mixin in mixin_classes:
        for name, attr in vars(mixin).items():
            if name.startswith("__"):
                continue
            if isinstance(attr, property) or isinstance(attr, type):
                continue
            if isinstance(attr, staticmethod):
                # Keep as plain function so ``self._static(x)`` does not inject host.
                object.__setattr__(service, name, attr.__func__)
                continue
            if isinstance(attr, classmethod):
                object.__setattr__(
                    service, name, types.MethodType(attr.__func__, type(host))
                )
                continue
            if not callable(attr):
                continue
            object.__setattr__(service, name, types.MethodType(attr, host))


def service_defines(service: Any, name: str) -> bool:
    """True if ``name`` is a bound method installed on the service instance."""
    d = object.__getattribute__(service, "__dict__")
    if name not in d:
        return False
    return callable(d[name])


class HostBoundService:
    """Service shell: methods bound to host; ``EngineService`` start/stop.

    Passive services (no background threads) leave ``start``/``stop`` as no-ops
    but still belong on ``TradingEngine._services`` so ``run()`` tears them
    down LIFO if they later grow autonomous workers.
    """

    def __init__(self, host: Any, *mixin_classes: type) -> None:
        object.__setattr__(self, "_host", host)
        bind_mixin_methods(self, host, *mixin_classes)

    @property
    def host(self) -> Any:
        return object.__getattribute__(self, "_host")

    def start(self) -> None:
        """No-op for passive services; override when owning threads/timers."""
        return None

    def stop(self) -> None:
        """No-op for passive services; override when owning threads/timers."""
        return None


# Back-compat alias
HostBackedService = HostBoundService


__all__ = [
    "HostBoundService",
    "HostBackedService",
    "bind_mixin_methods",
    "service_defines",
]
