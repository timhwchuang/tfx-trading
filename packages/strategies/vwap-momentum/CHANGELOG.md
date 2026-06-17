# Changelog

All notable changes to `strategy-vwap-momentum` are documented here.  
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).  
Versioning follows [SemVer](https://semver.org/) (0.x = API may still evolve; compatible with trading-engine 0.x).

## [0.1.2] - 2026-06-17

### Added

- Block new entries when `RiskGate.atr_stale` or `RiskGate.reconnect_warmup_active` (exits unchanged).

### Changed

- Depends on `trading-engine>=0.2.2,<1.0`.

[0.1.2]: https://github.com/timhwchuang/strategy-vwap-momentum/releases/tag/v0.1.2

## [0.1.1] - 2026-06-16

### Fixed

- `_try_pullback_entry`: define `trend_dir` from `market.trend_dir` before `trend_allows_entry` / `trend_veto` audit (fixes `NameError` on pullback entry path).

[0.1.1]: https://github.com/timhwchuang/strategy-vwap-momentum/releases/tag/v0.1.1

## [0.1.0] - 2026-06-16

Initial public release of the first reference `strategy-<name>` plugin for `trading-engine`.

### Added

- `VWAPMomentumStrategy` — full implementation of the `trading_engine.core.strategy.Strategy` Protocol (evaluate + reset + manage_exit + audit builders + session_force_flatten hook).
- `StrategyParams` + live overlay / sweep helpers (`patch_strategy_params`, `apply_strategy_params`, `sweepable_value`, `SWEEPABLE_PARAMS`) for research & calibration use with `RuntimeConfig`.
- `trend.py` — `compute_trend` (ema/slope + Level-2 `min_strength` gate in ATR units), `trend_allows_entry`, `dynamic_trail_points`, `dynamic_vwap_stop_distance`, supporting math (ema with proper SMA-seed warmup, resample_closes that guarantees latest bar, linear regression slope).
- `MomentumState` (internal to the plugin — correctly **not** part of the public Protocol).
- Rich `SignalAudit` builders emitting `reason="pullback" | "stop_loss" | "stop_loss_vwap" | "take_profit" | "trailing_stop" | "session_force_flatten" | "trend_veto"`.
- Unit & behavior tests (trend math + Level-2 gating + gap hygiene + CAL-1 slice guard, cooldown, exit-grace period, session force-flatten). ~27 tests (count per three-repo workspace doc).
- Entry point registration: `trading_engine.strategies = "vwap_momentum"`.
- Package metadata, MIT license, py.typed, runnable `python run_tests.py` (after trading-engine installed).
- `README.md`, `SPEC.md`, `CHANGELOG.md`, CI scaffold, docs/ structure.

### Changed / Notes

- Removed dead `MomentumState.peak` + `update_momentum_peak()` + call site (never read for decisions or audit; historical remnant). `MomentumState` now only carries `active`, `direction`, `trigger_time`.
- `MOMENTUM_TIMEOUT_SEC` (180s) moved into `StrategyParams.momentum_timeout_sec` (reads via RuntimeConfig overlay, fully sweepable/documented). The timeout value is now logged on expiry and documented in SPEC/README.
- Added pure unit test for momentum timeout branch.
- trading-engine side updated (SWEEP_FIELD_TO_CONST + _CONST_TO_SNAKE + Settings + test defaults) so that consuming apps get first-class sweep support for `momentum_timeout_sec` / `MOMENTUM_TIMEOUT_SEC`.
- **SignalAudit emission** on momentum timeout (`reason="momentum_timeout"`) for UAT/harness parity with `trend_veto`.
- Light defensive normalization for `trend_dir`/`position_dir` in hot paths (evaluate / manage_exit).
- SPEC.md: explicit notes on daily-loss-breach tick arming window and hard-stop (entry_price) vs vwap-stop (current vwap) reference difference.
- Type polish: `_try_activate_momentum` call site no longer assigns return value (was -> None but treated as signal).
- This package is the **reference implementation** of the VWAP + momentum pullback + P6 (trend filter + ATR-dynamic exits) logic previously developed inside the internal `theman` monorepo.
- Depends on `trading-engine>=0.2.0,<1.0`. Follows the three-repo architecture (see `docs/three-repo/README.md` and `strategy/SPEC.md`).
- Strategy decision logic is **pure** (no broker, no replay, no side effects except lightweight `StrategySideEffects` + audit logs). All heavy lifting (state machine, MockBroker, live Shioaji bootstrap) lives in `trading-engine` / `trading-backtest`.
- Strong emphasis: this reference strategy (and the package) is published for academic / personal research and learning. See README Disclaimer.

[0.1.0]: https://github.com/timhwchuang/strategy-vwap-momentum/releases/tag/v0.1.0
