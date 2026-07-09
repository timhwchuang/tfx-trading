"""Minimal flip strategy for infrastructure / UAT soak tests.

After each confirmed fill, wait ``flip_interval_sec`` then flip:
flat → Buy, long → Sell. No TP/SL, no alpha filters.
Session force-flatten is left to the Host (returns None → flatten slippage).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any

from trading_engine.core.audit.signal_audit import SignalAudit
from trading_engine.core.strategy import BaseStrategy
from trading_engine.core.types import (
    MarketSnapshot,
    OrderSignal,
    PositionSnapshot,
    RiskGate,
    StrategySideEffects,
)


@dataclass(frozen=True)
class SimpleParams:
    flip_interval_sec: int = 300
    qty: int = 1
    day_session_start: datetime.time = datetime.time(8, 45)
    day_session_end: datetime.time = datetime.time(13, 45)
    night_session_start: datetime.time = datetime.time(15, 0)
    night_session_end: datetime.time = datetime.time(5, 0)

    @classmethod
    def from_runtime_config(cls, cfg: Any) -> SimpleParams:
        return cls(
            flip_interval_sec=int(
                getattr(
                    cfg,
                    "simple_flip_interval_sec",
                    getattr(cfg, "flip_interval_sec", 300),
                )
            ),
            qty=1,
            day_session_start=getattr(cfg, "session_start", datetime.time(8, 45)),
            day_session_end=getattr(cfg, "session_end", datetime.time(13, 45)),
            night_session_start=getattr(
                cfg, "night_session_start", datetime.time(15, 0)
            ),
            night_session_end=getattr(
                cfg, "night_session_end", datetime.time(5, 0)
            ),
        )


class SimpleStrategy(BaseStrategy):
    """UAT soak: flip long/flat every N seconds after last fill."""

    def __init__(self, params: SimpleParams, obs: Any | None = None) -> None:
        super().__init__()
        self.params = params
        self.obs = obs
        self._last_fill_ts: int | None = None
        self._had_position: bool = False

    def reset(self) -> None:
        # Keep fill clock across episode resets within the same process.
        return None

    def _interval_elapsed(self, market_ts: int) -> bool:
        if self._last_fill_ts is None:
            return True
        return (market_ts - self._last_fill_ts) >= self.params.flip_interval_sec

    def evaluate(
        self,
        market: MarketSnapshot,
        position: PositionSnapshot,
        risk: RiskGate,
    ) -> tuple[OrderSignal | None, StrategySideEffects]:
        if risk.settling or risk.position_unconfirmed:
            return None, StrategySideEffects()

        if (
            not risk.api_connected
            or risk.is_pending
            or risk.exit_pending
            or risk.cooldown_active
            or not risk.in_trading_session
            or risk.after_flatten_time
            or risk.force_flatten
            or risk.reconnect_warmup_active
        ):
            return None, StrategySideEffects()

        if position.has_position:
            self._had_position = True
            if position.entry_exchange_ts > 0:
                self._last_fill_ts = position.entry_exchange_ts
            elif self._last_fill_ts is None:
                # Resync/restart: position known but entry ts missing. Seed
                # fill clock to now so we wait a full interval (not flip-exit
                # on the first tick while still long).
                self._last_fill_ts = market.ts
            if not self._interval_elapsed(market.ts):
                return None, StrategySideEffects()
            audit = self.build_exit_audit(
                market,
                position.position_dir or "Long",
                "uat_flip_exit",
                entry_price=position.entry_price,
            )
            signal = OrderSignal(
                action="Sell",
                qty=max(1, position.qty or self.params.qty),
                ref_price=market.price,
                intent="exit",
                exchange_ts=market.ts,
                audit=audit,
            )
            return signal, StrategySideEffects()

        # Flat: detect exit fill transition, then maybe re-enter.
        if risk.block_new_entry:
            return None, StrategySideEffects()

        if self._had_position:
            self._last_fill_ts = market.ts
            self._had_position = False

        if not self._interval_elapsed(market.ts):
            return None, StrategySideEffects()

        audit = self.build_entry_audit(market, "Long")
        signal = OrderSignal(
            action="Buy",
            qty=self.params.qty,
            ref_price=market.price,
            intent="entry",
            exchange_ts=market.ts,
            audit=audit,
        )
        return signal, StrategySideEffects()

    def manage_exit(
        self, market: MarketSnapshot, position: PositionSnapshot
    ) -> tuple[OrderSignal | None, StrategySideEffects]:
        # Flip exits are emitted from evaluate; no TP/SL path.
        del market, position
        return None, StrategySideEffects()

    def session_force_flatten_signal(
        self,
        market: MarketSnapshot,
        position: PositionSnapshot,
        session_force_flatten_time: datetime.time,
    ) -> tuple[OrderSignal | None, StrategySideEffects]:
        # Let Host synthesize flatten with flatten_slippage_points.
        del market, position, session_force_flatten_time
        return None, StrategySideEffects()

    def build_entry_audit(
        self,
        market: MarketSnapshot,
        direction: str,
    ) -> SignalAudit:
        return SignalAudit(
            intent="entry",
            direction=direction,
            price=market.price,
            ts=market.ts,
            reason="uat_flip_entry",
        )


__all__ = ["SimpleParams", "SimpleStrategy"]
