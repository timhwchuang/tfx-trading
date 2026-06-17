# Release v0.1.0 — Research-grade deterministic backtest driver (2026-06-16) [PRE-MONOREPO HISTORICAL]

> Archived. Current work is inside the tfx-trading monorepo under packages/trading-backtest/. Install via scripts/setup-dev.sh or -e packages/.... Old git+@tag instructions below are historical only.

**Install (pin tag):**

```bash
pip install "trading-backtest @ git+https://github.com/timhwchuang/trading-backtest.git@v0.1.0"
# plus matching trading-engine
pip install "trading-engine @ git+https://github.com/timhwchuang/trading-engine.git@v0.2.0"
```

## Highlights

`trading-backtest` provides a deterministic tick replay framework that drives the **exact same `TradingEngine`** as live trading, with `MockBroker` (IOC + heuristic slippage/latency) and loader.

- Same kernel as live (no duplicate state machine).
- Strong test coverage of determinism invariants, matching rules, pending/premarket behavior.
- [packages/trading-backtest/SPEC.md](../../../packages/trading-backtest/SPEC.md) — authoritative documentation for this package.

### Key guarantees

See [packages/trading-backtest/SPEC.md §5–6](../../../packages/trading-backtest/SPEC.md):

- Same `TradingEngine` host.
- Determinism: single-thread, sync orders, VirtualClock, no future data in kbars.
- Byte-identical audit logs for identical inputs.

## ⚠️ Backtest Fidelity & Limitations

**v0.1.0 is research / alpha quality — not a production execution simulator.**

Before trusting any PnL metric:

| Works well | Does **not** work well |
|------------|------------------------|
| Strategy state machine, pending, force-flatten, risk gates (same kernel) | Equity curve / Sharpe / drawdown for position sizing or go-live |
| Determinism regression, param sweep | Assuming backtest fills match TAIFEX live microstructure |

- **Execution model**: next-tick close + fixed-point slippage; no order book, queue, or partial fills.
- **Slippage defaults** (0.5 / 2.5 / 8.0 pts) are heuristics — not calibrated from your broker fills.
- **No** commission / fee / tax in this layer.
- **Tick cache quality** is caller responsibility; missing files warn-and-skip (silent day loss in sweeps).
- **No built-in** backtest-vs-paper fill comparison tooling.

**Recommended path**: unit tests → determinism re-run → paper trade → fill statistics comparison → conservative slippage → live (with trading-engine UAT). Details: [packages/trading-backtest/SPEC.md §9](../../../packages/trading-backtest/SPEC.md).

### Before using for serious validation

- Pin `trading-engine` tag.
- Supply your own tick cache ([packages/trading-backtest/SPEC.md §7](../../../packages/trading-backtest/SPEC.md)).
- Do **not** skip paper-trade fill validation.
- For live safety, see [`docs/uat/KERNEL.md`](../../uat/KERNEL.md) and [`docs/ops/LIVE_SAFETY.md`](../../ops/LIVE_SAFETY.md).

### Full changelog

See [CHANGELOG.md](../../../CHANGELOG.md).

## Related

- [trading-engine](https://github.com/timhwchuang/trading-engine) v0.2.x (the host)
- [strategy-vwap-momentum](https://github.com/timhwchuang/strategy-vwap-momentum) v0.1.0 (example strategy plugin)
- [packages/trading-backtest/SPEC.md](../../../packages/trading-backtest/SPEC.md) (authoritative spec for this package)