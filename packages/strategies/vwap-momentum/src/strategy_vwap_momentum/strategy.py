"""VWAP momentum entry/exit decision logic."""

from __future__ import annotations

import datetime
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from trading_engine.core.audit.decision_audit import DecisionAudit, format_decision_audit
from trading_engine.core.audit.signal_audit import SignalAudit, format_signal_audit
from trading_engine.core.strategy import BaseStrategy
from trading_engine.core.types import (
    MarketSnapshot,
    OrderSignal,
    PositionSnapshot,
    RiskGate,
    StrategySideEffects,
)
from trading_engine.calendar.taifex import TAIWAN_TZ

from strategy_vwap_momentum.params import StrategyParams
from strategy_vwap_momentum.structure import (
    STRUCTURE_ALGO_VERSION,
    StructureState,
    regime_allows_entry,
    structure_params_from_strategy,
    structure_state_from_market_fields,
)
from strategy_vwap_momentum.trend import (
    dynamic_trail_points,
    dynamic_vwap_stop_distance,
)

logger = logging.getLogger(__name__)


@dataclass
class MomentumState:
    """Internal momentum episode state (strictly private to this plugin).

    - `active` + `direction` + `trigger_time` drive the two-phase (activate → pullback) logic
      and the  momentum timeout.
    - `peak` was historical (used to track extreme during wait for pullback) but was never
      read for any decision or audit. It has been removed as dead code (see CodeReview#1).
    """

    active: bool = False
    direction: str = "None"
    trigger_time: int = 0
    episode_id: str = ""


class VWAPMomentumStrategy(BaseStrategy):
    """VWAP Momentum 策略決策實作（實現 Strategy interface）。

    策略相關參數已封裝在此類別內，透過 `self.params` (StrategyParams) 存取。
    所有決策邏輯（進場、出場、停損、Phase 6 濾網等）都只依賴傳入的 snapshots 與 self.params，
    不直接依賴全域 config（sweep patch 機制除外，屬於測試基礎設施）。
    """

    def __init__(
        self,
        params: StrategyParams,
        obs: Any | None = None,
    ) -> None:
        super().__init__()
        self.params = params
        self.obs = obs
        self.momentum = MomentumState()
        self._episode_seq: int = 0
        self._current_trade_date: str = ""

    def reset(self) -> None:
        self.momentum = MomentumState()
        # Note: episode seq and trade_date are *not* reset here (persist for day-level seq across episodes)

    def reset_momentum(self) -> None:
        self.reset()

    def _make_episode_id(self, ts: int) -> str:
        """Generate per-day episode_id like 20260617-003. Seq resets on trade date change."""
        try:
            dt = datetime.datetime.fromtimestamp(ts, tz=TAIWAN_TZ)
            trade_date = dt.strftime("%Y%m%d")
        except Exception:
            # Fallback (tests, non-tz env): use UTC for ID generation.
            # Behavior is equivalent during trading hours.
            dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
            trade_date = dt.strftime("%Y%m%d")
        if trade_date != self._current_trade_date:
            self._current_trade_date = trade_date
            self._episode_seq = 0
        self._episode_seq += 1
        return f"{trade_date}-{self._episode_seq:03d}"

    def _structure_audit_fields(self, market: MarketSnapshot) -> dict[str, Any]:
        """Structure battlefield snapshot for armed / structure_veto audits (filter on only)."""
        if not self.params.structure_filter_enabled:
            return {}
        return {
            "structure_algo_version": STRUCTURE_ALGO_VERSION,
            "structure_bias": market.structure_bias,
            "structure_strength": round(market.structure_strength, 4),
            "structure_in_discount": market.structure_in_discount,
            "structure_in_premium": market.structure_in_premium,
            "structure_fvg_low": market.structure_fvg_low,
            "structure_fvg_high": market.structure_fvg_high,
            "structure_sweep_reclaim": market.structure_sweep_reclaim,
        }

    def _emit_momentum_armed(
        self,
        direction: str,
        episode_id: str,
        market: MarketSnapshot,
        buy_ratio: float,
        sell_ratio: float,
        threshold: float,
        multiplier: float,
    ) -> None:
        """Emit DECISION_AUDIT for momentum_armed. Extracted to avoid Long/Short duplication.
        No pressure ctx attached: armed json kept clean (no irrelevant zeros); ctx only for veto/timeout/risk_blocked per SPEC.
        """
        decision = DecisionAudit(
            event_type="momentum_armed",
            ts=market.ts,
            episode_id=episode_id,
            direction=direction,
            trigger_price=round(market.price, 1),
            vol_1s=market.vol_1s,
            buy_ratio=round(buy_ratio, 4),
            sell_ratio=round(sell_ratio, 4),
            vol_threshold=round(threshold, 1),
            multiplier=multiplier,
            vwap=round(market.vwap, 1),
            atr=round(market.current_atr, 2),
        )
        for k, v in self._structure_audit_fields(market).items():
            setattr(decision, k, v)
        logger.info("DECISION_AUDIT %s", format_decision_audit(decision))

    def activate_momentum(self, direction: str, price: float, ts: int, episode_id: str = "") -> None:
        self.momentum = MomentumState(
            active=True,
            direction=direction,
            trigger_time=ts,
            episode_id=episode_id,
        )
        if self.obs is not None:
            self.obs.record_momentum_trigger()
        logger.info("MOMENTUM %s 突破 | 價格 %.1f", direction, price)

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
        effects = StrategySideEffects()

        # Tiny defensive normalization (low priority per review)
        trend_dir = market.trend_dir if market.trend_dir in ("Long", "Short", "Flat") else "Flat"

        if not risk.api_connected:
            if position.has_position:
                if risk.force_flatten:
                    return self.session_force_flatten_signal(
                        market, position, session_force_flatten_time
                    )
                return self.manage_exit(market, position)
            return None, effects

        structure_stale_block = (
            self.params.structure_filter_enabled and risk.structure_stale
        )
        if risk.reconnect_warmup_active or risk.atr_stale or structure_stale_block:
            if position.has_position:
                if risk.force_flatten:
                    return self.session_force_flatten_signal(
                        market, position, session_force_flatten_time
                    )
                return self.manage_exit(market, position)
            if structure_stale_block and self.obs is not None:
                self.obs.record_risk_blocked("structure_stale", ts=market.ts)
                ctx = self.obs.get_pressure_context()
                risk_dec = DecisionAudit(
                    event_type="risk_blocked",
                    ts=market.ts,
                    price=market.price,
                    block_reason="structure_stale",
                )
                for k, v in ctx.items():
                    setattr(risk_dec, k, v)
                logger.info("DECISION_AUDIT %s", format_decision_audit(risk_dec))
            return None, effects

        if risk.is_pending or risk.exit_pending:
            return None, effects
        if risk.cooldown_active:
            return None, effects
        if not risk.in_trading_session:
            return None, effects

        if risk.daily_pnl <= -max_daily_loss_points and not risk.block_new_entry:
            effects.block_new_entry = True
            if self.obs is not None:
                self.obs.record_risk_blocked("daily_pnl", ts=market.ts)
                ctx = self.obs.get_pressure_context()
                risk_dec = DecisionAudit(
                    event_type="risk_blocked",
                    ts=market.ts,
                    price=market.price,
                    block_reason="daily_pnl",
                    consecutive_loss=risk.consecutive_loss,
                )
                for k, v in ctx.items():
                    setattr(risk_dec, k, v)
                logger.info("DECISION_AUDIT %s", format_decision_audit(risk_dec))
            if on_daily_loss_block is not None:
                on_daily_loss_block()

        if position.has_position:
            if risk.force_flatten:
                return self.session_force_flatten_signal(
                    market, position, session_force_flatten_time
                )
            return self.manage_exit(market, position)

        if risk.after_flatten_time:
            if self.obs is not None:
                self.obs.record_risk_blocked("after_flatten", ts=market.ts)
                ctx = self.obs.get_pressure_context()
                risk_dec = DecisionAudit(
                    event_type="risk_blocked",
                    ts=market.ts,
                    price=market.price,
                    block_reason="after_flatten",
                )
                for k, v in ctx.items():
                    setattr(risk_dec, k, v)
                logger.info("DECISION_AUDIT %s", format_decision_audit(risk_dec))
            return None, effects
        if risk.block_new_entry:
            if self.obs is not None:
                self.obs.record_risk_blocked("block_new_entry", ts=market.ts)
                ctx = self.obs.get_pressure_context()
                risk_dec = DecisionAudit(
                    event_type="risk_blocked",
                    ts=market.ts,
                    price=market.price,
                    block_reason="block_new_entry",
                )
                for k, v in ctx.items():
                    setattr(risk_dec, k, v)
                logger.info("DECISION_AUDIT %s", format_decision_audit(risk_dec))
            return None, effects
        if risk.consecutive_loss >= self.params.max_consecutive_loss:
            if self.obs is not None:
                self.obs.record_risk_blocked("consecutive_loss", ts=market.ts)
                ctx = self.obs.get_pressure_context()
                risk_dec = DecisionAudit(
                    event_type="risk_blocked",
                    ts=market.ts,
                    price=market.price,
                    block_reason="consecutive_loss",
                    consecutive_loss=risk.consecutive_loss,
                )
                for k, v in ctx.items():
                    setattr(risk_dec, k, v)
                logger.info("DECISION_AUDIT %s", format_decision_audit(risk_dec))
            return None, effects
        if market.current_atr < self.params.min_atr_threshold:
            if self.obs is not None:
                self.obs.record_risk_blocked("min_atr", ts=market.ts)
                ctx = self.obs.get_pressure_context()
                risk_dec = DecisionAudit(
                    event_type="risk_blocked",
                    ts=market.ts,
                    price=market.price,
                    block_reason="min_atr",
                    atr=market.current_atr,
                    **ctx,
                )
                logger.info("DECISION_AUDIT %s", format_decision_audit(risk_dec))
            return None, effects

        if not self.momentum.active:
            self._try_activate_momentum(market, vol_threshold)
            return None, effects

        timeout_sec = self.params.momentum_timeout_sec
        if market.ts - self.momentum.trigger_time > timeout_sec:
            if self.obs is not None:
                self.obs.record_momentum_timeout()

            direction = self.momentum.direction
            audit_dir = "Buy" if direction == "Long" else "Sell"

            # Phase 4 migration: emit only DECISION_AUDIT (legacy SIGNAL removed)
            if self.obs is not None:
                ctx = self.obs.get_pressure_context()
                timeout_dec = DecisionAudit(
                    event_type="momentum_timeout",
                    ts=market.ts,
                    episode_id=self.momentum.episode_id,
                    direction=direction,
                    elapsed_sec=market.ts - self.momentum.trigger_time,
                    price=market.price,
                    trend_dir=trend_dir,
                    trend_strength=market.trend_strength,
                    parent_id=self.momentum.episode_id,
                    **ctx,
                )
                logger.info(
                    "DECISION_AUDIT %s", format_decision_audit(timeout_dec)
                )

            logger.info(
                "MOMENTUM %s timeout | elapsed=%ds > %ds (reset)",
                direction,
                market.ts - self.momentum.trigger_time,
                timeout_sec,
            )
            self.reset_momentum()
            return None, effects

        return self._try_pullback_entry(market, vol_threshold), effects

    def _try_activate_momentum(
        self,
        market: MarketSnapshot,
        vol_threshold: tuple[float, float, float],
    ) -> None:
        """Side-effect only: attempts to activate internal momentum state.

        Never produces an OrderSignal on the activation tick (call site no longer
        assigns the return value -- type polish for the previous `signal = ...` smell).
        """
        base_vol, multiplier, threshold = vol_threshold
        buy_ratio = market.buy_vol_1s / market.vol_1s if market.vol_1s > 0 else 0
        sell_ratio = market.sell_vol_1s / market.vol_1s if market.vol_1s > 0 else 0

        if market.vol_1s >= threshold and buy_ratio >= self.params.momentum_buy_ratio:
            logger.info(
                "MOMENTUM 量能通過 | dir=Long vol_1s=%d base=%.0f mult=%.2f "
                "threshold=%.0f buy_ratio=%.2f",
                market.vol_1s,
                base_vol,
                multiplier,
                threshold,
                buy_ratio,
            )
            episode_id = self._make_episode_id(market.ts)
            self.activate_momentum("Long", market.price, market.ts, episode_id=episode_id)
            self._emit_momentum_armed(
                "Long", episode_id, market, buy_ratio, sell_ratio, threshold, multiplier
            )
        elif market.vol_1s >= threshold and sell_ratio >= self.params.momentum_sell_ratio:
            logger.info(
                "MOMENTUM 量能通過 | dir=Short vol_1s=%d base=%.0f mult=%.2f "
                "threshold=%.0f sell_ratio=%.2f",
                market.vol_1s,
                base_vol,
                multiplier,
                threshold,
                sell_ratio,
            )
            episode_id = self._make_episode_id(market.ts)
            self.activate_momentum("Short", market.price, market.ts, episode_id=episode_id)
            self._emit_momentum_armed(
                "Short", episode_id, market, buy_ratio, sell_ratio, threshold, multiplier
            )
        # implicit None -- activation is purely side-effecting

    def _try_pullback_entry(
        self,
        market: MarketSnapshot,
        vol_threshold: tuple[float, float, float],
    ) -> OrderSignal | None:
        near_vwap = abs(market.price - market.vwap) <= self.params.entry_band_points
        exhausted = market.vol_1s <= self.params.exhaustion_vol
        if self.obs is not None:
            self.obs.record_pullback_tick(
                market.price,
                market.vwap,
                near_vwap=near_vwap,
                vol_dried_up=exhausted,
            )

        if not (near_vwap and exhausted):
            return None

        trend_dir = (
            market.trend_dir
            if market.trend_dir in ("Long", "Short", "Flat")
            else "Flat"
        )
        if self.params.structure_filter_enabled:
            structure_state = structure_state_from_market_fields(
                bias=market.structure_bias,
                strength=market.structure_strength,
                in_discount=market.structure_in_discount,
                in_premium=market.structure_in_premium,
                fvg_low=market.structure_fvg_low,
                fvg_high=market.structure_fvg_high,
                sweep_reclaim=market.structure_sweep_reclaim,
            )
        else:
            structure_state = StructureState()
        allowed, veto_reason = regime_allows_entry(
            params=structure_params_from_strategy(self.params),
            trend_dir=trend_dir,
            state=structure_state,
            momentum_dir=self.momentum.direction,
            price=market.price,
        )
        if not allowed:
            direction = self.momentum.direction
            audit_dir = "Buy" if direction == "Long" else "Sell"
            if self.obs is not None:
                if veto_reason == "structure_veto":
                    self.obs.record_structure_veto()
                elif veto_reason == "trend_veto":
                    self.obs.record_trend_veto()
            ctx = self.obs.get_pressure_context() if self.obs is not None else {}
            if veto_reason == "structure_veto":
                veto_dec = DecisionAudit(
                    event_type="structure_veto",
                    ts=market.ts,
                    episode_id=self.momentum.episode_id,
                    direction=audit_dir,
                    price=market.price,
                    vol_1s=market.vol_1s,
                    reason="structure_veto",
                    vwap=round(market.vwap, 1),
                    momentum_dir=direction,
                    **ctx,
                )
                for k, v in self._structure_audit_fields(market).items():
                    setattr(veto_dec, k, v)
            else:
                veto_dec = DecisionAudit(
                    event_type="trend_veto",
                    ts=market.ts,
                    episode_id=self.momentum.episode_id,
                    direction=audit_dir,
                    price=market.price,
                    vol_1s=market.vol_1s,
                    reason="trend_veto",
                    trend_dir=trend_dir,
                    trend_strength=market.trend_strength,
                    **ctx,
                )
            logger.info("DECISION_AUDIT %s", format_decision_audit(veto_dec))
            return None

        if self.obs is not None:
            self.obs.record_momentum_entry()

        direction = self.momentum.direction
        action = "Buy" if direction == "Long" else "Sell"
        audit_dir = "Buy" if direction == "Long" else "Sell"
        base_vol, multiplier, threshold = vol_threshold
        return OrderSignal(
            action,
            1,
            market.price,
            "entry",
            exchange_ts=market.ts,
            audit=self.build_entry_audit(market, audit_dir, multiplier, threshold),
        )

    def build_entry_audit(
        self,
        market: MarketSnapshot,
        direction: str,
        multiplier: float,
        vol_threshold: float,
    ) -> SignalAudit:
        buy_ratio = market.buy_vol_1s / market.vol_1s if market.vol_1s > 0 else 0.0
        sell_ratio = market.sell_vol_1s / market.vol_1s if market.vol_1s > 0 else 0.0
        episode_id = self.momentum.episode_id if self.momentum.active else ""
        elapsed = (market.ts - self.momentum.trigger_time) if self.momentum.active else 0
        dist_vwap = round(abs(market.price - market.vwap), 1) if market.vwap is not None else 0.0
        return SignalAudit(
            intent="entry",
            direction=direction,
            price=market.price,
            ts=market.ts,
            vol_1s=market.vol_1s,
            buy_ratio=round(buy_ratio, 4),
            sell_ratio=round(sell_ratio, 4),
            atr=round(market.current_atr, 2),
            multiplier=multiplier,
            vol_threshold=round(vol_threshold, 1),
            vwap=round(market.vwap, 1),
            reason="pullback",
            trend_dir=market.trend_dir,
            trend_strength=market.trend_strength,
            episode_id=episode_id,
            elapsed_since_arm_sec=elapsed,
            dist_vwap=dist_vwap,
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
        vwap_stop_level: float = 0.0,
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
            vwap_stop_level=round(vwap_stop_level, 1),
            trailing_peak=round(trailing_peak, 1),
        )

    def _effective_trail_points(self, atr: float) -> float:
        if not self.params.atr_trailing_enabled:
            return self.params.trail_points
        return dynamic_trail_points(
            atr,
            floor=self.params.trail_points_floor,
            atr_k=self.params.trail_atr_k,
        )

    def _effective_vwap_stop_distance(self, atr: float) -> float:
        if not self.params.atr_vwap_stop_enabled:
            return self.params.vwap_stop_points
        return dynamic_vwap_stop_distance(
            atr,
            floor=self.params.vwap_stop_points_floor,
            atr_k=self.params.vwap_stop_atr_k,
        )

    def _in_exit_grace_period(self, ts: int, position: PositionSnapshot) -> bool:
        if position.ticks_since_entry < self.params.exit_grace_ticks:
            return True
        if position.entry_exchange_ts <= 0:
            return False
        return (ts - position.entry_exchange_ts) < self.params.exit_grace_sec

    def _stop_loss_hit(
        self,
        market: MarketSnapshot,
        position: PositionSnapshot,
        *,
        is_long: bool,
    ) -> tuple[bool, str]:
        vwap_stop = self._effective_vwap_stop_distance(market.current_atr)
        if is_long:
            hard_hit = market.price <= position.entry_price - self.params.hard_stop_points
            vwap_hit = market.price <= market.vwap - vwap_stop
        else:
            hard_hit = market.price >= position.entry_price + self.params.hard_stop_points
            vwap_hit = market.price >= market.vwap + vwap_stop

        if self._in_exit_grace_period(market.ts, position):
            return (hard_hit, "stop_loss") if hard_hit else (False, "")

        if hard_hit:
            return True, "stop_loss"
        if vwap_hit:
            return True, "stop_loss_vwap"
        return False, ""

    def manage_exit(
        self, market: MarketSnapshot, position: PositionSnapshot
    ) -> tuple[OrderSignal | None, StrategySideEffects]:
        # Tiny defensive normalization (low priority per review)
        pos_dir = position.position_dir if position.position_dir in ("Long", "Short", "Flat") else "Flat"
        trail_pts = self._effective_trail_points(market.current_atr)
        if pos_dir == "Long":
            sl_hit, sl_reason = self._stop_loss_hit(market, position, is_long=True)
            tp_hit = market.price >= position.entry_price + self.params.fixed_tp_points
            trail_hit = market.price <= position.trailing_peak - trail_pts
            if sl_hit or tp_hit or trail_hit:
                reason = sl_reason if sl_hit else "take_profit" if tp_hit else "trailing_stop"
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
                            in_grace=self._in_exit_grace_period(market.ts, position),
                            hard_stop_level=position.entry_price - self.params.hard_stop_points,
                            vwap_stop_level=market.vwap - self._effective_vwap_stop_distance(market.current_atr),
                            trailing_peak=position.trailing_peak,
                        ),
                    ),
                    StrategySideEffects(),
                )
        elif pos_dir == "Short":
            sl_hit, sl_reason = self._stop_loss_hit(market, position, is_long=False)
            tp_hit = market.price <= position.entry_price - self.params.fixed_tp_points
            trail_hit = market.price >= position.trailing_peak + trail_pts
            if sl_hit or tp_hit or trail_hit:
                reason = sl_reason if sl_hit else "take_profit" if tp_hit else "trailing_stop"
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
                            in_grace=self._in_exit_grace_period(market.ts, position),
                            hard_stop_level=position.entry_price + self.params.hard_stop_points,
                            vwap_stop_level=market.vwap + self._effective_vwap_stop_distance(market.current_atr),
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
