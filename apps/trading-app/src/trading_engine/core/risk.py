"""Capital risk: cumulative realized equity MDD freeze.

MDD is **progressive** (not day-scoped). Day rollover must not clear
``capital_frozen``, ``realized_pnl``, or ``equity_peak``.

Not cleared by a plain process restart when durable ``CapitalStore`` is
enabled — the book is **reloaded** from JSON. Clear only via
``clear_capital_risk()``, empty ``capital_state_path``, or deleting the
JSON before start.

``max_mdd_points <= 0`` disables the capital freeze (UAT default).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CapitalRiskState:
    """Mutable capital book for progressive MDD."""

    realized_pnl: float = 0.0
    equity_peak: float = 0.0
    capital_frozen: bool = False

    @property
    def current_drawdown(self) -> float:
        return max(0.0, self.equity_peak - self.realized_pnl)

    def apply_realized_pnl(self, pnl_delta: float) -> None:
        """Accumulate realized PnL and refresh equity peak (HWM)."""
        self.realized_pnl = round(self.realized_pnl + pnl_delta, 4)
        if self.realized_pnl > self.equity_peak:
            self.equity_peak = self.realized_pnl

    def evaluate_mdd(self, max_mdd_points: float) -> bool:
        """Return True if this call newly freezes capital (breach transition).

        Sticky: once frozen, stays frozen until ``clear()``.
        """
        if self.capital_frozen:
            return False
        limit = float(max_mdd_points or 0)
        if limit <= 0:
            return False
        if self.current_drawdown >= limit:
            self.capital_frozen = True
            return True
        return False

    def clear(self) -> None:
        """Operator clear: reset progressive equity book and unfreeze."""
        self.realized_pnl = 0.0
        self.equity_peak = 0.0
        self.capital_frozen = False


def compute_limit_price(signal_price: float, *, is_buy: bool, ioc_slippage: int) -> float:
    """IOC limit from signal price (host-owned; not strategy/telemetry)."""
    if is_buy:
        return signal_price + ioc_slippage
    return signal_price - ioc_slippage


__all__ = ["CapitalRiskState", "compute_limit_price"]
