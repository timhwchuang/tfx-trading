# Changelog

All notable changes to `trading-backtest` are documented here.  
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).  
Versioning follows [SemVer](https://semver.org/) and tracks `trading-engine` major per spec (0.x = API may still evolve).

## [0.1.1] - 2026-06-16

### Fixed

- `MockBroker.process_matching_queue`: coerce `tick.close` with `float()` so CSV replay ticks (str close) match against limit price without `TypeError`.

[0.1.1]: https://github.com/timhwchuang/trading-backtest/releases/tag/v0.1.1

## [0.1.0] - 2026-06-16

Initial public release of the deterministic tick replay driver for `trading-engine` (completes the public three-repo core with trading-engine + strategy-vwap-momentum).

### Added
- `BacktestEngine`: thin deterministic host that wires `TradingEngine` (exact same as live) + `MockBroker` + `VirtualClock` + replay loop. Reuses `TradingEngine` for state machine, pending, session, risk gates.
- `MockBroker`: IOC matching, latency gate, normal/blowout/flatten slippage, no-lookahead kbars via loader, spread calibration option.
- `loader`: `iter_replay_ticks`, `ReplayTick`, kbar helpers (`iter_kbars_in_range`, save/load), cache (plain + .gz), `DEFAULT_CACHE_DIR`, data-quality warnings (sort, duplicate ts, non-positive price, large jumps).
- `VirtualClock`: injectable clock for determinism (no `time.time()`).
- `validation`: audit log parsing, determinism hash (`hash_audit_records`), backtest-vs-reference fill comparison (`compare_fill_audits`).
- Examples: `compare_fill_audits.py`, `tick_cache_template.py`, `minimal_backtest_smoke.py`.
- Tests (25+): MockBroker, BacktestEngine, loader guards, validation helpers.
- Package metadata, MIT license, py.typed, runnable `python run_tests.py`.
- `README.md`, standalone `SPEC.md`, CHANGELOG.md, CI scaffold, docs/releases/.
- theman thin wrappers already delegate (`src/backtest/engine.py` etc.); remaining call-site cleanups coordinated.

### Documentation (pre-release polish)
- Rewrote standalone [SPEC.md](SPEC.md) — authoritative spec for this repo (replaces broken `backtest/SPEC.md` pointers from monorepo extraction).
- Added prominent **Backtest Fidelity & Limitations** sections to README and `docs/releases/v0.1.0.md`.
- Fixed `pyproject.toml` Documentation URL and all in-repo broken links.

### Changed / Notes
- This package is the **reference implementation** of the Backtest role in the three-repo ecosystem (see `SPEC.md` §1).
- Depends on `trading-engine>=0.2.0,<1.0`. Follows iron laws: Backtest only depends on Trading; reuses same `TradingEngine`; no strategy hard-coding; determinism (single-thread, sync orders, VirtualClock, byte-identical audits).
- theman `BacktestEngine` is now thin delegation (M2 per spec); app/sweep/CLI updated to external package.

[0.1.0]: https://github.com/timhwchuang/trading-backtest/releases/tag/v0.1.0
