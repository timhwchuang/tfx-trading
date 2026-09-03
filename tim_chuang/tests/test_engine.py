from __future__ import annotations

from datetime import datetime, timedelta

from tfx_trading.backtest.config import BacktestConfig
from tfx_trading.backtest.dummy import FixedTimeStrategy
from tfx_trading.backtest.engine import prefixes_at_closes, run
from tfx_trading.bar_store import BarStore
from tfx_trading.kbar import KBar
from tfx_trading.strategy.protocol import DecisionContext
from tfx_trading.trading.costs import CostConfig, round_trip_pnl_nt
from tfx_trading.trading.models import Intent, IntentKind, Side


def _cfg() -> CostConfig:
    return CostConfig(
        commission_nt=20,
        slippage_ticks=1,
        flatten_slippage_ticks=2,
        initial_margin_nt=10_000,
        maintenance_margin_nt=8_000,
    )


def _bar(
    ts: datetime,
    *,
    open_: float = 20000.0,
    high: float = 20000.0,
    low: float = 20000.0,
    close: float = 20000.0,
) -> KBar:
    return KBar(timestamp=ts, open=open_, high=high, low=low, close=close, volume=1, amount=open_)


def _minutes(start: datetime, n: int, price: float = 20000.0) -> list[KBar]:
    return [
        _bar(start + timedelta(minutes=i), open_=price, high=price, low=price, close=price)
        for i in range(n)
    ]


def _intent(
    intent_id: str,
    kind: IntentKind,
    side: Side | None,
    price: float | None,
) -> Intent:
    return Intent(
        intent_id=intent_id,
        kind=kind,
        side=side,
        price=price,
        qty=1,
        expire_at=None,
        target_intent_id=None,
    )


class _Capture:
    def __init__(self) -> None:
        self.ctxs: list[DecisionContext] = []

    def decide(self, ctx: DecisionContext) -> list[Intent]:
        self.ctxs.append(ctx)
        return []


def test_empty_bars_no_barstore() -> None:
    result = run([], _Capture(), _cfg(), BacktestConfig(fill_mode="conservative"))
    assert result.trades == ()
    assert result.n_1m == 0


def test_lookahead_limit_does_not_fill_on_decide_bar() -> None:
    start = datetime(2026, 8, 17, 8, 46)
    bars = _minutes(start, 11, 20000.0)
    bars[4] = _bar(
        datetime(2026, 8, 17, 8, 50),
        open_=20000.0,
        high=20000.0,
        low=19900.0,
        close=20000.0,
    )
    bars[5] = _bar(
        datetime(2026, 8, 17, 8, 51),
        open_=20000.0,
        high=20000.0,
        low=19900.0,
        close=20000.0,
    )
    t850 = datetime(2026, 8, 17, 8, 50)
    t855 = datetime(2026, 8, 17, 8, 55)
    strategy = FixedTimeStrategy(
        {
            t850: [_intent("e", "place_limit", "long", 19950.0)],
            t855: [_intent("f", "flatten", "short", None)],
        }
    )
    result = run(bars, strategy, _cfg(), BacktestConfig(fill_mode="optimistic"))
    assert len(result.trades) == 1
    assert result.trades[0].entry_ts == datetime(2026, 8, 17, 8, 51)


def test_bars_5m_prefix_at_0850() -> None:
    start = datetime(2026, 8, 17, 8, 46)
    bars = _minutes(start, 10, 20000.0)
    cap = _Capture()
    run(bars, cap, _cfg(), BacktestConfig(fill_mode="conservative"))
    first = cap.ctxs[0]
    assert first.bar_1m.timestamp == datetime(2026, 8, 17, 8, 50)
    assert first.bars_5m[-1].timestamp == datetime(2026, 8, 17, 8, 50)
    assert all(b.timestamp <= datetime(2026, 8, 17, 8, 50) for b in first.bars_5m)


def test_missing_1m_skips_decide() -> None:
    start = datetime(2026, 8, 17, 8, 46)
    bars = _minutes(start, 10, 20000.0)
    bars = [b for b in bars if b.timestamp != datetime(2026, 8, 17, 8, 47)]
    cap = _Capture()
    run(bars, cap, _cfg(), BacktestConfig(fill_mode="conservative"))
    decide_ts = {c.bar_1m.timestamp for c in cap.ctxs}
    assert datetime(2026, 8, 17, 8, 50) not in decide_ts
    assert datetime(2026, 8, 17, 8, 55) in decide_ts


def test_fixed_time_round_trip_trade_log() -> None:
    start = datetime(2026, 8, 17, 8, 46)
    bars = _minutes(start, 11, 20000.0)
    bars[5] = _bar(
        datetime(2026, 8, 17, 8, 51),
        open_=20000.0,
        high=20010.0,
        low=19990.0,
        close=20000.0,
    )
    bars[10] = _bar(
        datetime(2026, 8, 17, 8, 56),
        open_=20010.0,
        high=20020.0,
        low=20000.0,
        close=20010.0,
    )
    t850 = datetime(2026, 8, 17, 8, 50)
    t855 = datetime(2026, 8, 17, 8, 55)
    strategy = FixedTimeStrategy(
        {
            t850: [
                _intent("e", "place_limit", "long", 20000.0),
                _intent("s", "place_stop", "short", 19900.0),
            ],
            t855: [_intent("f", "flatten", "short", None)],
        }
    )
    result = run(bars, strategy, _cfg(), BacktestConfig(fill_mode="optimistic"))
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.side == "long"
    assert trade.reason == "flatten"
    assert trade.entry_price == 20000.0
    expected = round_trip_pnl_nt("long", 20000.0, 20008.0, 1, _cfg())
    assert trade.pnl_nt == expected
    assert trade.r_multiple is not None


def test_conservative_trades_le_optimistic() -> None:
    start = datetime(2026, 8, 17, 8, 46)
    bars = _minutes(start, 12, 20100.0)
    bars[5] = _bar(
        datetime(2026, 8, 17, 8, 51),
        open_=20050.0,
        high=20050.0,
        low=20000.0,
        close=20050.0,
    )
    bars[6] = _bar(
        datetime(2026, 8, 17, 8, 52),
        open_=20050.0,
        high=20050.0,
        low=20050.0,
        close=20050.0,
    )
    t850 = datetime(2026, 8, 17, 8, 50)
    t855 = datetime(2026, 8, 17, 8, 55)
    schedule = {
        t850: [
            _intent("e", "place_limit", "long", 20000.0),
            _intent("s", "place_stop", "short", 19900.0),
        ],
        t855: [_intent("f", "flatten", "short", None)],
    }
    opt = run(
        bars,
        FixedTimeStrategy(schedule),
        _cfg(),
        BacktestConfig(fill_mode="optimistic"),
    )
    cons = run(
        bars,
        FixedTimeStrategy(schedule),
        _cfg(),
        BacktestConfig(fill_mode="conservative"),
    )
    assert len(cons.trades) <= len(opt.trades)
    assert len(opt.trades) == 1
    assert len(cons.trades) == 0


def test_closed_trades_visible_on_same_5m_close() -> None:
    start = datetime(2026, 8, 17, 8, 46)
    bars = _minutes(start, 10, 20000.0)
    bars[5] = _bar(
        datetime(2026, 8, 17, 8, 51),
        open_=20000.0,
        high=20010.0,
        low=19990.0,
        close=20000.0,
    )
    bars[9] = _bar(
        datetime(2026, 8, 17, 8, 55),
        open_=20000.0,
        high=20000.0,
        low=19980.0,
        close=19990.0,
    )
    t850 = datetime(2026, 8, 17, 8, 50)
    cap = _Capture()

    class _PlaceThenWatch:
        def __init__(self) -> None:
            self.inner = FixedTimeStrategy(
                {
                    t850: [
                        _intent("e", "place_limit", "long", 20000.0),
                        _intent("s", "place_stop", "short", 19985.0),
                    ]
                }
            )

        def decide(self, ctx: DecisionContext) -> list[Intent]:
            cap.ctxs.append(ctx)
            return self.inner.decide(ctx)

    run(bars, _PlaceThenWatch(), _cfg(), BacktestConfig(fill_mode="optimistic"))
    at_855 = next(c for c in cap.ctxs if c.bar_1m.timestamp == datetime(2026, 8, 17, 8, 55))
    assert len(at_855.closed_trades) == 1
    assert at_855.position.side is None
    assert at_855.entry_ts is None
    assert at_855.closed_trades[0].reason == "stop"


def test_open_position_carries_entry_ts() -> None:
    start = datetime(2026, 8, 17, 8, 46)
    bars = _minutes(start, 10, 20000.0)
    bars[5] = _bar(
        datetime(2026, 8, 17, 8, 51),
        open_=20000.0,
        high=20010.0,
        low=19990.0,
        close=20000.0,
    )
    t850 = datetime(2026, 8, 17, 8, 50)
    cap = _Capture()

    class _PlaceThenWatch:
        def decide(self, ctx: DecisionContext) -> list[Intent]:
            cap.ctxs.append(ctx)
            if ctx.bar_1m.timestamp == t850:
                return [
                    _intent("e", "place_limit", "long", 20000.0),
                    _intent("s", "place_stop", "short", 19900.0),
                ]
            return []

    run(bars, _PlaceThenWatch(), _cfg(), BacktestConfig(fill_mode="optimistic"))
    at_855 = next(c for c in cap.ctxs if c.bar_1m.timestamp == datetime(2026, 8, 17, 8, 55))
    assert at_855.position.side == "long"
    assert at_855.entry_ts == datetime(2026, 8, 17, 8, 51)
    assert at_855.closed_trades == ()


def test_prefix_slice_matches_filter() -> None:
    start = datetime(2026, 8, 17, 8, 46)
    bars = _minutes(start, 30, 20000.0)
    bars = [b for b in bars if b.timestamp != datetime(2026, 8, 17, 8, 47)]
    ordered = sorted(bars, key=lambda bar: bar.timestamp)
    five = BarStore(ordered).resample_5m()
    sliced = prefixes_at_closes(five, ordered)
    five_ts = {bar.timestamp for bar in five}
    filtered: list[tuple[KBar, tuple[KBar, ...]]] = []
    for bar in ordered:
        if bar.timestamp not in five_ts:
            continue
        filtered.append((bar, tuple(item for item in five if item.timestamp <= bar.timestamp)))
    assert sliced == filtered
