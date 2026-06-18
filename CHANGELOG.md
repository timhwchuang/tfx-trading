# Changelog — tfx-trading monorepo

All notable changes are documented here by package.  
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).  
Per-package `version` in `pyproject.toml` follows [SemVer](https://semver.org/) (0.x = API may still evolve).

Historical standalone-repo release links are kept for archaeology only; development continues in this monorepo.

---

## Docs

### [Unreleased]

#### Added

- **FT-002 Phase 4**：`regime_allows_entry` 接線；`structure_veto` / armed structure enrichment DECISION_AUDIT；`structure_stale` → `risk_blocked` audit；`record_structure_veto`；filter-on 3-run determinism；[`TODO.md`](docs/TODO.md) / [`WeeklyStatus.md`](docs/WeeklyStatus.md) / [`uat/APP.md`](docs/uat/APP.md) 同步 P6-SMC-CAL 指引。
- **FT-002 Phase 3 + sweep（A1–A8）**：`StructureRefreshPort` / `structure_stale` / `refresh_atr` 掛載；`structure_refresh.py`；config + runtime 互斥；`structure_calibration_cli --sweep`；`param_sweep` structure grid；`test_structure_stale_guards`。
- **FT-002 Phase 2** P6-SMC-CAL offline harness: `structure_calibration.py` + `structure_calibration_cli.py` —三組 counterfactual（no_filter / structure_only / trend_only）、friction-adjusted expectancy、`structure_events.csv` + `structure_armed_join.csv`、30s armed conversion；A/B-class tests + kbar fixture。
- **FT-002** SMC structure filter: SPEC v2 + PLAN Phase 1 complete + `REVIEW.md` Phase 1 re-review（PASS）；[`docs/TODO.md`](docs/TODO.md) §P6-SMC-CAL

---

## trading-engine

### [Unreleased]

#### Added

- **FT-002 Phase 4** `DecisionAudit` structure fields + `format_decision_audit` for `structure_veto` / armed enrichment。

- **KERNEL UAT regression** `tests/runtime/test_kernel_uat_regression.py`: B3 `event_code` 12/13 reconnect, B4 pending-timeout CRITICAL + `sync_positions` + `EXEC_AUDIT`, B6 `sync_positions` → `get_state_snapshot` chain (85 kernel tests).

- **FT-001 Phase 1** `DecisionAudit` + emitter in strategy; `episode_id` generation (date-seq); enriched `SignalAudit` (entry/exit fields); `EXEC` prep (pending ids stored in kernel).
- Audit fields are optional; old logs/parsers/determinism unaffected.

- **FT-001 Phase 2** Kernel `signal_id` assigned to every `OrderSignal`; `ExecAudit` + `EXEC_AUDIT` emissions for `pending_armed` / `pending_cancelled` / `pending_timeout` / `position_sync`.

### [0.2.2] - 2026-06-17

#### Added

- **P0** `RiskGate.atr_stale`: blocks new entries when last successful ATR refresh is older than `atr_refresh_sec × atr_stale_multiplier` (default 2×).
- **P4-13** Reconnect warmup: `reconnect_warmup_sec` (default 300) blocks new entries after reconnect until exchange tick ts catches up; exits still allowed.
- **P4-13** Daily disconnect limit: `max_disconnects_per_day` (default 3) sets `block_new_entry` + CRITICAL alert.
- **P4-13** Alert on disconnect with open position (`alert_on_disconnect_with_position`, default true).

#### Changed

- ATR refresh: `last_atr_refresh` advances only on **successful** kbars fetch; failed refreshes retry sooner (30s when never succeeded, else `atr_refresh_sec`).
- `_maybe_refresh_atr` uses in-flight guard to avoid duplicate daemon threads.

### [0.2.1] - 2026-06-16

Patch release to support `strategy-vwap-momentum` v0.1.0 (first public reference strategy plugin) and improve sweep integration.

#### Added

- `momentum_timeout_sec` (with const `MOMENTUM_TIMEOUT_SEC`) to `Settings`, `SWEEP_FIELD_TO_CONST`, `_CONST_TO_SNAKE`, and test defaults.
  - Enables first-class `patch_strategy_params` / sweep support for the momentum episode timeout in strategy plugins.
  - Default 180s (matching previous hardcoded value in the reference plugin).

#### Changed

- `SWEEPABLE_PARAMS` in consuming strategy plugins (e.g. `strategy-vwap-momentum`) will now automatically surface `MOMENTUM_TIMEOUT_SEC`.

### [0.2.0] - 2026-06-16

UAT-ready release addressing CodeReview#2 (see `docs/ARCHIVE/reviews/` for re-review).

#### Added

- `TradingEngine.get_state_snapshot()` and frozen `EngineStateSnapshot` for read-only state observation
- `_validate_order_signal()` — kernel rejects invalid `OrderSignal` before arming pending
- `RuntimeConfig.warn_if_placeholder_credentials()` on live login
- Docs: LIVE_SAFETY, UAT checklist, ARCHIVE migration notes
- README: Disclaimer, Live Safety, Go-Live Checklist, Secrets, Logging (`configure_root=False`)
- `.env.example`, `examples/minimal_live/`
- CI `quality` job: ruff lint/format, gradual mypy, explicit no-shioaji guard step
- Tests: `test_state_snapshot.py`, `test_signal_validation.py` (73 kernel tests total)

#### Changed

- Logger name `theman` → `trading_engine`; lazy `get_logger()` init
- SPEC.md: CI status, position model scope (§4.2.1), theman section historicalized
- Ruff format applied across `src/` and `tests/` (CI enforcement)

#### Fixed

- Removed last `theman` reference in `NullTelemetryPort` docstring

### [0.1.0] - 2026-06 (initial public release)

- Broker-agnostic futures execution kernel (Shioaji + Mock adapters)
- `position_qty` model, kernel-owned force-flatten, reconnect reconcile
- 63 kernel tests, GitHub Actions CI matrix (Python 3.11–3.13)
- Core docs: README, SPEC, DESIGN (now archived)

---

## trading-backtest

### [0.1.1] - 2026-06-16

#### Fixed

- `MockBroker.process_matching_queue`: coerce `tick.close` with `float()` so CSV replay ticks (str close) match against limit price without `TypeError`.

### [0.1.0] - 2026-06-16

Initial public release of the deterministic tick replay driver for `trading-engine`.

#### Added

- `BacktestEngine`: thin deterministic host that wires `TradingEngine` (exact same as live) + `MockBroker` + `VirtualClock` + replay loop.
- `MockBroker`: IOC matching, latency gate, normal/blowout/flatten slippage, no-lookahead kbars via loader, spread calibration option.
- `loader`: `iter_replay_ticks`, `ReplayTick`, kbar helpers, cache (plain + .gz), data-quality warnings.
- `VirtualClock`: injectable clock for determinism (no `time.time()`).
- `validation`: audit log parsing, determinism hash, backtest-vs-reference fill comparison.
- Examples: `compare_fill_audits.py`, `tick_cache_template.py`, `minimal_backtest_smoke.py`.
- Tests (25+): MockBroker, BacktestEngine, loader guards, validation helpers.
- Package metadata, MIT license, py.typed, runnable `python run_tests.py`.

#### Documentation (pre-release polish)

- Rewrote standalone SPEC.md — authoritative spec for this package.
- Added prominent **Backtest Fidelity & Limitations** sections to README and release notes.

#### Changed / Notes

- Depends on `trading-engine>=0.2.0,<1.0`. Iron laws: reuses same `TradingEngine`; no strategy hard-coding; determinism contract.

---

## strategy-vwap-momentum

### [Unreleased]

#### Added

- **FT-002 Phase 4** `_try_pullback_entry` 改用 `regime_allows_entry`；`structure_veto` DECISION_AUDIT；`momentum_armed` structure 戰場快照；`structure_stale` → `risk_blocked`。

- **FT-002 Phase 1** `strategy_vwap_momentum.structure`: frozen SMC v0.1 (`compute_structure`, `regime_allows_entry`, `structure_allows_entry`); 15+ unit tests (`test_structure.py`). No engine wiring yet (`structure_filter_enabled` not in runtime).

---

### [0.1.2] - 2026-06-17

#### Added

- Block new entries when `RiskGate.atr_stale` or `RiskGate.reconnect_warmup_active` (exits unchanged).

#### Changed

- Depends on `trading-engine>=0.2.2,<1.0`.

### [0.1.1] - 2026-06-16

#### Fixed

- `_try_pullback_entry`: define `trend_dir` from `market.trend_dir` before `trend_allows_entry` / `trend_veto` audit (fixes `NameError` on pullback entry path).

### [0.1.0] - 2026-06-16

Initial public release of the first reference `strategy-<name>` plugin for `trading-engine`.

#### Added

- `VWAPMomentumStrategy` — full implementation of the `trading_engine.core.strategy.Strategy` Protocol.
- `StrategyParams` + live overlay / sweep helpers for research & calibration.
- `trend.py` — `compute_trend`, Level-2 gating, dynamic trail / vwap-stop math.
- Rich `SignalAudit` builders; unit & behavior tests (~27 tests).
- Entry point registration: `trading_engine.strategies = "vwap_momentum"`.
- Package metadata, MIT license, py.typed, runnable `python run_tests.py`.

#### Changed / Notes

- Removed dead `MomentumState.peak` + `update_momentum_peak()`.
- `MOMENTUM_TIMEOUT_SEC` moved into `StrategyParams.momentum_timeout_sec` (sweepable).
- Depends on `trading-engine>=0.2.0,<1.0`.

---

## trading-app

### [Unreleased]

#### Added

- **FT-002 Phase 4** `observability.record_structure_veto` + `episode_funnel.structure_veto`；`uat_report` 將 `structure_veto` 計入 episode outcome `veto`。

- **FT-001 Phase 1**: `DECISION_AUDIT` + `DecisionAudit` dataclass + `format_decision_audit`; `momentum_armed` emission from `vwap-momentum` with `episode_id`; `SignalAudit`/`FillAudit` enriched with optional `episode_id`/`signal_id`/exit fields; `episode_id` propagated through pending to entry FILL.
- `build_exit_audit` now carries `entry_price`, `hold_ticks`, `in_grace`, stop levels, `trailing_peak`.
- Unit tests in `strategy` for armed DECISION and enriched exits (Phase 1 DoD).
- **FT-001** `docs/features/audit-event-replay/`: audit event replay SPEC + PLAN (qualified audit contract, episode timeline examples); `docs/features/` feature board + `_template/`.
- Grok project skill **`audit-event-replay`** (slash `/audit-event-replay`) for FT-001 implementation and audit contract review.
- FT-001 **REVIEW.md** (senior-trader): pressure metrics, high-pressure episode §6.4, Agent consumers §8.2; FT-002/003 scoped out.
- Grok project skill **`senior-trading-professional`** (slash `/senior-trading-professional`): risk-first trader persona for strategy review, Pilot Go/No-Go, sweep interpretation, CAL-8 framing.
- Role prompts: `prompts/roles/senior-trading-professional.md`, `prompts/roles/references/txf-gates.md` (UAT / Pilot / Live gate quick reference).

#### Added / Changed (UAT to Pilot hardening)

- `determinism_check.py` CLI for UAT evidence collection.
- `docs/uat/APP.md` (formerly UAT_CHECKLIST) v2: phased UAT→Pilot flow, evidence collection, Pilot Readiness Gate.
- Monorepo docs slim: single root CHANGELOG, centralized `docs/`.

#### FT-001 Phase 3 + Phase 4 (Audit Event Replay)

- **Phase 3**: `parse_decision_audit_line` / `parse_exec...`, `build_episode_timeline` + richer `Episode` (pressure_context, trade_date, outcome), `--episodes` / `--episode-id` CLI, `build_tuning_hints` using episode funnel + pressure, `DAILY_SUMMARY` with `episode_funnel` + `pressure` (max_consec, ratio, risk_blocked_count), streak emit in DECISION_AUDIT.
- Synthetic fixture + snapshot test for `--episodes`.
- **Phase 4 migration/land**: trend_veto/momentum_timeout/risk now primary via `DECISION_AUDIT` (legacy SIGNAL removed); determinism includes DEC/EXEC; contracts merged to `apps/trading-app/SPEC.md`; strategy SPEC updated; status → Landed.
- Risk_blocked now throttled (60s/reason).
- Full review fixes + 89+ tests green.

#### CLI discoverability

- **`python -m cli_help`**: catalog of all trading-app entry points; delegates to per-module `--help`.
- Richer `--help` epilog examples on `live`, `reporting`, `uat_evidence_export`, `pilot_gate_check`, `determinism_check`, `storage`, `backtest`.
- Root [`README.md`](README.md) + [`apps/trading-app/README.md`](apps/trading-app/README.md) CLI index tables.

#### Fixed (CLI discoverability follow-up)

- **`live --help`**: lazy-import Shioaji/engine after `argparse`; `raise SystemExit` exit semantics aligned with other CLIs.
- **`cli_help` delegate**: subprocess sets `cwd=src` and `PYTHONPATH` (app `src/` + monorepo sibling packages); removed dead `--list` flag.
- **Doc SSOT**: [`SPEC.md`](apps/trading-app/SPEC.md) + root [`README.md`](README.md) aligned with `CATALOG` (`storage`, `determinism_check`, `calibration_cli`); `storage.compress` documented as alias.
- **Tests**: +5 (`test_cli_help`: SPEC↔catalog drift guard, delegate mock/integration, `live --help` without `shioaji` import); **121** app tests green.

#### Hybrid ops (on-prem research + GCE live)

- **[`docs/ops/HYBRID_DEPLOY.md`](docs/ops/HYBRID_DEPLOY.md)**: 地雲雙管架構、GCE `asia-east1` 規格（`e2-standard-2` UAT/Pilot）、tick_cache rsync 流程。
- **[`docs/ops/LinuxOps.md`](docs/ops/LinuxOps.md)**: systemd、cron、`post-session.sh`；[`scripts/linux/`](scripts/linux/)（`start-trading-app.sh`, `install-systemd.sh`, `sync-from-gce.sh`）。
- **Doc sweep**: `python -m storage` 為主、`storage.compress` alias — [`TODO.md`](docs/TODO.md), [`AGENTS.md`](docs/AGENTS.md), [`uat/APP.md`](docs/uat/APP.md), [`WindowsOps.md`](docs/ops/WindowsOps.md)；測試基線 **269**（85+27+36+121）。
- **`calibration_cli`**: `--help` epilog examples；`cli_help.parse_spec_cli_modules()` 從 SPEC 解析防 catalog drift。

#### Fixed (hybrid ops review follow-up)

- **`install-systemd.sh`**: `chown -R tfx:tfx` monorepo + data dirs；env `640 root:tfx`；`TICK_ARCHIVE`/`KBARS_ARCHIVE` 預設啟用。
- **`post-session.sh`**: source `/etc/tfx-trading/env`；加 `determinism_check` → `snapshots/`；略過缺 log。
- **`sync-from-gce.sh`**: `ubuntu@` deploy 帳號；sync `kbar_cache/`；遠端缺目錄不 fail。
- **`parse_spec_cli_modules`**: 僅解析 SPEC `## CLI` 表格；`calibration_cli` Linux epilog；AGENTS/SPEC 測試數對齊。

#### UAT tooling (Phase 3–5 automation)

- **`reporting.uat_evidence_export`**: broker reconciliation + tick stratification CSV from `reports/day*.json`; merge-by-date; `--broker-data` import; invalid PnL safe-parse.
- **`sweep.pilot_gate_check`**: APP.md Phase 5 auto checklist (sample, density, expectancy, Sharpe per-trade/daily, MDD, big-loss streak, Critical scan); reads broker/tick evidence CSV when present.
- **`reporting.metrics_extract`** / **`reporting.evidence_csv`**: shared JSON→metric helpers + CSV validation for gate.
- **Episode timeline**: EXEC `pending_*` via `signal_id`; `position_sync` operational section in `--episodes` output.
- **Tests**: +23 (112 app tests); KERNEL regression in engine package.
- **Docs**: [`docs/uat/APP.md`](docs/uat/APP.md), [`uat_evidence/README.md`](uat_evidence/README.md), [`apps/trading-app/SPEC.md`](apps/trading-app/SPEC.md).

#### Changed

- BeforePilot content fully merged into [`docs/uat/APP.md`](docs/uat/APP.md) Phase 5 (Pilot Readiness Gate).
- Emphasis on determinism hash discipline from monorepo root.
- Phase 3/4 evidence CSV: manual copy-from-template → `python -m reporting.uat_evidence_export` (broker PnL still human/API sourced).

### [0.1.2] - 2026-06-17

#### Added

- P4-13 `operations` config: reconnect warmup, disconnect limits, `atr_stale_multiplier`
- Cumulative MDD risk budget in `uat_report` / `performance_metrics`

#### Changed

- Pin `trading-engine@v0.2.2`, `strategy-vwap-momentum@v0.1.2`
- Docs sync: README, SPEC, UAT, Architecture, WeeklyStatus

### [0.1.1] - 2026-06-16

#### Changed

- Remove deprecated `theman_*` port / config aliases; use `trading_app_*` symbols only
- Alert prefix `[theman]` → `[trading-app]`
- Windows ops: `start-trading-app.ps1`, `register-task.ps1` default task `trading-app-vwap`
- Pin siblings: `trading-backtest@v0.1.1`, `strategy-vwap-momentum@v0.1.1`

#### Fixed

- Sweep tick helpers: `ReplayTick.close` as `str` (pairs with backtest MockBroker float coercion fix)

### [0.1.0] - 2026-06-16

First public release as **reference integrator app** (renamed from internal `theman`).

#### Added

- `pyproject.toml`, `SPEC.md`, `LICENSE`, `.env.example`
- `trading_app_engine_ports()` wiring for live, backtest, and tests
- `reporting/` UAT log parser; `storage/` tick/kbar archive; `sweep/` param research tooling
- CI: standalone clone via git-tagged sibling packages

#### Changed

- Renamed from `theman` → `trading-app`
- Dependencies: `trading-engine`, `trading-backtest`, `strategy-vwap-momentum`
- App tests scoped to integration / storage / reporting / sweep (~30 tests)

#### Notes

- **UAT-ready**, not Live-ready — see `docs/uat/APP.md`