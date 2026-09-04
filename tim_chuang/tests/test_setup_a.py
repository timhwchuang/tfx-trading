from __future__ import annotations

from datetime import datetime, time, timedelta

from tfx_trading.backtest.config import BacktestConfig
from tfx_trading.backtest.engine import run
from tfx_trading.calendar import TradeCalendar
from tfx_trading.indicators.fvg import Fvg
from tfx_trading.indicators.fvg import compute as fvg_compute
from tfx_trading.indicators.smc import DealingRange, SessionLevel, SmcLevels, StructureEvent
from tfx_trading.indicators.smc import compute as smc_compute
from tfx_trading.kbar import KBar
from tfx_trading.strategy.protocol import DecisionContext
from tfx_trading.strategy.setup_a import (
    SetupA,
    SetupAParams,
    _below_cost_floor,
    _evaluate,
    load_setup_a_params,
)
from tfx_trading.trading.costs import CostConfig
from tfx_trading.trading.models import Intent, Order, Position, TradeRecord

_CAL = TradeCalendar()
SWEEP_TS = datetime(2026, 8, 17, 9, 30)
FVG_TS = datetime(2026, 8, 17, 9, 40)
NOW = datetime(2026, 8, 17, 10, 0)


def _k(ts: datetime, high: float, low: float, close: float | None = None) -> KBar:
    close_px = high if close is None else close
    return KBar(
        timestamp=ts,
        open=close_px,
        high=high,
        low=low,
        close=close_px,
        volume=1,
        amount=close_px,
    )


def _level(
    kind: str,
    price: float,
    interact: str | None,
    interact_ts: datetime | None,
) -> SessionLevel:
    return SessionLevel(
        kind=kind,  # type: ignore[arg-type]
        price=price,
        source_ts=interact_ts or datetime(2026, 8, 14, 13, 45),
        developing=False,
        interact=interact,  # type: ignore[arg-type]
        interact_ts=interact_ts,
    )


def _range(position: str, high: float = 20100.0, low: float = 19800.0) -> DealingRange:
    return DealingRange(
        high=high,
        high_ts=datetime(2026, 8, 17, 9, 20),
        low=low,
        low_ts=datetime(2026, 8, 17, 9, 25),
        eq=(high + low) / 2.0,
        position=position,  # type: ignore[arg-type]
    )


def _event(
    ts: datetime,
    direction: str = "bullish",
    kind: str = "choch",
    scope: str = "internal",
) -> StructureEvent:
    return StructureEvent(
        kind=kind,  # type: ignore[arg-type]
        direction=direction,  # type: ignore[arg-type]
        ts=ts,
        broken_price=20000.0,
        broken_swing_ts=ts,
        scope=scope,  # type: ignore[arg-type]
    )


def _fvg(
    direction: str,
    top: float,
    bottom: float,
    formed_at: datetime,
    state: str = "untouched",
    size: float | None = None,
) -> Fvg:
    return Fvg(
        direction=direction,  # type: ignore[arg-type]
        top=top,
        bottom=bottom,
        ce=(top + bottom) / 2.0,
        size=top - bottom if size is None else size,
        gap_start_ts=formed_at,
        formed_at=formed_at,
        session="day",
        state=state,  # type: ignore[arg-type]
        mitigated_ts=None,
        filled_ts=None,
    )


def _smc(
    *,
    dealing: DealingRange | None,
    pdl: SessionLevel | None = None,
    pdh: SessionLevel | None = None,
    prev_night_low: SessionLevel | None = None,
    prev_night_high: SessionLevel | None = None,
    events: list[StructureEvent] | None = None,
    session_high: SessionLevel | None = None,
    session_low: SessionLevel | None = None,
) -> SmcLevels:
    return SmcLevels(
        swings=[],
        pdh=pdh,
        pdl=pdl,
        prev_night_high=prev_night_high,
        prev_night_low=prev_night_low,
        session_high=session_high,
        session_low=session_low,
        last_bar=None,
        dealing_range=dealing,
        events=events or [],
    )


def _bars() -> tuple[KBar, ...]:
    return (
        _k(datetime(2026, 8, 17, 9, 15), 20000.0, 19900.0, 19950.0),
        _k(SWEEP_TS, 19950.0, 19790.0, 19920.0),
        _k(FVG_TS, 20050.0, 19980.0, 20020.0),
        _k(NOW, 20040.0, 19990.0, 20010.0),
    )


def _long_smc(**kwargs: object) -> SmcLevels:
    base = dict(
        dealing=_range("discount"),
        pdl=_level("pdl", 19900.0, "swept", SWEEP_TS),
        events=[_event(SWEEP_TS)],
    )
    base.update(kwargs)
    return _smc(**base)  # type: ignore[arg-type]


def _long_fvg(**kwargs: object) -> Fvg:
    fields = dict(
        direction="bullish",
        top=19920.0,
        bottom=19850.0,
        formed_at=FVG_TS,
    )
    fields.update(kwargs)
    return _fvg(**fields)  # type: ignore[arg-type]


def _ctx(
    ts: datetime = NOW,
    *,
    position: Position | None = None,
    pending: tuple[Order, ...] = (),
    closed: tuple[TradeRecord, ...] = (),
    entry_ts: datetime | None = None,
    bars_5m: tuple[KBar, ...] | None = None,
) -> DecisionContext:
    bar = _k(ts, 20040.0, 19990.0, 20010.0)
    if bars_5m is not None:
        prefix = bars_5m
    elif ts == NOW:
        prefix = _bars()
        bar = prefix[-1]
    else:
        prefix = _bars() + (bar,)
    return DecisionContext(
        bar_1m=bar,
        bars_5m=prefix,
        position=position if position is not None else Position(side=None, qty=0, avg_price=None),
        pending=pending,
        closed_trades=closed,
        entry_ts=entry_ts,
    )


def _order(
    oid: str,
    kind: str,
    side: str,
    price: float | None,
    expire_at: datetime | None = None,
) -> Order:
    return Order(
        order_id=oid,
        intent_id=oid,
        kind=kind,  # type: ignore[arg-type]
        side=side,  # type: ignore[arg-type]
        price=price,
        qty=1,
        expire_at=expire_at,
        status="pending",
        reject_reason=None,
    )


def _trade(pnl: float, exit_ts: datetime = NOW) -> TradeRecord:
    return TradeRecord(
        side="long",
        entry_ts=datetime(2026, 8, 17, 9, 50),
        entry_price=20000.0,
        exit_ts=exit_ts,
        exit_price=19900.0,
        qty=1,
        pnl_nt=pnl,
        r_multiple=-1.0,
        reason="stop",
    )


def _run(
    smc: SmcLevels,
    fvgs: list[Fvg],
    ctx: DecisionContext,
    params: SetupAParams | None = None,
) -> list[Intent]:
    return _evaluate(smc, fvgs, ctx, params if params is not None else SetupAParams(), _CAL)


def _kinds(intents: list[Intent]) -> list[str]:
    return [intent.kind for intent in intents]


def test_load_setup_a_params_defaults() -> None:
    params = load_setup_a_params()
    assert params.entry_price == "top"
    assert params.min_points == 20.0
    assert params.flatten_time == time(13, 40)
    assert params.no_trade_before == time(9, 15)
    assert params.skip_settlement_day is True
    assert params.max_fvg_age_bars is None
    assert params.min_r_points == 15.0


def test_long_happy_path_three_intents() -> None:
    intents = _run(_long_smc(), [_long_fvg()], _ctx())
    assert _kinds(intents) == ["place_limit", "place_stop", "place_limit"]
    entry, stop, tp = intents
    assert entry.side == "long"
    assert entry.price == 19920.0
    assert entry.expire_at == datetime(2026, 8, 17, 13, 40)
    assert stop.expire_at is None
    assert tp.expire_at is None
    assert stop.side == "short"
    assert stop.price == 19785.0
    assert tp.price == 20190.0
    assert entry.price is not None and stop.price is not None
    assert abs(entry.price - stop.price) == 135.0
    assert entry.intent_id == "202608171000-entry"


def test_prices_round_to_tick() -> None:
    fvg = _long_fvg(top=19920.4, bottom=19850.4)
    params = SetupAParams(entry_price="ce")
    intents = _run(_long_smc(), [fvg], _ctx(), params)
    assert intents[0].price == 19885.0
    assert intents[1].price is not None
    assert intents[2].price is not None
    assert intents[1].price == round(intents[1].price)
    assert intents[2].price == round(intents[2].price)


def test_opposite_liquidity_rounds_off_entry_falls_back_to_2r() -> None:
    params = SetupAParams(take_profit="opposite_liquidity")
    smc = _long_smc(session_high=_level("session_high", 19920.4, None, NOW))
    intents = _run(smc, [_long_fvg()], _ctx(), params)
    assert intents[0].price == 19920.0
    assert intents[2].price == 20190.0
    assert intents[2].price > intents[0].price


def test_opposite_liquidity_uses_nearest_level() -> None:
    params = SetupAParams(take_profit="opposite_liquidity")
    smc = _long_smc(
        session_high=_level("session_high", 20100.0, None, NOW),
        pdh=_level("pdh", 20200.0, "untouched", None),
    )
    intents = _run(smc, [_long_fvg()], _ctx(), params)
    assert intents[2].price == 20100.0


def test_opposite_liquidity_short_round_falls_back_to_2r() -> None:
    params = SetupAParams(take_profit="opposite_liquidity")
    sweep = SWEEP_TS
    smc = _smc(
        dealing=_range("premium"),
        pdh=_level("pdh", 20100.0, "swept", sweep),
        events=[_event(sweep, direction="bearish")],
        session_low=_level("session_low", 20049.6, None, NOW),
    )
    fvg = _fvg("bearish", top=20050.0, bottom=19980.0, formed_at=FVG_TS)
    bars = (
        _k(sweep, 20120.0, 20040.0, 20060.0),
        _k(NOW, 20080.0, 20020.0, 20040.0),
    )
    intents = _run(smc, [fvg], _ctx(bars_5m=bars), params)
    assert intents[0].price == 20050.0
    assert intents[2].price == 19900.0
    assert intents[2].price < intents[0].price


def test_wrong_bias_no_entry() -> None:
    smc = _long_smc(dealing=_range("premium"))
    assert _run(smc, [_long_fvg()], _ctx()) == []


def test_taken_does_not_qualify() -> None:
    smc = _long_smc(pdl=_level("pdl", 19900.0, "taken", SWEEP_TS))
    assert _run(smc, [_long_fvg()], _ctx()) == []


def test_same_bar_sweep_and_event_allowed() -> None:
    smc = _long_smc(events=[_event(SWEEP_TS, kind="bos")])
    intents = _run(smc, [_long_fvg()], _ctx())
    assert len(intents) == 3


def test_event_before_sweep_rejected() -> None:
    smc = _long_smc(events=[_event(datetime(2026, 8, 17, 9, 25))])
    assert _run(smc, [_long_fvg()], _ctx()) == []


def test_fvg_too_small() -> None:
    assert _run(_long_smc(), [_long_fvg(top=19865.0, bottom=19850.0)], _ctx()) == []


def test_fvg_filled_skipped() -> None:
    assert _run(_long_smc(), [_long_fvg(state="filled")], _ctx()) == []


def test_fvg_formed_before_sweep_skipped() -> None:
    assert _run(_long_smc(), [_long_fvg(formed_at=datetime(2026, 8, 17, 9, 20))], _ctx()) == []


def test_fvg_too_old() -> None:
    params = SetupAParams(max_fvg_age_bars=0)
    assert _run(_long_smc(), [_long_fvg()], _ctx(), params) == []


def test_require_external_blocks_internal_on_new_entry() -> None:
    params = SetupAParams(require_external=True)
    smc = _long_smc(events=[_event(SWEEP_TS, scope="internal")])
    assert _run(smc, [_long_fvg()], _ctx(), params) == []
    smc_ext = _long_smc(events=[_event(SWEEP_TS, scope="external")])
    assert len(_run(smc_ext, [_long_fvg()], _ctx(), params)) == 3


def test_daily_loss_count_halts() -> None:
    closed = (
        _trade(-100.0, datetime(2026, 8, 17, 9, 50)),
        _trade(-80.0, datetime(2026, 8, 17, 9, 55)),
    )
    assert _run(_long_smc(), [_long_fvg()], _ctx(closed=closed)) == []


def test_halt_cancels_pending() -> None:
    expire = datetime(2026, 8, 17, 13, 40)
    pending = (
        _order("e", "limit", "long", 19920.0, expire_at=expire),
        _order("s", "stop", "short", 19845.0),
        _order("t", "limit", "short", 20070.0),
    )
    closed = (
        _trade(-100.0, datetime(2026, 8, 17, 9, 50)),
        _trade(-80.0, datetime(2026, 8, 17, 9, 55)),
    )
    intents = _run(_long_smc(), [_long_fvg()], _ctx(pending=pending, closed=closed))
    assert _kinds(intents) == ["cancel"]
    assert intents[0].target_intent_id == "e"


def test_daily_loss_nt_uses_exit_date() -> None:
    params = SetupAParams(max_daily_loss_nt=50.0, max_daily_losses=10)
    closed = (_trade(-80.0, datetime(2026, 8, 17, 9, 50)),)
    assert _run(_long_smc(), [_long_fvg()], _ctx(closed=closed), params) == []
    other_day = (_trade(-80.0, datetime(2026, 8, 16, 13, 30)),)
    assert len(_run(_long_smc(), [_long_fvg()], _ctx(closed=other_day), params)) == 3


def test_settlement_day_hard_exit() -> None:
    ts = datetime(2026, 2, 23, 10, 0)
    pos = Position(side="long", qty=1, avg_price=20000.0)
    intents = _run(_EMPTY_IF_NEEDED(), [], _ctx(ts, position=pos, bars_5m=(_k(ts, 1, 1, 1),)))
    assert _kinds(intents) == ["flatten"]


def _EMPTY_IF_NEEDED() -> SmcLevels:
    return _smc(dealing=None)


def test_normal_wednesday_not_settlement() -> None:
    ts = datetime(2026, 8, 12, 10, 0)
    bar = _k(ts, 20040.0, 19990.0, 20010.0)
    sweep = datetime(2026, 8, 12, 9, 30)
    bars = (_k(sweep, 19950.0, 19790.0, 19920.0), bar)
    smc = _smc(
        dealing=_range("discount"),
        pdl=_level("pdl", 19900.0, "swept", sweep),
        events=[_event(sweep)],
    )
    fvg = _long_fvg(formed_at=datetime(2026, 8, 12, 9, 40))
    intents = _run(smc, [fvg], _ctx(ts, bars_5m=bars))
    assert len(intents) == 3


def test_no_trade_before_0915() -> None:
    early = datetime(2026, 8, 17, 8, 50)
    early_ctx = _ctx(early, bars_5m=_bars() + (_k(early, 1, 1, 1),))
    assert _run(_long_smc(), [_long_fvg()], early_ctx) == []
    at_open = datetime(2026, 8, 17, 9, 15)
    bar = _k(at_open, 20040.0, 19990.0, 20010.0)
    assert len(_run(_long_smc(), [_long_fvg()], _ctx(at_open, bars_5m=_bars() + (bar,)))) == 3


def test_time_stop_flattens() -> None:
    params = SetupAParams(max_hold_bars=2)
    pos = Position(side="long", qty=1, avg_price=19920.0)
    entry_ts = datetime(2026, 8, 17, 9, 45)
    later = datetime(2026, 8, 17, 10, 5)
    bars = _bars() + (_k(later, 20040.0, 19990.0, 20010.0),)
    intents = _run(
        _long_smc(),
        [_long_fvg()],
        _ctx(later, position=pos, entry_ts=entry_ts, bars_5m=bars),
        params,
    )
    assert _kinds(intents) == ["flatten"]
    held = [bar.timestamp for bar in bars if entry_ts < bar.timestamp <= later]
    assert held == [NOW, later]


def test_time_stop_one_bar_does_not_flatten() -> None:
    params = SetupAParams(max_hold_bars=2)
    pos = Position(side="long", qty=1, avg_price=19920.0)
    intents = _run(
        _long_smc(),
        [_long_fvg()],
        _ctx(position=pos, entry_ts=datetime(2026, 8, 17, 9, 45)),
        params,
    )
    assert intents == []


def test_flatten_at_1340() -> None:
    ts = datetime(2026, 8, 17, 13, 40)
    pos = Position(side="long", qty=1, avg_price=19920.0)
    intents = _run(_EMPTY_IF_NEEDED(), [], _ctx(ts, position=pos, bars_5m=(_k(ts, 1, 1, 1),)))
    assert _kinds(intents) == ["flatten"]
    assert intents[0].side == "short"


def test_already_in_position_no_second_bracket() -> None:
    pos = Position(side="long", qty=1, avg_price=19920.0)
    ctx = _ctx(position=pos, entry_ts=datetime(2026, 8, 17, 9, 50))
    assert _run(_long_smc(), [_long_fvg()], ctx) == []


def test_pending_not_doubled() -> None:
    pending = (
        _order("e", "limit", "long", 19920.0),
        _order("s", "stop", "short", 19845.0),
        _order("t", "limit", "short", 20070.0),
    )
    assert _run(_long_smc(), [_long_fvg()], _ctx(pending=pending)) == []


def test_entry_plus_tp_without_stop_does_not_rearm() -> None:
    expire = datetime(2026, 8, 17, 13, 40)
    pending = (
        _order("e", "limit", "long", 19920.0, expire_at=expire),
        _order("t", "limit", "short", 20070.0),
    )
    assert _run(_long_smc(), [_long_fvg()], _ctx(pending=pending)) == []


def test_newer_fvg_does_not_cancel() -> None:
    pending = (
        _order("e", "limit", "long", 19920.0),
        _order("s", "stop", "short", 19845.0),
    )
    newer = _long_fvg(top=19940.0, bottom=19860.0, formed_at=datetime(2026, 8, 17, 9, 50))
    assert _run(_long_smc(), [_long_fvg(), newer], _ctx(pending=pending)) == []


def test_scope_flip_does_not_cancel_pending() -> None:
    pending = (
        _order("e", "limit", "long", 19920.0),
        _order("s", "stop", "short", 19845.0),
    )
    smc = _long_smc(events=[_event(SWEEP_TS, scope="internal")])
    params = SetupAParams(require_external=True)
    assert _run(smc, [_long_fvg()], _ctx(pending=pending), params) == []


def test_invalidation_cancels_only() -> None:
    pending = (
        _order("e", "limit", "long", 19920.0),
        _order("s", "stop", "short", 19845.0),
    )
    filled = _long_fvg(state="filled")
    intents = _run(_long_smc(), [filled], _ctx(pending=pending))
    assert _kinds(intents) == ["cancel"]
    assert intents[0].target_intent_id == "e"


def test_halt_does_not_flatten_open() -> None:
    pos = Position(side="long", qty=1, avg_price=19920.0)
    closed = (_trade(-100.0), _trade(-80.0))
    assert (
        _run(
            _long_smc(),
            [_long_fvg()],
            _ctx(position=pos, closed=closed, entry_ts=datetime(2026, 8, 17, 9, 50)),
        )
        == []
    )


def test_halt_still_time_stops() -> None:
    params = SetupAParams(max_hold_bars=1)
    pos = Position(side="long", qty=1, avg_price=19920.0)
    closed = (_trade(-100.0), _trade(-80.0))
    intents = _run(
        _long_smc(),
        [_long_fvg()],
        _ctx(position=pos, closed=closed, entry_ts=datetime(2026, 8, 17, 9, 45)),
        params,
    )
    assert _kinds(intents) == ["flatten"]


def test_same_bar_close_then_rearm_unless_halt() -> None:
    one_loss = (_trade(-50.0),)
    intents = _run(_long_smc(), [_long_fvg()], _ctx(closed=one_loss))
    assert len(intents) == 3
    halted = (_trade(-50.0), _trade(-40.0))
    assert _run(_long_smc(), [_long_fvg()], _ctx(closed=halted)) == []


def test_below_cost_floor_inclusive() -> None:
    assert _below_cost_floor(15.0, 15.0) is True
    assert _below_cost_floor(15.1, 15.0) is False
    assert _below_cost_floor(5.0, 15.0) is True


def _tight_short_ctx(sweep_high: float = 20054.0) -> tuple[SmcLevels, list[Fvg], DecisionContext]:
    sweep = SWEEP_TS
    smc = _smc(
        dealing=_range("premium"),
        pdh=_level("pdh", 20100.0, "swept", sweep),
        events=[_event(sweep, direction="bearish")],
    )
    fvg = _fvg("bearish", top=20050.0, bottom=19980.0, formed_at=FVG_TS)
    bars = (
        _k(sweep, sweep_high, 20040.0, 20048.0),
        _k(NOW, 20080.0, 20020.0, 20040.0),
    )
    return smc, [fvg], _ctx(bars_5m=bars)


def test_tight_short_r5_does_not_arm() -> None:
    smc, fvgs, ctx = _tight_short_ctx()
    params = SetupAParams(entry_price="top", stop_buffer=1.0)
    assert params.min_r_points == 15.0
    assert _run(smc, fvgs, ctx, params) == []


def test_tight_short_r5_arms_when_floor_off() -> None:
    smc, fvgs, ctx = _tight_short_ctx()
    params = SetupAParams(entry_price="top", stop_buffer=1.0, min_r_points=0.0)
    intents = _run(smc, fvgs, ctx, params)
    assert _kinds(intents) == ["place_limit", "place_stop", "place_limit"]
    entry, stop, _tp = intents
    assert entry.price == 20050.0
    assert stop.price == 20055.0
    assert entry.price is not None and stop.price is not None
    assert abs(entry.price - stop.price) == 5.0


def test_short_r15_equals_floor_does_not_arm() -> None:
    smc, fvgs, ctx = _tight_short_ctx(sweep_high=20064.0)
    params = SetupAParams(entry_price="top", stop_buffer=1.0)
    assert params.min_r_points == 15.0
    assert _run(smc, fvgs, ctx, params) == []
    open_floor = SetupAParams(entry_price="top", stop_buffer=1.0, min_r_points=0.0)
    intents = _run(smc, fvgs, ctx, open_floor)
    assert _kinds(intents) == ["place_limit", "place_stop", "place_limit"]
    entry, stop, _tp = intents
    assert entry.price is not None and stop.price is not None
    assert abs(entry.price - stop.price) == 15.0


def test_short_mirror() -> None:
    sweep = SWEEP_TS
    smc = _smc(
        dealing=_range("premium"),
        pdh=_level("pdh", 20100.0, "swept", sweep),
        events=[_event(sweep, direction="bearish")],
    )
    fvg = _fvg("bearish", top=20050.0, bottom=19980.0, formed_at=FVG_TS)
    bars = (
        _k(sweep, 20120.0, 20040.0, 20060.0),
        _k(NOW, 20080.0, 20020.0, 20040.0),
    )
    intents = _run(smc, [fvg], _ctx(bars_5m=bars))
    assert _kinds(intents) == ["place_limit", "place_stop", "place_limit"]
    assert intents[0].side == "short"
    assert intents[0].price == 20050.0
    assert intents[1].side == "long"
    assert intents[1].expire_at is None


def test_a_prime_short_stop_is_sweep_extreme_not_fvg_top_buffer() -> None:
    params = SetupAParams(entry_price="top", stop_buffer=3.0)
    sweep = SWEEP_TS
    smc = _smc(
        dealing=_range("premium"),
        pdh=_level("pdh", 20100.0, "swept", sweep),
        events=[_event(sweep, direction="bearish")],
    )
    fvg = _fvg("bearish", top=20050.0, bottom=19980.0, formed_at=FVG_TS)
    sweep_high = 20120.0
    bars = (
        _k(sweep, sweep_high, 20040.0, 20060.0),
        _k(NOW, 20080.0, 20020.0, 20040.0),
    )
    intents = _run(smc, [fvg], _ctx(bars_5m=bars), params)
    entry = intents[0].price
    stop = intents[1].price
    assert entry is not None and stop is not None
    assert stop == sweep_high + params.stop_buffer
    assert stop - entry != params.stop_buffer


def test_a_prime_long_stop_is_sweep_extreme_not_fvg_bottom_buffer() -> None:
    params = SetupAParams(entry_price="top", stop_buffer=5.0)
    intents = _run(_long_smc(), [_long_fvg()], _ctx(), params)
    entry = intents[0].price
    stop = intents[1].price
    sweep_low = 19790.0
    fvg_bottom = 19850.0
    assert entry == 19920.0
    assert stop is not None
    assert stop == sweep_low - params.stop_buffer
    assert stop != fvg_bottom - params.stop_buffer
    assert entry - stop != params.stop_buffer


def test_night_leftover_flatten_1505_and_0200() -> None:
    pos = Position(side="long", qty=1, avg_price=19920.0)
    for ts in (datetime(2026, 8, 17, 15, 5), datetime(2026, 8, 18, 2, 0)):
        intents = _run(_EMPTY_IF_NEEDED(), [], _ctx(ts, position=pos, bars_5m=(_k(ts, 1, 1, 1),)))
        assert _kinds(intents) == ["flatten"], ts


def test_night_flat_no_entry() -> None:
    ts = datetime(2026, 8, 17, 15, 5)
    assert _run(_long_smc(), [_long_fvg()], _ctx(ts, bars_5m=_bars() + (_k(ts, 1, 1, 1),))) == []


def _long_compute_series() -> list[KBar]:
    return [
        _k(datetime(2026, 8, 14, 13, 40), 20200.0, 19950.0, 20050.0),
        _k(datetime(2026, 8, 14, 13, 45), 20220.0, 19900.0, 20000.0),
        _k(datetime(2026, 8, 17, 8, 50), 20020.0, 19980.0, 20000.0),
        _k(datetime(2026, 8, 17, 8, 55), 20030.0, 19970.0, 20010.0),
        _k(datetime(2026, 8, 17, 9, 0), 20100.0, 19980.0, 20080.0),
        _k(datetime(2026, 8, 17, 9, 5), 20040.0, 19960.0, 20000.0),
        _k(datetime(2026, 8, 17, 9, 10), 20030.0, 19950.0, 19980.0),
        _k(datetime(2026, 8, 17, 9, 15), 20020.0, 19940.0, 19960.0),
        _k(datetime(2026, 8, 17, 9, 20), 20010.0, 19880.0, 19920.0),
        _k(datetime(2026, 8, 17, 9, 25), 20000.0, 19910.0, 19940.0),
        _k(datetime(2026, 8, 17, 9, 30), 19990.0, 19900.0, 19930.0),
        _k(datetime(2026, 8, 17, 9, 35), 20150.0, 19920.0, 20120.0),
        _k(datetime(2026, 8, 17, 9, 40), 20160.0, 20080.0, 20100.0),
        _k(datetime(2026, 8, 17, 9, 45), 20140.0, 20090.0, 20110.0),
        _k(datetime(2026, 8, 17, 9, 50), 20130.0, 20085.0, 20100.0),
        _k(datetime(2026, 8, 17, 9, 55), 20185.0, 20100.0, 20180.0),
        _k(datetime(2026, 8, 17, 10, 0), 20190.0, 20050.0, 20070.0),
        _k(datetime(2026, 8, 17, 10, 5), 20090.0, 20000.0, 20010.0),
    ]


def _mirror(bar: KBar, pivot: float = 40000.0) -> KBar:
    return _k(bar.timestamp, pivot - bar.low, pivot - bar.high, pivot - bar.close)


def _short_compute_series() -> list[KBar]:
    return [_mirror(bar) for bar in _long_compute_series()]


def _flat_ctx(bars: list[KBar]) -> DecisionContext:
    last = bars[-1]
    return DecisionContext(
        bar_1m=last,
        bars_5m=tuple(bars),
        position=Position(side=None, qty=0, avg_price=None),
        pending=(),
        closed_trades=(),
        entry_ts=None,
    )


def test_compute_long_series_arms_bracket() -> None:
    bars = _long_compute_series()
    levels = smc_compute(bars)
    fvgs = fvg_compute(bars, min_points=0.0)
    assert levels.pdl is not None
    assert levels.pdl.interact == "swept"
    assert levels.dealing_range is not None
    assert levels.dealing_range.position == "discount"
    assert any(ev.direction == "bullish" for ev in levels.events)
    assert any(fvg.direction == "bullish" and fvg.state != "filled" for fvg in fvgs)
    intents = SetupA().decide(_flat_ctx(bars))
    assert _kinds(intents) == ["place_limit", "place_stop", "place_limit"]
    assert intents[0].side == "long"
    assert intents[1].expire_at is None
    assert intents[2].expire_at is None


def test_compute_short_series_arms_bracket() -> None:
    bars = _short_compute_series()
    levels = smc_compute(bars)
    assert levels.pdh is not None
    assert levels.pdh.interact == "swept"
    assert levels.dealing_range is not None
    assert levels.dealing_range.position == "premium"
    intents = SetupA().decide(_flat_ctx(bars))
    assert _kinds(intents) == ["place_limit", "place_stop", "place_limit"]
    assert intents[0].side == "short"


def _expand_1m(bars_5m: list[KBar]) -> list[KBar]:
    out: list[KBar] = []
    for bar in bars_5m:
        for i in range(4, -1, -1):
            ts = bar.timestamp - timedelta(minutes=i)
            out.append(
                KBar(
                    timestamp=ts,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume=bar.volume,
                    amount=bar.amount,
                )
            )
    return out


def _cost() -> CostConfig:
    return CostConfig(
        commission_nt=20,
        slippage_ticks=1,
        flatten_slippage_ticks=2,
        initial_margin_nt=10_000,
        maintenance_margin_nt=8_000,
    )


def test_engine_fill_after_decide_and_stop_live_at_1340() -> None:
    bars_5m = _long_compute_series()
    bars_1m = _expand_1m(bars_5m)
    last = bars_5m[-1].timestamp
    pad_start = last + timedelta(minutes=1)
    pad_end = datetime(2026, 8, 17, 13, 41)
    ts = pad_start
    while ts <= pad_end:
        bars_1m.append(
            KBar(
                timestamp=ts,
                open=20050.0,
                high=20060.0,
                low=20040.0,
                close=20050.0,
                volume=1,
                amount=20050.0,
            )
        )
        ts += timedelta(minutes=1)

    class _Wrap:
        def __init__(self) -> None:
            self.inner = SetupA()
            self.at_arm: DecisionContext | None = None
            self.at_1340: DecisionContext | None = None

        def decide(self, ctx: DecisionContext) -> list[Intent]:
            intents = self.inner.decide(ctx)
            if any(item.kind == "place_limit" and item.side == "long" for item in intents):
                self.at_arm = ctx
            if ctx.bar_1m.timestamp == datetime(2026, 8, 17, 13, 40):
                self.at_1340 = ctx
            return intents

    wrap = _Wrap()
    result = run(bars_1m, wrap, _cost(), BacktestConfig(fill_mode="optimistic"))
    assert wrap.at_arm is not None
    assert result.trades
    assert result.trades[0].entry_ts > wrap.at_arm.bar_1m.timestamp
    assert wrap.at_1340 is not None
    assert wrap.at_1340.position.side == "long"
    stops = [order for order in wrap.at_1340.pending if order.kind == "stop"]
    assert stops
    assert stops[0].expire_at is None
    assert result.trades[0].reason == "flatten"
