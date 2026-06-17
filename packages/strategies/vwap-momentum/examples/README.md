# Examples for strategy-vwap-momentum

These examples show how to construct and use the reference `VWAPMomentumStrategy` with `trading-engine`.

They do **not** contain secrets or full historical data.

## 1. Pure construction (only needs trading-engine)

See `minimal_strategy_usage.py`. This demonstrates:
- Loading `RuntimeConfig` (your app supplies the real one)
- Building `StrategyParams`
- Instantiating `VWAPMomentumStrategy`
- Calling `reset()` and inspecting public surface

This works even without `trading-backtest` installed.

## 2. With BacktestEngine (optional)

If you `pip install ".[backtest]"` (or install trading-backtest separately), you can wire the strategy into a `BacktestEngine` from `trading-backtest` and run deterministic replay.

The actual replay + MockBroker + tick loading logic lives in `trading-backtest`. This package only supplies the decision module.

Example skeleton (in your own research script):

```python
from trading_backtest import BacktestEngine
from strategy_vwap_momentum import VWAPMomentumStrategy, StrategyParams
from trading_engine.testing.defaults import default_runtime_config   # for research only

cfg = default_runtime_config()   # replace with your real calibrated RuntimeConfig
strategy = VWAPMomentumStrategy(params=StrategyParams.from_runtime_config(cfg))

bt = BacktestEngine(
    code="TXFR1",
    dates=[...],                 # your list of date objects
    strategy=strategy,
    runtime_config=cfg,
    # cache_dir=..., ports=...
)
bt.run()
# inspect bt result, audit logs, etc.
```

See [trading-backtest/SPEC.md](../../trading-backtest/SPEC.md) for tick cache format, matching limits, and fill validation.

## Reminder

This is reference research code. Always run full UAT per trading-engine guidelines before any live usage. Calibrate parameters (especially trend `min_strength`) against your own data using the emitted SIGNAL_AUDIT records (including trend_veto).
