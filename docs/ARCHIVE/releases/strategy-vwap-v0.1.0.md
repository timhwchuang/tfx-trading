# Release v0.1.0 — First public reference strategy plugin (2026-06-16) [PRE-MONOREPO HISTORICAL]

> Archived from separate-repo era. Current development is in the `tfx-trading` monorepo under `packages/strategies/vwap-momentum/`. Install via monorepo clone + editable or local paths (see root README + [SPEC.md](../../../SPEC.md)). Old git+ URLs no longer active for new work.

**Install (pin tag):**

```bash
pip install "strategy-vwap-momentum @ git+https://github.com/timhwchuang/strategy-vwap-momentum.git@v0.1.0"
# plus matching trading-engine
pip install "trading-engine @ git+https://github.com/timhwchuang/trading-engine.git@v0.2.0"
```

## Highlights

This is the **first public `strategy-<name>`** package (at the time under the prior multi-package / "three-repo" layout; now consolidated in monorepo).

It provides a complete, well-tested reference implementation of the VWAP momentum pullback strategy with:
- Higher-timeframe trend filter (P6-1 Level-2 with `min_strength` in ATR units + honest "Flat" on weak regimes)
- ATR-dynamic trailing stops and VWAP stops
- Exit grace period decoupling hard vs. VWAP stops
- Rich `SIGNAL_AUDIT` emission (including `reason="trend_veto"`) for honest calibration and UAT analysis
- Full `Strategy` Protocol compliance + sweep / patch helpers for research

### Before you use this strategy in any serious backtest or live

1. Read trading-engine [LIVE_SAFETY.md](https://github.com/timhwchuang/trading-engine/blob/main/docs/LIVE_SAFETY.md) and complete the UAT checklist in your consuming app.
2. Treat this as **academic / personal research reference code**, not a production black-box alpha. See the prominent Disclaimer in the root [README.md](../README.md).
3. Calibrate `min_strength`, ATR k factors, grace periods, etc. using your own tick data + the `SIGNAL_AUDIT` logs + trend veto visibility. The Level-2 gate and veto audit are there precisely so you can measure whether the filter actually helps expectancy.

### New surface for strategy authors & consumers

- `VWAPMomentumStrategy(params=StrategyParams.from_runtime_config(cfg))`
- Entry point `vwap_momentum`
- `compute_trend`, dynamic ATR helpers, and patch utilities are exposed for advanced calibration work.

### Tests

~27 tests focused on trend correctness (including quantitative guards for resample hygiene, SMA seed, min_strength gating, gap pollution prevention) + behavioral integration for grace / cooldown / force-flatten / veto audit.

Full matrix CI (Python 3.11–3.13) installs a pinned `trading-engine` before running.

### Full changelog

See [CHANGELOG.md](../../CHANGELOG.md).

## Related

- trading-engine v0.2.0 (the host this plugin targets)
- See root [SPEC.md](../../../SPEC.md) and [packages/strategies/vwap-momentum/SPEC.md](../../../packages/strategies/vwap-momentum/SPEC.md) (this note is historical)
