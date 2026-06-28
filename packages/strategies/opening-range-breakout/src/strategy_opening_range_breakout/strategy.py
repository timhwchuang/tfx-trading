"""Opening Range Breakout: session-anchored first break, ATR-scaled exits."""

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

from strategy_opening_range_breakout.atr_utils import dynamic_atr_distance
from strategy_opening_range_breakout.orb_logic import (
    MinuteBar,
    OrbDayState,
    on_bar_closed,
    reset_day_state,
)
from strategy_opening_range_breakout.params import OrbParams
from strategy_opening_range_breakout.session_atr import SessionAtrTracker

logger = logging.getLogger(__name__)


class _MinuteBarBuilder:
    def __init__(self) -> None:
        self._minute_key: tuple[int, int, int, int, int] | None = None
        self._open = 0.0
        self._high = 0.0
        self._low = 0.0
        self._close = 0.0
        self._bar_time: datetime.time | None = None

    def feed(self, market: MarketSnapshot) -> MinuteBar | None:
        local_dt = market.dt
        if local_dt.tzinfo is not None:
            local_dt = local_dt.astimezone().replace(tzinfo=None)
        minute_key = (
            local_dt.year,
            local_dt.month,
            local_dt.day,
            local_dt.hour,
            local_dt.minute,
        )
        price = market.price
        if self._minute_key is None:
            self._start_bar(minute_key, local_dt.time(), price)
            return None

        if minute_key != self._minute_key:
            completed = MinuteBar(
                bar_time=self._bar_time or local_dt.time(),
                open=self._open,
                high=self._high,
                low=self._low,
                close=self._close,
            )
            self._start_bar(minute_key, local_dt.time(), price)
            return completed

        self._high = max(self._high, price)
        self._low = min(self._low, price)
        self._close = price
        return None

    def _start_bar(
        self,
        minute_key: tuple[int, int, int, int, int],
        bar_time: datetime.time,
        price: float,
    ) -> None:
        self._minute_key = minute_key
        self._bar_time = bar_time
        self._open = price
        self._high = price
        self._low = price
        self._close = price


class OpeningRangeBreakoutStrategy(BaseStrategy):
    """ORB: first break of opening range; ≤1 entry per session day."""

    def __init__(
        self,
        params: OrbParams,
        obs: Any | None = None,
    ) -> None:
        super().__init__()
        self.params = params
        self.obs = obs
        self._day = OrbDayState()
        self._bar_builder = _MinuteBarBuilder()
        self._session_atr = SessionAtrTracker(
            atr_period=params.atr_period,
            min_atr_floor=params.min_atr_threshold,
        )
        self._entry_atr = 0.0

    def reset(self) -> None:
        self._day = OrbDayState()
        self._bar_builder = _MinuteBarBuilder()
        self._session_atr.reset()
        self._entry_atr = 0.0

    def _trading_date(self, market: MarketSnapshot) -> datetime.date:
        local_dt = market.dt
        if local_dt.tzinfo is not None:
            local_dt = local_dt.astimezone().replace(tzinfo=None)
        return local_dt.date()

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
        range_high: float,
        range_low: float,
        entry_price: float | None = None,
        entry_atr: float | None = None,
    ) -> SignalAudit:
        return SignalAudit(
            intent="entry",
            direction=direction,
            price=entry_price if entry_price is not None else market.price,
            ts=market.ts,
            atr=round(entry_atr if entry_atr is not None else market.current_atr, 2),
            vwap=round(market.vwap, 1),
            reason="opening_range_breakout",
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
        return self.params.hard_stop_atr_k * atr

    def _effective_tp(self, atr: float) -> float:
        return self.params.tp_atr_k * atr

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

    def _pos_to_audit_dir(self, pos_dir: str) -> str:
        return "Buy" if pos_dir == "Long" else "Sell"

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
        del vol_threshold
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

        return self._try_orb_entry(market), effects

    def _try_orb_entry(self, market: MarketSnapshot) -> OrderSignal | None:
        day = self._trading_date(market)
        if self._day.trading_date != day:
            reset_day_state(self._day, day)
            self._bar_builder = _MinuteBarBuilder()
            self._session_atr.reset()

        completed = self._bar_builder.feed(market)
        if completed is None:
            return None

        bar_atr = self._session_atr.on_bar_closed(completed)
        completed = MinuteBar(
            bar_time=completed.bar_time,
            open=completed.open,
            high=completed.high,
            low=completed.low,
            close=completed.close,
            atr=bar_atr,
        )

        direction = on_bar_closed(
            self._day,
            completed,
            session_start=self.params.session_start,
            range_minutes=self.params.range_minutes,
            buffer_atr_k=self.params.buffer_atr_k,
            min_range_atr_k=self.params.orb_min_range_atr_k,
            atr=bar_atr,
            min_atr_floor=self.params.min_atr_threshold,
        )
        if direction is None:
            return None

        entry_price = completed.close
        fill_price = market.price
        entry_atr = bar_atr
        self._entry_atr = entry_atr

        audit_dir = self._pos_to_audit_dir(direction)
        if self.obs is not None:
            self.obs.record_momentum_trigger()
            self.obs.record_momentum_entry()

        logger.info(
            "MOMENTUM %s opening_range_breakout | range=%.1f-%.1f rm=%s bk=%.2f",
            direction,
            self._day.range_low,
            self._day.range_high,
            self.params.range_minutes,
            self.params.buffer_atr_k,
        )

        return OrderSignal(
            audit_dir,
            1,
            fill_price,
            "entry",
            exchange_ts=market.ts,
            audit=self.build_entry_audit(
                market,
                audit_dir,
                range_high=self._day.range_high,
                range_low=self._day.range_low,
                entry_price=entry_price,
                entry_atr=entry_atr,
            ),
        )

    def manage_exit(
        self, market: MarketSnapshot, position: PositionSnapshot
    ) -> tuple[OrderSignal | None, StrategySideEffects]:
        pos_dir = (
            position.position_dir
            if position.position_dir in ("Long", "Short", "Flat")
            else "Flat"
        )
        atr = self._entry_atr if self._entry_atr > 0 else market.current_atr
        hard_dist = self._effective_hard_stop(atr)
        tp_dist = self._effective_tp(atr)
        trail_pts = self._effective_trail(atr)
        in_grace = self._in_exit_grace_period(market.ts, position)

        if position.entry_exchange_ts > 0:
            held = market.ts - position.entry_exchange_ts
            if held >= self.params.orb_max_hold_sec:
                action = "Sell" if pos_dir == "Long" else "Buy"
                return (
                    OrderSignal(
                        action,
                        1,
                        market.price,
                        "exit",
                        exchange_ts=market.ts,
                        audit=self.build_exit_audit(
                            market,
                            action,
                            "time_stop",
                            entry_price=position.entry_price,
                            hold_ticks=position.ticks_since_entry,
                        ),
                    ),
                    StrategySideEffects(),
                )

        if pos_dir == "Long":
            hard_hit = market.price <= position.entry_price - hard_dist
            tp_hit = not in_grace and market.price >= position.entry_price + tp_dist
            trail_hit = (
                self.params.atr_trailing_enabled
                and not in_grace
                and market.price <= position.trailing_peak - trail_pts
            )
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
            trail_hit = (
                self.params.atr_trailing_enabled
                and not in_grace
                and market.price >= position.trailing_peak + trail_pts
            )
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
