from __future__ import annotations

from tfx_trading.backtest.broker import Broker
from tfx_trading.backtest.config import BacktestConfig
from tfx_trading.backtest.ledger import BacktestResult, Ledger, RunMeta, empty_result
from tfx_trading.bar_store import BarStore
from tfx_trading.kbar import KBar
from tfx_trading.strategy.protocol import DecisionContext, Strategy
from tfx_trading.trading.costs import CostConfig
from tfx_trading.trading.models import TradeRecord


def run(
    bars_1m: list[KBar],
    strategy: Strategy,
    cost_cfg: CostConfig,
    backtest_cfg: BacktestConfig,
    *,
    meta: RunMeta | None = None,
) -> BacktestResult:
    if not bars_1m:
        return empty_result(cost_cfg, backtest_cfg.fill_mode, meta)
    ordered = sorted(bars_1m, key=lambda bar: bar.timestamp)
    seen: set[object] = set()
    for bar in ordered:
        ts = bar.timestamp
        if ts in seen:
            raise ValueError(f"duplicate 1m timestamp: {ts}")
        seen.add(ts)
    bars_5m_all = BarStore(ordered).resample_5m()
    five_ts = {bar.timestamp for bar in bars_5m_all}
    broker = Broker(cost_cfg, backtest_cfg)
    ledger = Ledger(cost_cfg, backtest_cfg.fill_mode, meta)
    closed: list[TradeRecord] = []
    for bar in ordered:
        _fills, trade = broker.on_bar(bar)
        if trade is not None:
            closed.append(trade)
        ledger.on_bar(bar, trade, broker.position)
        if bar.timestamp not in five_ts:
            continue
        prefix = tuple(item for item in bars_5m_all if item.timestamp <= bar.timestamp)
        ctx = DecisionContext(
            bar_1m=bar,
            bars_5m=prefix,
            position=broker.position,
            pending=broker.pending,
            closed_trades=tuple(closed),
            entry_ts=broker.entry_ts,
        )
        intents = strategy.decide(ctx)
        broker.submit(intents, now=bar.timestamp)
    return ledger.finish(ordered)


__all__ = [
    "run",
]
