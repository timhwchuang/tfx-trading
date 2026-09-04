from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Literal

import yaml

from tfx_trading.bar_store import session_key, session_kind
from tfx_trading.calendar import TradeCalendar
from tfx_trading.indicators.fvg import Fvg
from tfx_trading.indicators.fvg import compute as fvg_compute
from tfx_trading.indicators.smc import DealingRange, SessionLevel, SmcLevels, StructureEvent
from tfx_trading.indicators.smc import compute as smc_compute
from tfx_trading.kbar import KBar
from tfx_trading.strategy.protocol import DecisionContext
from tfx_trading.trading.costs import TICK_SIZE
from tfx_trading.trading.models import Intent, Order, Side

EntryPrice = Literal["top", "ce"]
TakeProfit = Literal["2R", "opposite_liquidity"]

_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "config.yaml"
_ALLOWED_ENTRY: frozenset[str] = frozenset({"top", "ce"})
_ALLOWED_TP: frozenset[str] = frozenset({"2R", "opposite_liquidity"})

_EMPTY_SMC = SmcLevels(
    swings=[],
    pdh=None,
    pdl=None,
    prev_night_high=None,
    prev_night_low=None,
    session_high=None,
    session_low=None,
    last_bar=None,
    dealing_range=None,
    events=[],
)


@dataclass(frozen=True)
class SetupAParams:
    entry_price: EntryPrice = "top"
    min_points: float = 20.0
    stop_buffer: float = 5.0
    take_profit: TakeProfit = "2R"
    require_external: bool = False
    max_daily_losses: int = 2
    max_daily_loss_nt: float = 3000.0
    flatten_time: time = time(13, 40)
    no_trade_before: time = time(9, 15)
    max_hold_bars: int = 10_000
    skip_settlement_day: bool = True
    max_fvg_age_bars: int | None = None


def load_setup_a_params(path: Path | None = None) -> SetupAParams:
    defaults = SetupAParams()
    config_path = path if path is not None else _DEFAULT_CONFIG_PATH
    if not config_path.is_file():
        raise FileNotFoundError(f"找不到設定檔: {config_path}")
    with config_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    section = raw.get("strategy") or {}
    entry_price = section.get("entry_price", defaults.entry_price)
    take_profit = section.get("take_profit", defaults.take_profit)
    if entry_price not in _ALLOWED_ENTRY:
        raise ValueError(f"invalid entry_price: {entry_price!r}")
    if take_profit not in _ALLOWED_TP:
        raise ValueError(f"invalid take_profit: {take_profit!r}")
    age = section.get("max_fvg_age_bars", defaults.max_fvg_age_bars)
    return SetupAParams(
        entry_price=entry_price,
        min_points=float(section.get("min_points", defaults.min_points)),
        stop_buffer=float(section.get("stop_buffer", defaults.stop_buffer)),
        take_profit=take_profit,
        require_external=bool(section.get("require_external", defaults.require_external)),
        max_daily_losses=int(section.get("max_daily_losses", defaults.max_daily_losses)),
        max_daily_loss_nt=float(section.get("max_daily_loss_nt", defaults.max_daily_loss_nt)),
        flatten_time=_as_time(section.get("flatten_time"), defaults.flatten_time),
        no_trade_before=_as_time(section.get("no_trade_before"), defaults.no_trade_before),
        max_hold_bars=int(section.get("max_hold_bars", defaults.max_hold_bars)),
        skip_settlement_day=bool(section.get("skip_settlement_day", defaults.skip_settlement_day)),
        max_fvg_age_bars=None if age is None else int(age),
    )


class SetupA:
    def __init__(
        self,
        params: SetupAParams | None = None,
        calendar: TradeCalendar | None = None,
    ) -> None:
        self._params = params if params is not None else SetupAParams()
        self._calendar = calendar if calendar is not None else TradeCalendar()

    def decide(self, ctx: DecisionContext) -> list[Intent]:
        if _skip_indicators(ctx, self._params, self._calendar):
            return _evaluate(_EMPTY_SMC, [], ctx, self._params, self._calendar)
        bars = list(ctx.bars_5m)
        return _evaluate(
            smc_compute(bars),
            fvg_compute(bars, min_points=0.0),
            ctx,
            self._params,
            self._calendar,
        )


def _evaluate(
    smc: SmcLevels,
    fvgs: list[Fvg],
    ctx: DecisionContext,
    params: SetupAParams,
    calendar: TradeCalendar,
) -> list[Intent]:
    now = ctx.bar_1m.timestamp
    kind = session_kind(now)
    key = session_key(now)
    if kind is None or key is None:
        return []
    session_date = key[0]
    clock = now.time()
    if kind != "day":
        return _hard_exit(ctx)
    if params.skip_settlement_day and calendar.is_settlement_day(session_date):
        return _hard_exit(ctx)
    if clock >= params.flatten_time:
        return _hard_exit(ctx)
    if ctx.position.side is not None:
        if _time_stop_hit(ctx, params) and not _has_pending_flatten(ctx):
            return [_flatten_intent(ctx)]
        return []
    entry = _pending_entry(ctx)
    halted = _is_halted(ctx, params, session_date)
    if entry is not None:
        if halted:
            return [_cancel_intent(ctx, entry)]
        if not _thesis_live(smc, fvgs, ctx, params, entry):
            return [_cancel_intent(ctx, entry)]
        return []
    if any(order.kind in {"limit", "stop"} for order in ctx.pending):
        return []
    if halted or clock < params.no_trade_before:
        return []
    return _arm_setup(smc, fvgs, ctx, params, session_date)


def _select_active_fvg(
    fvgs: list[Fvg],
    direction: Literal["bullish", "bearish"],
    interact_ts: datetime,
    min_points: float,
    max_age_bars: int | None,
    ctx: DecisionContext,
) -> Fvg | None:
    now = ctx.bar_1m.timestamp
    chosen: Fvg | None = None
    for fvg in fvgs:
        if fvg.direction != direction:
            continue
        if fvg.state not in ("untouched", "mitigated"):
            continue
        if fvg.size < min_points:
            continue
        if fvg.formed_at < interact_ts:
            continue
        if max_age_bars is not None:
            age = _count_day_5m(ctx.bars_5m, fvg.formed_at, now)
            if age > max_age_bars:
                continue
        if chosen is None or fvg.formed_at >= chosen.formed_at:
            chosen = fvg
    return chosen


def preferred_event(
    events: list[StructureEvent],
    direction: Literal["bullish", "bearish"],
    interact_ts: datetime,
    require_external: bool,
) -> StructureEvent | None:
    matching = [
        ev
        for ev in events
        if ev.direction == direction
        and ev.ts >= interact_ts
        and (not require_external or ev.scope == "external")
    ]
    if not matching:
        return None
    for ev in matching:
        if ev.kind == "choch":
            return ev
    return matching[0]


def _arm_setup(
    smc: SmcLevels,
    fvgs: list[Fvg],
    ctx: DecisionContext,
    params: SetupAParams,
    session_date: date,
) -> list[Intent]:
    rng = smc.dealing_range
    if rng is None:
        return []
    if rng.position == "discount":
        return _bracket_for_side("long", smc, fvgs, ctx, params, session_date)
    if rng.position == "premium":
        return _bracket_for_side("short", smc, fvgs, ctx, params, session_date)
    return []


def _bracket_for_side(
    side: Side,
    smc: SmcLevels,
    fvgs: list[Fvg],
    ctx: DecisionContext,
    params: SetupAParams,
    session_date: date,
) -> list[Intent]:
    swept = _swept_level(smc, side)
    if swept is None or swept.interact_ts is None:
        return []
    direction: Literal["bullish", "bearish"] = "bullish" if side == "long" else "bearish"
    if preferred_event(smc.events, direction, swept.interact_ts, params.require_external) is None:
        return []
    fvg = _select_active_fvg(
        fvgs,
        direction,
        swept.interact_ts,
        params.min_points,
        params.max_fvg_age_bars,
        ctx,
    )
    if fvg is None:
        return []
    sweep_bar = _bar_at(ctx.bars_5m, swept.interact_ts)
    if sweep_bar is None:
        return []
    entry = _round_tick(_fvg_limit(fvg, params))
    extreme = sweep_bar.low if side == "long" else sweep_bar.high
    stop = _structural_stop(side, extreme, params.stop_buffer)
    if (side == "long" and stop >= entry) or (side == "short" and stop <= entry):
        return []
    target = _take_profit_price(side, entry, stop, smc, params)
    expire_at = datetime.combine(session_date, params.flatten_time)
    opp: Side = "short" if side == "long" else "long"
    stamp = _stamp(ctx.bar_1m.timestamp)
    return [
        Intent(
            intent_id=f"{stamp}-entry",
            kind="place_limit",
            side=side,
            price=entry,
            qty=1,
            expire_at=expire_at,
            target_intent_id=None,
        ),
        Intent(
            intent_id=f"{stamp}-stop",
            kind="place_stop",
            side=opp,
            price=stop,
            qty=1,
            expire_at=None,
            target_intent_id=None,
        ),
        Intent(
            intent_id=f"{stamp}-tp",
            kind="place_limit",
            side=opp,
            price=target,
            qty=1,
            expire_at=None,
            target_intent_id=None,
        ),
    ]


def _thesis_live(
    smc: SmcLevels,
    fvgs: list[Fvg],
    ctx: DecisionContext,
    params: SetupAParams,
    entry: Order,
) -> bool:
    side = entry.side
    if not _bias_ok(smc.dealing_range, side):
        return False
    if _swept_level(smc, side) is None:
        return False
    return _matching_live_fvg(fvgs, entry, params) is not None


def _matching_live_fvg(fvgs: list[Fvg], entry: Order, params: SetupAParams) -> Fvg | None:
    direction: Literal["bullish", "bearish"] = "bullish" if entry.side == "long" else "bearish"
    for fvg in fvgs:
        if fvg.direction != direction:
            continue
        if fvg.state not in ("untouched", "mitigated"):
            continue
        if entry.price == _round_tick(_fvg_limit(fvg, params)):
            return fvg
    return None


def _swept_level(smc: SmcLevels, side: Side) -> SessionLevel | None:
    levels = (smc.pdl, smc.prev_night_low) if side == "long" else (smc.pdh, smc.prev_night_high)
    swept = [
        level
        for level in levels
        if level is not None and level.interact == "swept" and level.interact_ts is not None
    ]
    if not swept:
        return None
    return max(swept, key=lambda level: level.interact_ts or datetime.min)


def _bias_ok(rng: DealingRange | None, side: Side) -> bool:
    if rng is None:
        return False
    if side == "long":
        return rng.position == "discount"
    return rng.position == "premium"


def _take_profit_price(
    side: Side,
    entry: float,
    stop: float,
    smc: SmcLevels,
    params: SetupAParams,
) -> float:
    risk = abs(entry - stop)
    r2 = _round_tick(entry + 2.0 * risk if side == "long" else entry - 2.0 * risk)
    if params.take_profit == "2R":
        return r2
    if side == "long":
        cands = [
            level.price
            for level in (smc.session_high, smc.pdh)
            if level is not None and level.price > entry
        ]
        if cands:
            rounded = _round_tick(min(cands))
            if rounded > entry:
                return rounded
        return r2
    cands = [
        level.price
        for level in (smc.session_low, smc.pdl)
        if level is not None and level.price < entry
    ]
    if cands:
        rounded = _round_tick(max(cands))
        if rounded < entry:
            return rounded
    return r2


def _fvg_limit(fvg: Fvg, params: SetupAParams) -> float:
    return fvg.top if params.entry_price == "top" else fvg.ce


def _hard_exit(ctx: DecisionContext) -> list[Intent]:
    intents: list[Intent] = []
    entry = _pending_entry(ctx)
    if entry is not None:
        intents.append(_cancel_intent(ctx, entry))
    if ctx.position.side is not None and not _has_pending_flatten(ctx):
        intents.append(_flatten_intent(ctx))
    return intents


def _pending_entry(ctx: DecisionContext) -> Order | None:
    if ctx.position.side is not None:
        return None
    limits = [order for order in ctx.pending if order.kind == "limit"]
    timed = [order for order in limits if order.expire_at is not None]
    if timed:
        return timed[0]
    stops = [order for order in ctx.pending if order.kind == "stop"]
    if stops:
        stop_side = stops[0].side
        entries = [order for order in limits if order.side != stop_side]
        return entries[0] if entries else None
    if len(limits) == 1:
        return limits[0]
    return None


def _has_pending_flatten(ctx: DecisionContext) -> bool:
    return any(order.kind == "flatten" for order in ctx.pending)


def _is_halted(ctx: DecisionContext, params: SetupAParams, session_date: date) -> bool:
    day = [trade for trade in ctx.closed_trades if trade.exit_ts.date() == session_date]
    if sum(1 for trade in day if trade.pnl_nt < 0) >= params.max_daily_losses:
        return True
    return sum(trade.pnl_nt for trade in day) <= -params.max_daily_loss_nt


def _time_stop_hit(ctx: DecisionContext, params: SetupAParams) -> bool:
    if ctx.entry_ts is None:
        return False
    held = _count_day_5m(ctx.bars_5m, ctx.entry_ts, ctx.bar_1m.timestamp)
    return held >= params.max_hold_bars


def _count_day_5m(bars: tuple[KBar, ...], start_exclusive: datetime, now: datetime) -> int:
    return sum(
        1
        for bar in bars
        if session_kind(bar.timestamp) == "day" and start_exclusive < bar.timestamp <= now
    )


def _skip_indicators(
    ctx: DecisionContext,
    params: SetupAParams,
    calendar: TradeCalendar,
) -> bool:
    now = ctx.bar_1m.timestamp
    kind = session_kind(now)
    key = session_key(now)
    if kind != "day":
        return True
    if key is not None and params.skip_settlement_day and calendar.is_settlement_day(key[0]):
        return True
    return now.time() >= params.flatten_time


def _flatten_intent(ctx: DecisionContext) -> Intent:
    assert ctx.position.side is not None
    side: Side = "short" if ctx.position.side == "long" else "long"
    return Intent(
        intent_id=f"{_stamp(ctx.bar_1m.timestamp)}-flatten",
        kind="flatten",
        side=side,
        price=None,
        qty=1,
        expire_at=None,
        target_intent_id=None,
    )


def _cancel_intent(ctx: DecisionContext, entry: Order) -> Intent:
    return Intent(
        intent_id=f"{_stamp(ctx.bar_1m.timestamp)}-cancel",
        kind="cancel",
        side=None,
        price=None,
        qty=1,
        expire_at=None,
        target_intent_id=entry.intent_id,
    )


def _bar_at(bars: tuple[KBar, ...], ts: datetime) -> KBar | None:
    for bar in bars:
        if bar.timestamp == ts:
            return bar
    return None


def _structural_stop(side: Side, extreme: float, buffer: float) -> float:
    """Sweep-bar extreme ± pad. Extreme is that K's high/low, not a SessionLevel price."""
    if side == "long":
        return _round_tick(extreme - buffer)
    return _round_tick(extreme + buffer)


def _round_tick(price: float) -> float:
    return round(price / TICK_SIZE) * TICK_SIZE


def _stamp(ts: datetime) -> str:
    return ts.strftime("%Y%m%d%H%M")


def _as_time(value: object, default: time) -> time:
    if value is None:
        return default
    if isinstance(value, time):
        return value
    text = str(value)
    hours, minutes = text.split(":")[:2]
    return time(int(hours), int(minutes))


__all__ = [
    "SetupA",
    "SetupAParams",
    "_EMPTY_SMC",
    "_evaluate",
    "_select_active_fvg",
    "_skip_indicators",
    "load_setup_a_params",
    "preferred_event",
]
