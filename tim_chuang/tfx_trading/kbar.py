from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class KBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    amount: float
