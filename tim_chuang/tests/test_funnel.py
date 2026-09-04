from __future__ import annotations

from datetime import datetime, time

from tfx_trading.backtest.funnel import (
    SpellTracker,
    fill_rate,
    impulse_bucket,
    next_5m_after,
    render_funnel_md,
)
from tfx_trading.kbar import KBar
from tfx_trading.strategy.protocol import DecisionContext
from tfx_trading.trading.models import Intent, Order, Position, TradeRecord


def _k(ts: datetime) -> KBar:
    return KBar(ts, 20000.0, 20010.0, 19990.0, 20000.0, 1, 20000.0)


def _order() -> Order:
    return Order(
        order_id="e1",
        intent_id="e1",
        kind="limit",
        side="short",
        price=20050.0,
        qty=1,
        expire_at=datetime(2026, 8, 17, 13, 40),
        status="pending",
        reject_reason=None,
    )


def _trade() -> TradeRecord:
    return TradeRecord(
        side="short",
        entry_ts=datetime(2026, 8, 17, 10, 5),
        entry_price=20050.0,
        exit_ts=datetime(2026, 8, 17, 10, 5),
        exit_price=20055.0,
        qty=1,
        pnl_nt=-50.0,
        r_multiple=-1.0,
        reason="entry_stopped",
    )


def _ctx(
    ts: datetime,
    *,
    pending: tuple[Order, ...] = (),
    closed: tuple[TradeRecord, ...] = (),
    position: Position | None = None,
) -> DecisionContext:
    return DecisionContext(
        bar_1m=_k(ts),
        bars_5m=(_k(ts),),
        position=position if position is not None else Position(None, 0, None),
        pending=pending,
        closed_trades=closed,
        entry_ts=None,
    )


def _arm(ts: datetime) -> list[Intent]:
    stamp = ts.strftime("%Y%m%d%H%M")
    return [
        Intent(f"{stamp}-entry", "place_limit", "short", 20050.0, 1, None, None),
        Intent(f"{stamp}-stop", "place_stop", "long", 20065.0, 1, None, None),
        Intent(f"{stamp}-tp", "place_limit", "long", 20020.0, 1, None, None),
    ]


def _cancel(ts: datetime) -> list[Intent]:
    stamp = ts.strftime("%Y%m%d%H%M")
    return [Intent(f"{stamp}-cancel", "cancel", None, None, 1, None, "e1")]


def test_impulse_bucket_same_next_later() -> None:
    interact = datetime(2026, 8, 17, 9, 30)
    next_ts = datetime(2026, 8, 17, 9, 35)
    assert impulse_bucket(interact, interact, next_ts) == "same"
    assert impulse_bucket(next_ts, interact, next_ts) == "next"
    assert impulse_bucket(datetime(2026, 8, 17, 9, 45), interact, next_ts) == "later"


def test_next_5m_after_stays_in_session() -> None:
    bars = [
        _k(datetime(2026, 8, 17, 9, 30)),
        _k(datetime(2026, 8, 17, 9, 35)),
        _k(datetime(2026, 8, 17, 13, 45)),
        _k(datetime(2026, 8, 17, 15, 5)),
    ]
    interact = datetime(2026, 8, 17, 9, 30)
    assert next_5m_after(bars, interact) == datetime(2026, 8, 17, 9, 35)
    assert next_5m_after(bars, datetime(2026, 8, 17, 13, 45)) is None
    assert impulse_bucket(datetime(2026, 8, 17, 15, 5), datetime(2026, 8, 17, 13, 45), None) == "later"


def test_fill_rate_uses_n_spells_not_seventeen() -> None:
    assert fill_rate(5, 10) == 0.5
    assert fill_rate(0, 0) is None
    assert fill_rate(17, 17) == 1.0
    assert fill_rate(5, 17) != 5 / 16


def test_arm_then_fill() -> None:
    tracker = SpellTracker()
    t0 = datetime(2026, 8, 17, 10, 0)
    t1 = datetime(2026, 8, 17, 10, 5)
    tracker.on_close(_ctx(t0), _arm(t0))
    tracker.on_close(_ctx(t1, closed=(_trade(),)), [])
    tracker.finish()
    assert tracker.counts.n_spells == 1
    assert tracker.counts.n_fills == 1
    assert tracker.counts.fill_rate == 1.0
    assert tracker.counts.n_unfilled_flatten == 0


def test_arm_then_thesis_cancel() -> None:
    tracker = SpellTracker()
    t0 = datetime(2026, 8, 17, 10, 0)
    t1 = datetime(2026, 8, 17, 10, 5)
    tracker.on_close(_ctx(t0), _arm(t0))
    tracker.on_close(_ctx(t1, pending=(_order(),)), _cancel(t1))
    tracker.finish()
    assert tracker.counts.n_spells == 1
    assert tracker.counts.n_cancel_thesis == 1
    assert tracker.counts.n_fills == 0
    assert tracker.counts.n_unfilled_flatten == 0


def test_arm_then_1340_expire_without_cancel() -> None:
    tracker = SpellTracker(flatten_time=time(13, 40))
    t0 = datetime(2026, 8, 17, 10, 0)
    t_mid = datetime(2026, 8, 17, 10, 5)
    t_flat = datetime(2026, 8, 17, 13, 40)
    tracker.on_close(_ctx(t0), _arm(t0))
    tracker.on_close(_ctx(t_mid, pending=(_order(),)), [])
    tracker.on_close(_ctx(t_flat), [])
    tracker.finish()
    assert tracker.counts.n_spells == 1
    assert tracker.counts.n_unfilled_flatten == 1
    assert tracker.counts.n_cancel_thesis == 0
    assert tracker.counts.n_fills == 0


def test_unfilled_flatten_requires_flatten_clock() -> None:
    tracker = SpellTracker(flatten_time=time(13, 40))
    t0 = datetime(2026, 8, 17, 10, 0)
    t_empty = datetime(2026, 8, 17, 10, 5)
    tracker.on_close(_ctx(t0), _arm(t0))
    tracker.on_close(_ctx(t_empty), [])
    tracker.finish()
    assert tracker.counts.n_unfilled_flatten == 0
    assert tracker.counts.n_still_open == 1
    assert tracker.counts.n_cancel_thesis == 0
    assert tracker.counts.n_fills == 0


def test_render_funnel_md_not_go_nogo() -> None:
    payload: dict[str, object] = {
        "git_hash": "abc",
        "start": "2025-03-03T08:46:00",
        "end": "2025-11-06T23:59:00",
        "n_1m": 1,
        "fill_mode": "conservative",
        "cell": {
            "entry_price": "top",
            "min_points": 15.0,
            "stop_buffer": 3.0,
            "take_profit": "2R",
            "require_external": False,
            "min_r_points": 15.0,
        },
        "detector": {
            "n_nested_any": 3,
            "n_nested_choch": 2,
            "n_long_any": 1,
            "n_short_any": 2,
            "n_long_choch": 1,
            "n_short_choch": 1,
            "fvg_same": 1,
            "fvg_next": 1,
            "fvg_later": 1,
            "shadowed_impulse": 0,
        },
        "spells": {
            "n_spells": 4,
            "n_fills": 1,
            "fill_rate": 0.25,
            "n_cancel_thesis": 1,
            "n_unfilled_flatten": 2,
            "n_still_open": 0,
            "raw_arm_closes": 9,
        },
        "fill_reasons": {
            "entry_stopped": 0,
            "stop": 1,
            "target": 0,
            "flatten": 0,
        },
        "n_result_trades": 1,
    }
    text = render_funnel_md(payload)
    assert "not go/no-go" in text
    assert "flatten≠0 is not a broker bug" in text
    assert "**4**" in text
    assert "fill_rate: **0.250**" in text
    assert "nested CHoCH + FVG≥15: **2**" in text
    assert "n_fills == n_result_trades == 1" in text
    assert "Hard-cutting impulse to same/next" in text
