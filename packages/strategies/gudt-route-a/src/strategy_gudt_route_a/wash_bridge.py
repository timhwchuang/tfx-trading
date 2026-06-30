"""Bridge to trading-app wash probe rules (canonical research implementation)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from reporting import gudt_wash_probe as _wp


def _wash_probe():
    try:
        from reporting import gudt_wash_probe as wp
    except ImportError as exc:
        raise ImportError(
            "strategy-gudt-route-a stack requires apps/trading-app on PYTHONPATH"
        ) from exc
    return wp


def __getattr__(name: str):
    if name == "simulate_atr_trail_skew_exit":
        from reporting.simulate_atr_trail_skew_exit import simulate_atr_trail_skew_exit

        return simulate_atr_trail_skew_exit
    return getattr(_wash_probe(), name)
