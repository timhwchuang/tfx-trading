"""Injectable side-effect ports: alerts + archive (Host runtime).

Live Host does not inject telemetry/observability ports.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class AlertPort(Protocol):
    def send(self, message: str, *, level: str = "WARNING") -> bool: ...


class NullAlertPort:
    def send(self, message: str, *, level: str = "WARNING") -> bool:
        logger.info("ALERT [%s] %s", level, message)
        return False


class ArchivePort(Protocol):
    def maybe_start_tick_archive(self, product_code: str) -> Any: ...

    def enqueue_tick(self, tick: Any, tick_type: int) -> None: ...

    def shutdown_tick_archive(self) -> None: ...

    def archive_kbars(
        self, kbars: Any, *, product_code: str, trade_date: datetime.date
    ) -> None: ...


class NullArchivePort:
    def maybe_start_tick_archive(self, product_code: str) -> Any:
        return None

    def enqueue_tick(self, tick: Any, tick_type: int) -> None:
        return None

    def shutdown_tick_archive(self) -> None:
        return None

    def archive_kbars(self, kbars: Any, *, product_code: str, trade_date: datetime.date) -> None:
        return None


__all__ = [
    "AlertPort",
    "ArchivePort",
    "NullAlertPort",
    "NullArchivePort",
]
