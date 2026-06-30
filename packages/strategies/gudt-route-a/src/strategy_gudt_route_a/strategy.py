"""GUDT Route A UAT stack — replay strategy driven by CF day plans."""

from __future__ import annotations

import datetime
import logging
from typing import Any

from trading_engine.core.strategy import BaseStrategy
from trading_engine.core.types import (
    MarketSnapshot,
    OrderSignal,
    PositionSnapshot,
    RiskGate,
    StrategySideEffects,
)

from strategy_gudt_route_a.params import GudtRouteAParams
from strategy_gudt_route_a.types import DayReplayPlan, TradeEvent

logger = logging.getLogger(__name__)


class GudtRouteAStrategy(BaseStrategy):
    """Replay counterfactual stack picks through TradingEngine for parity backtest."""

    def __init__(
        self,
        params: GudtRouteAParams,
        obs: Any = None,
        *,
        day_plans: dict[str, DayReplayPlan] | None = None,
    ) -> None:
        self.params = params
        self.obs = obs
        self._day_plans: dict[str, DayReplayPlan] = day_plans or {}
        self._current_day: str | None = None
        self._plan: DayReplayPlan | None = None
        self._event_idx = 0
        self._pending_events: list[TradeEvent] = []

    def set_day_plans(self, plans: dict[str, DayReplayPlan]) -> None:
        self._day_plans = plans

    def _day_key(self, market: MarketSnapshot) -> str:
        local = market.dt
        if local.tzinfo is not None:
            local = local.astimezone().replace(tzinfo=None)
        return local.date().isoformat()

    def _ensure_day(self, market: MarketSnapshot) -> None:
        day = self._day_key(market)
        if day == self._current_day:
            return
        self._current_day = day
        self._plan = self._day_plans.get(day)
        self._event_idx = 0
        self._pending_events = list(self._plan.events) if self._plan and not self._plan.skipped else []

    def reset(self) -> None:
        self._current_day = None
        self._plan = None
        self._event_idx = 0
        self._pending_events = []

    def evaluate(
        self,
        market: MarketSnapshot,
        position: PositionSnapshot,
        risk: RiskGate,
        vol_threshold: tuple[float, float, float],
        *,
        session_force_flatten_time: datetime.time,
        max_daily_loss_points: float,
        on_daily_loss_block: Any = None,
    ) -> tuple[OrderSignal | None, StrategySideEffects]:
        del risk, vol_threshold, session_force_flatten_time, max_daily_loss_points, on_daily_loss_block
        self._ensure_day(market)
        if not self._pending_events or self._plan is None or self._plan.skipped:
            return None, StrategySideEffects()

        pos_dir = (
            position.position_dir
            if position.position_dir in ("Long", "Short", "Flat")
            else "Flat"
        )

        while self._event_idx < len(self._pending_events):
            ev = self._pending_events[self._event_idx]
            if market.ts < ev.ts:
                return None, StrategySideEffects()

            if ev.leg == "long_entry" and pos_dir == "Flat":
                self._event_idx += 1
                if self.obs is not None:
                    self.obs.record_momentum_trigger()
                    self.obs.record_momentum_entry()
                logger.info("GUDT Route A long entry @ %.1f path=%s", ev.price, self._plan.path)
                return (
                    OrderSignal(
                        "Buy",
                        1,
                        ev.price,
                        "entry",
                        exchange_ts=market.ts,
                        audit=self.build_entry_audit(market, "Buy", 1.0, vol_threshold[0]),
                    ),
                    StrategySideEffects(),
                )

            if ev.leg == "long_exit" and pos_dir == "Long":
                self._event_idx += 1
                return (
                    OrderSignal(
                        "Sell",
                        1,
                        ev.price,
                        "exit",
                        exchange_ts=market.ts,
                        audit=self.build_exit_audit(
                            market,
                            "Sell",
                            ev.reason,
                            entry_price=position.entry_price,
                            hold_ticks=position.ticks_since_entry,
                        ),
                    ),
                    StrategySideEffects(),
                )

            if ev.leg == "short_entry" and pos_dir == "Flat":
                self._event_idx += 1
                logger.info("GUDT Route A short entry @ %.1f reason=%s", ev.price, ev.reason)
                return (
                    OrderSignal(
                        "Sell",
                        1,
                        ev.price,
                        "entry",
                        exchange_ts=market.ts,
                        audit=self.build_entry_audit(market, "Sell", 1.0, vol_threshold[0]),
                    ),
                    StrategySideEffects(),
                )

            if ev.leg == "short_exit" and pos_dir == "Short":
                self._event_idx += 1
                return (
                    OrderSignal(
                        "Buy",
                        1,
                        ev.price,
                        "exit",
                        exchange_ts=market.ts,
                        audit=self.build_exit_audit(
                            market,
                            "Buy",
                            ev.reason,
                            entry_price=position.entry_price,
                            hold_ticks=position.ticks_since_entry,
                        ),
                    ),
                    StrategySideEffects(),
                )

            # Event is due but position not ready (e.g. pending fill) — wait, do not skip.
            return None, StrategySideEffects()

        return None, StrategySideEffects()

    def session_force_flatten_signal(
        self,
        market: MarketSnapshot,
        position: PositionSnapshot,
        session_force_flatten_time: datetime.time,
    ) -> tuple[OrderSignal | None, StrategySideEffects]:
        if not position.has_position:
            return None, StrategySideEffects()
        action = "Sell" if position.position_dir == "Long" else "Buy"
        return (
            OrderSignal(
                action,
                1,
                market.price,
                "exit",
                exchange_ts=market.ts,
                slippage_points=self.params.flatten_slippage_points,
                audit=self.build_exit_audit(
                    market,
                    action,
                    "session_force_flatten",
                    entry_price=position.entry_price,
                    hold_ticks=position.ticks_since_entry,
                ),
            ),
            StrategySideEffects(),
        )
