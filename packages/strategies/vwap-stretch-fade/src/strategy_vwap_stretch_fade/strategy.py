"""VWAP stretch fade: mean reversion when |price-vwap| >= stretch_k * ATR."""

from __future__ import annotations

import datetime
import logging
from collections.abc import Callable
from typing import Any

from trading_engine.core.audit.decision_audit import DecisionAudit, format_decision_audit
from trading_engine.core.audit.signal_audit import SignalAudit
from trading_engine.core.strategy import BaseStrategy
from trading_engine.core.types import (
    MarketSnapshot,
    OrderSignal,
    PositionSnapshot,
    RiskGate,
    StrategySideEffects,
)

from strategy_vwap_stretch_fade.atr_utils import dynamic_atr_distance
from strategy_vwap_stretch_fade.params import StretchFadeParams

logger = logging.getLogger(__name__)


class VwapStretchFadeStrategy(BaseStrategy):
    """Fade over-extended price vs 5m VWAP; ATR-scaled exits (FT-004 semantics)."""

    def __init__(
        self,
        params: StretchFadeParams,
        obs: Any | None = None,
    ) -> None:
        super().__init__()
        self.params = params
        self.obs = obs
        self._can_arm = True
        self._last_entry_ts: int = 0

    def reset(self) -> None:
        self._can_arm = True
        self._last_entry_ts = 0

    def _z_score(self, market: MarketSnapshot) -> float:
        atr = max(market.current_atr, self.params.min_atr_threshold)
        if atr <= 0:
            return 0.0
        return (market.price - market.vwap) / atr

    def _fade_direction(self, z: float) -> tuple[str, str]:
        """Return (position_dir Long|Short, audit_dir Buy|Sell)."""
        if z > 0:
            return "Short", "Sell"
        return "Long", "Buy"

    def _emit_risk_blocked_audit(
        self,
        reason: str,
        market: MarketSnapshot,
        *,
        consecutive_loss: int | None = None,
        atr: float | None = None,
    ) -> None:
        if self.obs is None:
            return
        if not self.obs.record_risk_blocked(reason, ts=market.ts):
            return
        ctx = self.obs.get_pressure_context()
        risk_dec = DecisionAudit(
            event_type="risk_blocked",
            ts=market.ts,
            price=market.price,
            block_reason=reason,
        )
        if consecutive_loss is not None:
            risk_dec.consecutive_loss = consecutive_loss
        if atr is not None:
            risk_dec.atr = atr
        for k, v in ctx.items():
            setattr(risk_dec, k, v)
        logger.info("DECISION_AUDIT %s", format_decision_audit(risk_dec))

    def build_entry_audit(
        self,
        market: MarketSnapshot,
        direction: str,
        *,
        z: float,
    ) -> SignalAudit:
        return SignalAudit(
            intent="entry",
            direction=direction,
            price=market.price,
            ts=market.ts,
            atr=round(market.current_atr, 2),
            vwap=round(market.vwap, 1),
            reason="vwap_stretch_fade",
            vol_1s=market.vol_1s,
        )

    def build_exit_audit(
        self,
        market: MarketSnapshot,
        direction: str,
        reason: str,
        *,
        trail_points_used: float = 0.0,
        entry_price: float = 0.0,
        hold_ticks: int = 0,
        in_grace: bool = False,
        hard_stop_level: float = 0.0,
        trailing_peak: float = 0.0,
    ) -> SignalAudit:
        return SignalAudit(
            intent="exit",
            direction=direction,
            price=market.price,
            ts=market.ts,
            atr=round(market.current_atr, 2),
            vwap=round(market.vwap, 1),
            reason=reason,
            trail_points_used=round(trail_points_used, 2),
            entry_price=round(entry_price, 1),
            hold_ticks=hold_ticks,
            in_grace=in_grace,
            hard_stop_level=round(hard_stop_level, 1),
            trailing_peak=round(trailing_peak, 1),
        )

    def _effective_hard_stop(self, atr: float) -> float:
        return dynamic_atr_distance(
            atr,
            floor=self.params.trail_points_floor * 0.5,
            atr_k=self.params.hard_stop_atr_k,
        )

    def _effective_tp(self, atr: float) -> float:
        return dynamic_atr_distance(atr, floor=10.0, atr_k=self.params.tp_atr_k)

    def _effective_trail(self, atr: float) -> float:
        if not self.params.atr_trailing_enabled:
            return self.params.trail_points_floor
        return dynamic_atr_distance(
            atr,
            floor=self.params.trail_points_floor,
            atr_k=self.params.trail_atr_k,
        )

    def _in_exit_grace_period(self, ts: int, position: PositionSnapshot) -> bool:
        if position.ticks_since_entry < self.params.exit_grace_ticks:
            return True
        if position.entry_exchange_ts <= 0:
            return False
        return (ts - position.entry_exchange_ts) < self.params.exit_grace_sec

    def evaluate(
        self,
        market: MarketSnapshot,
        position: PositionSnapshot,
        risk: RiskGate,
        vol_threshold: tuple[float, float, float],
        *,
        session_force_flatten_time: datetime.time,
        max_daily_loss_points: float,
        on_daily_loss_block: Callable[[], None] | None = None,
    ) -> tuple[OrderSignal | None, StrategySideEffects]:
        del vol_threshold  # unused — no momentum spike path
        effects = StrategySideEffects()

        if risk.settling or risk.position_unconfirmed:
            return None, effects

        if not risk.api_connected:
            if position.has_position:
                if risk.force_flatten:
                    return self.session_force_flatten_signal(
                        market, position, session_force_flatten_time
                    )
                return self.manage_exit(market, position)
            return None, effects

        if risk.reconnect_warmup_active or risk.atr_stale:
            if position.has_position:
                if risk.force_flatten:
                    return self.session_force_flatten_signal(
                        market, position, session_force_flatten_time
                    )
                return self.manage_exit(market, position)
            return None, effects

        if risk.is_pending or risk.exit_pending:
            return None, effects
        if risk.cooldown_active:
            return None, effects
        if not risk.in_trading_session:
            return None, effects

        if risk.daily_pnl <= -max_daily_loss_points and not risk.block_new_entry:
            effects.block_new_entry = True
            self._emit_risk_blocked_audit(
                "daily_pnl", market, consecutive_loss=risk.consecutive_loss
            )
            if on_daily_loss_block is not None:
                on_daily_loss_block()

        if position.has_position:
            if risk.force_flatten:
                return self.session_force_flatten_signal(
                    market, position, session_force_flatten_time
                )
            return self.manage_exit(market, position)

        if risk.after_flatten_time:
            self._emit_risk_blocked_audit("after_flatten", market)
            return None, effects
        if risk.block_new_entry:
            self._emit_risk_blocked_audit("block_new_entry", market)
            return None, effects
        if risk.consecutive_loss >= self.params.max_consecutive_loss:
            self._emit_risk_blocked_audit(
                "consecutive_loss", market, consecutive_loss=risk.consecutive_loss
            )
            return None, effects
        if market.current_atr < self.params.min_atr_threshold:
            self._emit_risk_blocked_audit("min_atr", market, atr=market.current_atr)
            return None, effects

        return self._try_stretch_fade_entry(market), effects

    def _try_stretch_fade_entry(self, market: MarketSnapshot) -> OrderSignal | None:
        z = self._z_score(market)

        if not self._can_arm and abs(z) <= self.params.reset_z:
            self._can_arm = True

        if not self._can_arm:
            return None
        if self._last_entry_ts and market.ts - self._last_entry_ts < self.params.cooldown_sec:
            return None
        if abs(z) < self.params.stretch_k:
            return None

        pos_dir, audit_dir = self._fade_direction(z)
        self._can_arm = False
        self._last_entry_ts = market.ts

        if self.obs is not None:
            self.obs.record_momentum_trigger()
            self.obs.record_momentum_entry()

        logger.info(
            "MOMENTUM %s vwap_stretch_fade | z=%.2f stretch_k=%.2f",
            pos_dir,
            z,
            self.params.stretch_k,
        )

        return OrderSignal(
            audit_dir,
            1,
            market.price,
            "entry",
            exchange_ts=market.ts,
            audit=self.build_entry_audit(market, audit_dir, z=z),
        )

    def manage_exit(
        self, market: MarketSnapshot, position: PositionSnapshot
    ) -> tuple[OrderSignal | None, StrategySideEffects]:
        pos_dir = position.position_dir if position.position_dir in ("Long", "Short", "Flat") else "Flat"
        atr = market.current_atr
        hard_dist = self._effective_hard_stop(atr)
        tp_dist = self._effective_tp(atr)
        trail_pts = self._effective_trail(atr)
        in_grace = self._in_exit_grace_period(market.ts, position)

        if pos_dir == "Long":
            hard_hit = market.price <= position.entry_price - hard_dist
            tp_hit = not in_grace and market.price >= position.entry_price + tp_dist
            trail_hit = not in_grace and market.price <= position.trailing_peak - trail_pts
            if hard_hit or tp_hit or trail_hit:
                reason = "stop_loss" if hard_hit else "take_profit" if tp_hit else "trailing_stop"
                return (
                    OrderSignal(
                        "Sell",
                        1,
                        market.price,
                        "exit",
                        exchange_ts=market.ts,
                        audit=self.build_exit_audit(
                            market,
                            "Sell",
                            reason,
                            trail_points_used=trail_pts,
                            entry_price=position.entry_price,
                            hold_ticks=position.ticks_since_entry,
                            in_grace=in_grace,
                            hard_stop_level=position.entry_price - hard_dist,
                            trailing_peak=position.trailing_peak,
                        ),
                    ),
                    StrategySideEffects(),
                )
        elif pos_dir == "Short":
            hard_hit = market.price >= position.entry_price + hard_dist
            tp_hit = not in_grace and market.price <= position.entry_price - tp_dist
            trail_hit = not in_grace and market.price >= position.trailing_peak + trail_pts
            if hard_hit or tp_hit or trail_hit:
                reason = "stop_loss" if hard_hit else "take_profit" if tp_hit else "trailing_stop"
                return (
                    OrderSignal(
                        "Buy",
                        1,
                        market.price,
                        "exit",
                        exchange_ts=market.ts,
                        audit=self.build_exit_audit(
                            market,
                            "Buy",
                            reason,
                            trail_points_used=trail_pts,
                            entry_price=position.entry_price,
                            hold_ticks=position.ticks_since_entry,
                            in_grace=in_grace,
                            hard_stop_level=position.entry_price + hard_dist,
                            trailing_peak=position.trailing_peak,
                        ),
                    ),
                    StrategySideEffects(),
                )
        return None, StrategySideEffects()

    def session_force_flatten_signal(
        self,
        market: MarketSnapshot,
        position: PositionSnapshot,
        session_force_flatten_time: datetime.time,
    ) -> tuple[OrderSignal | None, StrategySideEffects]:
        action = "Sell" if position.position_dir == "Long" else "Buy"
        logger.warning(
            "收盤強制平倉 | %s @ %.1f | force_flatten_time=%s",
            position.position_dir,
            market.price,
            session_force_flatten_time.strftime("%H:%M"),
        )
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
                    entry_price=position.entry_price if position.has_position else 0.0,
                    hold_ticks=position.ticks_since_entry if position.has_position else 0,
                    trailing_peak=position.trailing_peak if position.has_position else 0.0,
                ),
            ),
            StrategySideEffects(),
        )
