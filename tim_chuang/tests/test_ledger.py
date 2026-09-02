from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from tfx_trading.backtest.config import BacktestConfig, load_backtest_config
from tfx_trading.backtest.dummy import FixedTimeStrategy
from tfx_trading.backtest.engine import run
from tfx_trading.backtest.ledger import Ledger, RunMeta, entry_session
from tfx_trading.kbar import KBar
from tfx_trading.trading.costs import CostConfig, load_trading_config
from tfx_trading.trading.models import Intent, Position, TradeRecord


def _cfg() -> CostConfig:
    return CostConfig(
        commission_nt=20,
        slippage_ticks=1,
        flatten_slippage_ticks=2,
        initial_margin_nt=10_000,
        maintenance_margin_nt=8_000,
    )


def _bar(ts: datetime, price: float = 20000.0) -> KBar:
    return KBar(
        timestamp=ts,
        open=price,
        high=price,
        low=price,
        close=price,
        volume=1,
        amount=price,
    )


def _trade(
    *,
    pnl: float,
    entry: datetime,
    exit: datetime,
    r_multiple: float | None,
    side: str = "long",
    reason: str = "flatten",
) -> TradeRecord:
    return TradeRecord(
        side=side,  # type: ignore[arg-type]
        entry_ts=entry,
        entry_price=20000.0,
        exit_ts=exit,
        exit_price=20000.0,
        qty=1,
        pnl_nt=pnl,
        r_multiple=r_multiple,
        reason=reason,  # type: ignore[arg-type]
    )


def test_mdd_and_min_account() -> None:
    ledger = Ledger(_cfg(), "conservative", RunMeta(git_hash="abc"))
    t0 = datetime(2026, 8, 17, 9, 0)
    t1 = datetime(2026, 8, 17, 9, 5)
    win = _trade(pnl=100.0, entry=t0, exit=t0, r_multiple=1.0)
    loss = _trade(pnl=-40.0, entry=t1, exit=t1, r_multiple=-0.4)
    flat = Position(side=None, qty=0, avg_price=None)
    ledger.on_bar(_bar(t0), win, flat)
    ledger.on_bar(_bar(t1), loss, flat)
    result = ledger.finish([_bar(t0), _bar(t1)])
    assert result.mdd_nt == pytest.approx(40.0)
    assert result.min_account_nt == pytest.approx(10_000 + 40.0)
    assert result.win_rate == pytest.approx(0.5)
    assert result.avg_hold == pytest.approx(0.0)
    assert result.expected_r == pytest.approx(0.3)


def test_expected_r_none_without_stop() -> None:
    start = datetime(2026, 8, 17, 8, 46)
    bars = [_bar(start + timedelta(minutes=i)) for i in range(11)]
    bars[5] = KBar(
        timestamp=datetime(2026, 8, 17, 8, 51),
        open=20000.0,
        high=20010.0,
        low=19990.0,
        close=20000.0,
        volume=1,
        amount=20000.0,
    )
    bars[10] = KBar(
        timestamp=datetime(2026, 8, 17, 8, 56),
        open=20010.0,
        high=20010.0,
        low=20000.0,
        close=20010.0,
        volume=1,
        amount=20010.0,
    )
    t850 = datetime(2026, 8, 17, 8, 50)
    t855 = datetime(2026, 8, 17, 8, 55)
    no_stop = FixedTimeStrategy(
        {
            t850: [
                Intent(
                    intent_id="e",
                    kind="place_limit",
                    side="long",
                    price=20000.0,
                    qty=1,
                    expire_at=None,
                    target_intent_id=None,
                ),
            ],
            t855: [
                Intent(
                    intent_id="f",
                    kind="flatten",
                    side="short",
                    price=None,
                    qty=1,
                    expire_at=None,
                    target_intent_id=None,
                ),
            ],
        }
    )
    result = run(bars, no_stop, _cfg(), BacktestConfig(fill_mode="optimistic"))
    assert len(result.trades) == 1
    assert result.expected_r is None
    with_stop = FixedTimeStrategy(
        {
            t850: [
                Intent(
                    intent_id="e",
                    kind="place_limit",
                    side="long",
                    price=20000.0,
                    qty=1,
                    expire_at=None,
                    target_intent_id=None,
                ),
                Intent(
                    intent_id="s",
                    kind="place_stop",
                    side="short",
                    price=19900.0,
                    qty=1,
                    expire_at=None,
                    target_intent_id=None,
                ),
            ],
            t855: [
                Intent(
                    intent_id="f",
                    kind="flatten",
                    side="short",
                    price=None,
                    qty=1,
                    expire_at=None,
                    target_intent_id=None,
                ),
            ],
        }
    )
    result2 = run(bars, with_stop, _cfg(), BacktestConfig(fill_mode="optimistic"))
    assert result2.trades[0].r_multiple is not None


def test_write_trade_log_header(tmp_path: Path) -> None:
    ledger = Ledger(_cfg(), "optimistic", RunMeta(git_hash="deadbeef", source_files="in-memory"))
    result = ledger.finish([])
    path = tmp_path / "trades.csv"
    result.write_trade_log(path)
    text = path.read_text(encoding="utf-8")
    assert "# git_hash: deadbeef" in text
    assert "# fill_mode: optimistic" in text


def test_load_backtest_config_defaults_and_extra_keys(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("simulation: true\n", encoding="utf-8")
    loaded = load_backtest_config(path)
    assert loaded.fill_mode == "conservative"
    path.write_text(
        "simulation: true\ntrading:\n  fill_mode: optimistic\n  max_daily_loss_nt: 1\n",
        encoding="utf-8",
    )
    loaded = load_backtest_config(path)
    assert loaded.fill_mode == "optimistic"
    assert not hasattr(_cfg(), "fill_mode")
    costs = load_trading_config(path)
    assert not hasattr(costs, "fill_mode")
    path.write_text("trading:\n  fill_mode: nope\n", encoding="utf-8")
    with pytest.raises(ValueError, match="fill_mode"):
        load_backtest_config(path)


def test_entry_session_tails() -> None:
    assert entry_session(datetime(2026, 8, 17, 13, 46)) == "day"
    assert entry_session(datetime(2026, 8, 17, 5, 1)) == "night"
    assert entry_session(datetime(2026, 8, 17, 8, 47)) is None
