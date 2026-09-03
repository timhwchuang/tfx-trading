from __future__ import annotations

from tfx_trading.backtest.broker import Broker
from tfx_trading.backtest.config import BacktestConfig
from tfx_trading.backtest.ledger import BacktestResult, Ledger, RunMeta, empty_result
from tfx_trading.bar_store import BarStore
from tfx_trading.kbar import KBar
from tfx_trading.strategy.protocol import DecisionContext, Strategy
from tfx_trading.trading.costs import CostConfig
from tfx_trading.trading.models import TradeRecord


def _close_indices(
    bars_5m_all: list[KBar],
    ordered_1m: list[KBar],
) -> list[tuple[KBar, int]]:
    """(1m bar at a 5m close, prefix length through that close).

    A 5m close with no matching 1m bar is skipped for decide, but remains in
    later prefixes (same as the old set-membership + filter).
    """
    out: list[tuple[KBar, int]] = []
    five_i = 0
    n_five = len(bars_5m_all)
    for bar in ordered_1m:
        while five_i < n_five and bars_5m_all[five_i].timestamp < bar.timestamp:
            five_i += 1
        if five_i >= n_five or bar.timestamp != bars_5m_all[five_i].timestamp:
            continue
        five_i += 1
        out.append((bar, five_i))
    return out


def prefixes_at_closes(
    bars_5m_all: list[KBar],
    ordered_1m: list[KBar],
) -> list[tuple[KBar, tuple[KBar, ...]]]:
    """(1m bar at a 5m close, 5m prefix through that close).

    Equivalent to filtering ``item.timestamp <= bar.timestamp`` on the sorted 5m
    list. Materializes every prefix at once — use for tests/inspection only; the
    engine slices lazily to keep peak memory O(n).
    """
    return [(bar, tuple(bars_5m_all[:idx])) for bar, idx in _close_indices(bars_5m_all, ordered_1m)]


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
    # Prefix length per close; the tuple itself is sliced lazily at decide time
    # so only one prefix is alive at a time (a 6-month tape would otherwise hold
    # O(n²) pointers in memory).
    close_idx = {bar.timestamp: idx for bar, idx in _close_indices(bars_5m_all, ordered)}
    broker = Broker(cost_cfg, backtest_cfg)
    ledger = Ledger(cost_cfg, backtest_cfg.fill_mode, meta)
    closed: list[TradeRecord] = []
    for bar in ordered:
        _fills, trade = broker.on_bar(bar)
        if trade is not None:
            closed.append(trade)
        ledger.on_bar(bar, trade, broker.position)
        idx = close_idx.get(bar.timestamp)
        if idx is None:
            continue
        prefix = tuple(bars_5m_all[:idx])
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
    "prefixes_at_closes",
    "run",
]
