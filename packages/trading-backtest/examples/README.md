# Examples for trading-backtest

These examples show how to use the deterministic backtest driver with `trading-engine`.

They do **not** contain secrets or full historical data.

## 1. Minimal smoke (only needs trading-engine)

See `minimal_backtest_smoke.py`. This demonstrates:

- Using `StubStrategy` (from trading_engine.testing) or a real plugin (e.g. public strategy-vwap-momentum).
- Constructing `BacktestEngine` with dates + runtime_config.
- Running replay and inspecting the host (`TradingEngine` instance) + clock.

## 2. With a real public strategy

If you have `strategy-vwap-momentum` installed:

```python
from trading_engine.testing.defaults import default_runtime_config
from trading_backtest import BacktestEngine
from strategy_vwap_momentum import VWAPMomentumStrategy, StrategyParams

cfg = default_runtime_config()
strategy = VWAPMomentumStrategy(params=StrategyParams.from_runtime_config(cfg))

engine = BacktestEngine(
    code="TXFR1",
    dates=[...],
    strategy=strategy,
    runtime_config=cfg,
)
engine.run()
print("final position qty:", engine.host.get_state_snapshot().position_qty)
```

## 3. Tick cache template

`tick_cache_template.py` writes a minimal valid `{code}_{date}.csv` under `./tick_cache/` for smoke testing. Replace with your own recorded ticks before serious runs. Format: [SPEC.md §7](../SPEC.md#7-tick-cache-format).

## 4. Backtest vs paper fill comparison

`compare_fill_audits.py` compares `FILL_AUDIT` statistics between a backtest log and a paper/live reference log:

```bash
python examples/compare_fill_audits.py backtest.log paper.log
```

Programmatic API: `trading_backtest.validation` (`compare_fill_audits`, `capture_backtest_audits`, `hash_audit_records`).

See [SPEC.md §9](../SPEC.md#9-backtest-fidelity--limitations) for the full validation pipeline.