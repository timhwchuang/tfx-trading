"""Session-anchored 1m bar ATR (counterfactual-aligned, not engine lookback)."""

from __future__ import annotations

from strategy_opening_range_breakout.atr_utils import BarHLC, atr_at_bar_index
from strategy_opening_range_breakout.orb_logic import MinuteBar


class SessionAtrTracker:
    """Accumulate session 1m bars and compute SMA(TR) ATR at each bar close."""

    def __init__(self, *, atr_period: int, min_atr_floor: float) -> None:
        self._atr_period = atr_period
        self._min_atr_floor = min_atr_floor
        self._bars: list[BarHLC] = []

    def reset(self) -> None:
        self._bars.clear()

    def on_bar_closed(self, bar: MinuteBar) -> float:
        self._bars.append((bar.high, bar.low, bar.close))
        idx = len(self._bars) - 1
        return atr_at_bar_index(
            self._bars,
            idx,
            period=self._atr_period,
            min_atr_floor=self._min_atr_floor,
        )
