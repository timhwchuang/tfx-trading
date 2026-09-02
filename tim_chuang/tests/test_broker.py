from __future__ import annotations

from datetime import datetime, timedelta

from tfx_trading.backtest.broker import Broker
from tfx_trading.backtest.config import BacktestConfig, FillMode
from tfx_trading.kbar import KBar
from tfx_trading.trading.costs import TICK_SIZE, CostConfig, apply_slippage
from tfx_trading.trading.models import Intent, IntentKind, Side


def _cfg() -> CostConfig:
    return CostConfig(
        commission_nt=20,
        slippage_ticks=1,
        flatten_slippage_ticks=2,
        initial_margin_nt=10_000,
        maintenance_margin_nt=8_000,
    )


def _bt(mode: FillMode = "optimistic") -> BacktestConfig:
    return BacktestConfig(fill_mode=mode)


def _broker(mode: FillMode = "optimistic") -> Broker:
    return Broker(_cfg(), _bt(mode))


def _bar(
    ts: datetime,
    *,
    open_: float = 20000.0,
    high: float = 20000.0,
    low: float = 20000.0,
    close: float = 20000.0,
) -> KBar:
    return KBar(timestamp=ts, open=open_, high=high, low=low, close=close, volume=1, amount=open_)


def _intent(
    intent_id: str,
    kind: IntentKind,
    side: Side | None,
    price: float | None,
    expire_at: datetime | None = None,
    target_intent_id: str | None = None,
) -> Intent:
    return Intent(
        intent_id=intent_id,
        kind=kind,
        side=side,
        price=price,
        qty=1,
        expire_at=expire_at,
        target_intent_id=target_intent_id,
    )


TS0 = datetime(2026, 8, 17, 9, 0)
TS1 = datetime(2026, 8, 17, 9, 1)


def test_buy_limit_touch_only_optimistic() -> None:
    opt = _broker("optimistic")
    cons = _broker("conservative")
    intent = _intent("e", "place_limit", "long", 20000.0)
    opt.submit([intent], now=TS0)
    cons.submit([intent], now=TS0)
    bar = _bar(TS1, open_=20001.0, high=20002.0, low=20000.0, close=20001.0)
    fills_opt, _ = opt.on_bar(bar)
    fills_cons, _ = cons.on_bar(bar)
    assert len(fills_opt) == 1
    assert fills_opt[0].price == 20000.0
    assert fills_cons == ()


def test_buy_limit_trade_through_both() -> None:
    opt = _broker("optimistic")
    cons = _broker("conservative")
    intent = _intent("e", "place_limit", "long", 20000.0)
    opt.submit([intent], now=TS0)
    cons.submit([intent], now=TS0)
    bar = _bar(TS1, open_=20001.0, high=20002.0, low=20000.0 - TICK_SIZE, close=20001.0)
    assert len(opt.on_bar(bar)[0]) == 1
    assert len(cons.on_bar(bar)[0]) == 1


def test_sell_limit_touch_only_optimistic() -> None:
    opt = _broker("optimistic")
    cons = _broker("conservative")
    intent = _intent("e", "place_limit", "short", 20000.0)
    opt.submit([intent], now=TS0)
    cons.submit([intent], now=TS0)
    bar = _bar(TS1, open_=19999.0, high=20000.0, low=19990.0, close=19999.0)
    fills_opt, _ = opt.on_bar(bar)
    fills_cons, _ = cons.on_bar(bar)
    assert len(fills_opt) == 1
    assert fills_opt[0].price == 20000.0
    assert fills_cons == ()


def test_stop_protects_long_gap_b() -> None:
    broker = _broker()
    broker.submit(
        [
            _intent("e", "place_limit", "long", 20000.0),
            _intent("s", "place_stop", "short", 19950.0),
        ],
        now=TS0,
    )
    entry_bar = _bar(TS1, open_=20000.0, high=20010.0, low=19990.0, close=20000.0)
    fills, trade = broker.on_bar(entry_bar)
    assert len(fills) == 1
    assert trade is None
    gap = _bar(
        datetime(2026, 8, 17, 9, 2),
        open_=19900.0,
        high=19910.0,
        low=19880.0,
        close=19900.0,
    )
    fills, trade = broker.on_bar(gap)
    assert trade is not None
    assert trade.reason == "stop"
    slipped = apply_slippage("stop", "short", 19950.0, _cfg())
    assert fills[0].price == min(slipped, 19900.0)


def test_same_bar_sl_beats_tp() -> None:
    broker = _broker()
    broker.submit([_intent("e", "place_limit", "long", 20000.0)], now=TS0)
    broker.on_bar(_bar(TS1, open_=20000.0, high=20000.0, low=20000.0, close=20000.0))
    broker.submit(
        [
            _intent("s", "place_stop", "short", 19980.0),
            _intent("t", "place_limit", "short", 20020.0),
        ],
        now=TS1,
    )
    both = _bar(
        datetime(2026, 8, 17, 9, 2),
        open_=20000.0,
        high=20030.0,
        low=19970.0,
        close=20000.0,
    )
    fills, trade = broker.on_bar(both)
    assert trade is not None
    assert trade.reason == "stop"
    assert len(fills) == 1


def test_entry_stopped_same_bar_skips_tp() -> None:
    broker = _broker()
    broker.submit(
        [
            _intent("e", "place_limit", "long", 20000.0),
            _intent("s", "place_stop", "short", 19990.0),
            _intent("t", "place_limit", "short", 20050.0),
        ],
        now=TS0,
    )
    bar = _bar(TS1, open_=20000.0, high=20060.0, low=19980.0, close=20000.0)
    fills, trade = broker.on_bar(bar)
    assert len(fills) == 2
    assert trade is not None
    assert trade.reason == "entry_stopped"
    assert broker.position.side is None


def test_expire_before_fill() -> None:
    broker = _broker()
    broker.submit(
        [_intent("e", "place_limit", "long", 20000.0, expire_at=TS1)],
        now=TS0,
    )
    fills, trade = broker.on_bar(_bar(TS1, open_=20000.0, high=20000.0, low=19900.0, close=20000.0))
    assert fills == ()
    assert trade is None
    assert broker.pending == ()


def test_flatten_next_open_position_side_long() -> None:
    broker = _broker()
    broker.submit(
        [
            _intent("e", "place_limit", "long", 20000.0),
            _intent("s", "place_stop", "short", 19900.0),
        ],
        now=TS0,
    )
    broker.on_bar(_bar(TS1, open_=20000.0, high=20000.0, low=20000.0, close=20000.0))
    created = broker.submit([_intent("f", "flatten", "short", None)], now=TS1)
    assert created[0].status == "pending"
    next_ts = datetime(2026, 8, 17, 9, 2)
    fills, trade = broker.on_bar(
        _bar(next_ts, open_=20010.0, high=20020.0, low=20000.0, close=20010.0)
    )
    assert trade is not None
    assert trade.reason == "flatten"
    assert trade.side == "long"
    assert fills[0].price == apply_slippage("flatten", "short", 20010.0, _cfg())


def test_resting_tp_does_not_fill_while_flat() -> None:
    broker = _broker()
    broker.submit(
        [
            _intent("e", "place_limit", "long", 19900.0),
            _intent("t", "place_limit", "short", 20050.0),
        ],
        now=TS0,
    )
    fills, trade = broker.on_bar(_bar(TS1, open_=20040.0, high=20060.0, low=20030.0, close=20040.0))
    assert fills == ()
    assert trade is None
    assert broker.position.side is None
    entry = _bar(
        datetime(2026, 8, 17, 9, 2),
        open_=19900.0,
        high=19910.0,
        low=19890.0,
        close=19900.0,
    )
    fills, trade = broker.on_bar(entry)
    assert len(fills) == 1
    assert trade is None
    tp_bar = _bar(
        datetime(2026, 8, 17, 9, 3),
        open_=20040.0,
        high=20060.0,
        low=20030.0,
        close=20050.0,
    )
    fills, trade = broker.on_bar(tp_bar)
    assert trade is not None
    assert trade.reason == "target"


def test_second_entry_rejected_opposite_tp_accepted() -> None:
    broker = _broker()
    first = broker.submit([_intent("e1", "place_limit", "long", 20000.0)], now=TS0)
    assert first[0].status == "pending"
    second = broker.submit([_intent("e2", "place_limit", "long", 20000.0)], now=TS0)
    assert second[0].status == "rejected"
    broker.on_bar(_bar(TS1, open_=20000.0, high=20000.0, low=19990.0, close=20000.0))
    assert broker.position.side == "long"
    tp = broker.submit([_intent("t", "place_limit", "short", 20100.0)], now=TS1)
    assert tp[0].status == "pending"
    add = broker.submit([_intent("e3", "place_limit", "long", 20000.0)], now=TS1)
    assert add[0].status == "rejected"


def test_cancel_entry_drops_orphan_stop() -> None:
    broker = _broker()
    broker.submit(
        [
            _intent("e", "place_limit", "long", 20000.0),
            _intent("s", "place_stop", "short", 19900.0),
        ],
        now=TS0,
    )
    broker.submit(
        [_intent("c", "cancel", None, None, target_intent_id="e")],
        now=TS0,
    )
    assert all(o.kind != "stop" or o.status != "pending" for o in broker.pending)
    created = broker.submit(
        [
            _intent("e2", "place_limit", "long", 20000.0),
            _intent("s2", "place_stop", "short", 19900.0),
        ],
        now=TS0,
    )
    assert created[0].status == "pending"
    assert created[1].status == "pending"
    broker.on_bar(_bar(TS1, open_=20000.0, high=20000.0, low=20000.0, close=20000.0))
    assert broker.position.side == "long"
    fills, trade = broker.on_bar(
        _bar(datetime(2026, 8, 17, 9, 2), open_=19890.0, high=19900.0, low=19880.0, close=19890.0)
    )
    assert trade is not None
    assert trade.reason == "stop"


def test_expire_entry_drops_orphan_stop() -> None:
    broker = _broker()
    broker.submit(
        [
            _intent("e", "place_limit", "long", 20000.0, expire_at=TS1),
            _intent("s", "place_stop", "short", 19900.0),
        ],
        now=TS0,
    )
    broker.on_bar(_bar(TS1, open_=20100.0, high=20100.0, low=20100.0, close=20100.0))
    assert broker.pending == ()
    created = broker.submit(
        [
            _intent("e2", "place_limit", "long", 20000.0),
            _intent("s2", "place_stop", "short", 19900.0),
        ],
        now=TS1,
    )
    assert [o.status for o in created] == ["pending", "pending"]


def test_flatten_same_side_rejected() -> None:
    broker = _broker()
    broker.submit(
        [
            _intent("e", "place_limit", "long", 20000.0),
            _intent("s", "place_stop", "short", 19900.0),
        ],
        now=TS0,
    )
    broker.on_bar(_bar(TS1, open_=20000.0, high=20000.0, low=20000.0, close=20000.0))
    created = broker.submit([_intent("f", "flatten", "long", None)], now=TS1)
    assert created[0].status == "rejected"
    fills, trade = broker.on_bar(
        _bar(datetime(2026, 8, 17, 9, 2), open_=20010.0, high=20020.0, low=20000.0, close=20010.0)
    )
    assert fills == ()
    assert trade is None
    assert broker.position.side == "long"


def test_gtc_none_does_not_expire() -> None:
    broker = _broker()
    broker.submit([_intent("e", "place_limit", "long", 20000.0)], now=TS0)
    later = TS1 + timedelta(days=1)
    fills, _ = broker.on_bar(_bar(later, open_=20100.0, high=20100.0, low=20100.0, close=20100.0))
    assert fills == ()
    assert any(o.status == "pending" for o in broker.pending)
