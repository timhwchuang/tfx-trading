"""Host fill ledger line: entry/exit PnL only (no strategy near-miss / VWAP).

Observability extras (DAILY_SUMMARY counters, near-miss) stay out of the kernel.
Strategy-layer metrics belong on the strategy, not on FILL_AUDIT.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass


@dataclass
class FillAudit:
    """Minimal bookkeeping row for one confirmed fill."""

    intent: str  # entry | exit
    direction: str  # Buy | Sell
    fill_price: float
    qty: int
    pnl_points: float  # 0 on entry; exit realized points for this fill
    realized_pnl: float  # progressive equity after this fill
    equity_peak: float
    drawdown: float
    order_id: str
    ts: int
    signal_id: str = ""
    exit_reason: str = ""


def format_fill_audit(audit: FillAudit) -> str:
    return json.dumps(asdict(audit), ensure_ascii=False, separators=(",", ":"))


__all__ = ["FillAudit", "format_fill_audit"]
