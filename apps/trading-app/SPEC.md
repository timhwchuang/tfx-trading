# trading-app — Reference Integrator App

> **Role**: compose `trading-engine` + `trading-backtest` + strategy plugins into a runnable deployment (GCE/Windows live + on-prem backtest) with config, storage, reporting, and UAT tooling.  
> **Not** a fourth core library — kernel and strategy alpha live in `packages/` (monorepo).

## Dependency direction

```mermaid
flowchart TD
    APP[trading-app]
    TE[trading-engine]
    BT[trading-backtest]
    SV[strategy-vwap-momentum]

    APP --> TE
    APP --> BT
    APP --> SV
    BT --> TE
    SV --> TE
```

- App **must not** be imported by any sibling package.
- App owns side effects: YAML config, tick archive, Telegram, UAT reports, param sweep orchestration.

## In scope (this repo)

| Module | Responsibility |
|--------|----------------|
| `src/integrations/` | `trading_app_engine_ports()` — telemetry, alerts, archive, trend refresh, adapter selection |
| `src/core/runtime_config.py` | `TradingAppRuntimeConfig` — YAML + env flags (`TICK_ARCHIVE`, etc.) |
| `src/live/` | `python -m live` — Shioaji + TradingEngine entry |
| `src/backtest/engine.py` | Thin wrapper injecting app ports into `trading_backtest.BacktestEngine` |
| `src/storage/` | Tick/kbar archive and loaders |
| `src/backfilldata/` | `python -m backfilldata` — Shioaji historical tick/kbar backfill CLI |
| `src/reporting/` | `uat_report`, `uat_evidence_export`, `metrics_extract`, `evidence_csv`, performance metrics, trend calibration |
| `src/sweep/` | Walk-forward param sweep, `pilot_gate_check`, determinism gate |
| `config/config.yaml` | Strategy/runtime parameters (non-secrets) |

## Out of scope

| Concern | Owner |
|---------|-------|
| Trading state machine | `trading-engine` |
| Tick replay / MockBroker | `trading-backtest` |
| VWAP momentum alpha | `strategy-vwap-momentum` |
| PyPI publish of kernel | sibling repos |

## Public wiring API

```python
from integrations.engine_wiring import (
    trading_app_engine_ports,
    default_strategy,
    order_adapter_for,
)
from trading_engine.engine import TradingEngine

ports = trading_app_engine_ports(api=api, use_mock_adapter=False, with_alerts=True, with_archive=True)
TradingEngine(
    api=api,
    strategy=default_strategy(ports["runtime_config"], ports["obs"]),
    **{k: v for k, v in ports.items() if k != "obs"},
).start()
```

## CLI (from `src/` or `PYTHONPATH=src`)

| Command | Purpose |
|---------|---------|
| `python -m cli_help` | CLI catalog; `python -m cli_help <module>` → module `--help` |
| `python -m live` | Simulation or live session |
| `python -m backtest` | App-wired backtest; `--dates` or `--dates-from-cache` (+ optional `--from-date`/`--to-date`) |
| `python -m reporting <log>` | UAT metrics; `--json` / `--trend` / `--episodes` |
| `python -m reporting.uat_evidence_export <broker\|tick\|both> reports/day*.json` | Broker reconciliation + tick stratification CSV |
| `python -m reporting.calibration_cli <log> --dates YYYY-MM-DD` or `--dates-from-cache` | P6-1 trend filter calibration (CAL-8) |
| `python -m reporting.structure_calibration_cli <log> --dates YYYY-MM-DD` | P6-SMC-CAL structure vs trend counterfactual harness |
| `python -m sweep.pilot_gate_check reports/day*.json` | APP.md Phase 5 Pilot Readiness Gate |
| `python -m sweep.determinism_check --date YYYY-MM-DD --mode hash` | Backtest audit hash / reproducibility |
| `python -m storage` | Post-session tick gzip (`storage.compress` alias) |
| `python -m backfilldata date YYYY-MM-DD` | Backfill past ticks/kbars into `tick_cache/` + `kbar_cache/` |

## Integration contracts

Stable interfaces between runtime, reporting, and research tooling. **Do not** change log prefixes or JSON field names without updating `reporting/uat_report.py`, determinism tests, and this section.

### Audit log (runtime → reporting)

| Prefix | Emitter | Consumer |
|--------|---------|----------|
| `DECISION_AUDIT {json}` | strategy (non-OrderSignal decisions: armed, timeout, veto, risk_blocked) | `uat_report` (Phase 3+ --episodes, pressure) |
| `SIGNAL_AUDIT {json}` | runtime on each `OrderSignal` | `uat_report.parse_log_audits_and_fills` |
| `EXEC_AUDIT {json}` | kernel (pending_armed, cancelled, timeout, position_sync) | `uat_report` (timeline) |
| `FILL_AUDIT {json}` | runtime on each fill | `uat_report.parse_log_audits_and_fills` |
| `DAILY_SUMMARY {json}` | trading-day rollover / shutdown | `uat_report`, `param_sweep` |

**DECISION_AUDIT** — `trading-engine/core/audit/decision_audit.py` (`DecisionAudit`, Phase 3+):

- `audit_schema_version`: 1
- `event_type`: `momentum_armed` | `momentum_timeout` | `trend_veto` | `risk_blocked` | ...
- `ts`, `episode_id`
- For `momentum_armed`: `direction`, `trigger_price`, `vol_1s`, `buy_ratio`, `sell_ratio`, `vol_threshold`, `multiplier`, (optional: `vwap`, `atr`, streaks)
- For others: `price`, `block_reason`, `elapsed_sec`, `reason`, `consecutive_*_streak`, `episodes_since_last_entry`, etc.

Serialization: `json.dumps(..., ensure_ascii=False, separators=(",", ":"))`

**EXEC_AUDIT** — `trading-engine/core/audit/exec_audit.py` (`ExecAudit`, Phase 2+):

- `audit_schema_version`: 1
- `event_type`: `pending_armed` | `pending_cancelled` | `pending_timeout` | `position_sync`
- `ts`, `signal_id`
- `pending_armed`: `order_id`, `limit_price`, `direction`
- `pending_cancelled`: `tag`, `order_id` (if any)
- `pending_timeout`: `pending_sec`
- `position_sync`: `qty_before`, `qty_after`, `position_dir`

**SIGNAL_AUDIT** — `core/audit/signal_audit.py` (`SignalAudit`):

- `intent`: `"entry"` \| `"exit"`
- `direction`: `"Buy"` \| `"Sell"`
- `price`, `ts`
- `vol_1s`, `buy_ratio`, `sell_ratio`
- `atr`, `multiplier`, `vol_threshold`, `vwap`
- `reason`, `trend_dir`, `trend_strength`, `trail_points_used`
- (optional Phase 1+: `episode_id`, `signal_id`, `elapsed_since_arm_sec`, `dist_vwap`, exit enrich fields)

Serialization: `json.dumps(asdict(audit), ensure_ascii=False, separators=(",", ":"))`

**FILL_AUDIT** — `observability.FillAudit`:

- `intent`, `direction`, `signal_price`, `fill_price`
- `slippage_pts`, `limit_price`, `slippage_vs_limit_pts`
- `order_id`, `ts`, `hold_sec`, `pnl_points`, `exit_reason`, `ioc_slippage_allowed`

**DAILY_SUMMARY** — `observability.DailyObservability.build_summary()`: near-miss stats, tick-type distribution, risk state, optional `performance` from `performance_metrics`.

**Auxiliary UAT lines** (regex-parsed): `MOMENTUM Long|Short 突破`, `tick_type 分布 | ...`, `委託未成交/已取消`.

**emit_policy** (future FT-002): per-event `required` | `optional` | `toggleable` (documented in FT-001 SPEC; toggle not yet implemented).

### Sweep & determinism (research — not a UAT gate)

App-layer tooling: determinism hash gate + walk-forward param sweep (`src/sweep/`, `src/reporting/`). Strategy trend calibration semantics: [`packages/strategies/vwap-momentum/SPEC.md`](../../packages/strategies/vwap-momentum/SPEC.md) §6.1 · progress [`docs/TODO.md`](../../docs/TODO.md) §P6-1-CAL.

**Determinism** (`sweep/determinism_check.py`) — `run_hash(code, dates, cache_dir) -> str`:

- Collect `SIGNAL_AUDIT`, `FILL_AUDIT`, `DAILY_SUMMARY`, `DECISION_AUDIT`, `EXEC_AUDIT` JSON; normalize; SHA-256
- Hash JSON body only (no log timestamps); `sort_keys=True, separators=(",", ":")`
- Strip `DAILY_SUMMARY.operational` wall-clock fields: `lock_wait_max_ms`, `lock_wait_over_50ms`, `no_tick_resubscribe`, `atr_min`, `atr_max`
- Include `DAILY_SUMMARY` decision fields
- DECISION/EXEC: full decision body (no wall-clock)

Tests: `tests/sweep/test_determinism.py` (`test_three_runs_same_hash`, `test_three_runs_same_hash_with_kbars_and_fills`, `test_daily_summary_in_hash`, `test_hash_robust_to_key_order`, `test_hash_ignores_operational_wall_clock`, `test_uat_report_parses_backtest_log`).

**Param sweep** (`sweep/param_sweep.py`) — `sweep(grid, dates_train, dates_valid, code, cache_dir)`:

1. Patch strategy params via `StrategyParams` / config overlay
2. Train backtest → KPI; valid backtest → KPI (out-of-sample)
3. Emit `{params, train_kpi, valid_kpi, veto_metrics?}`; rank on **valid** only
4. Output: `sweep_result.jsonl`

Trend grid (CAL-3): when grid contains `trend_*` keys, attach `veto_metrics` from harness. B-class replay: `forward_policy=ForwardPnlPolicy(...)`; CLI `python -m reporting.calibration_cli ... --sweep`. `quick_stop_loss_rate` = `Σ quick_sl / Σ exits` (weighted).

Tests (`tests/sweep/test_param_sweep.py`): `test_sweep_small_grid`, `test_config_restored`, `test_daily_summary_params_match_sweep`, `test_sweep_params_affect_entry`, `test_sweep_with_trend_params_attaches_veto_metrics`. Scoring: `reporting/performance_metrics.py` survival KPIs.

| Module | Path |
|--------|------|
| Determinism | `src/sweep/determinism_check.py` |
| Param sweep | `src/sweep/param_sweep.py` |
| UAT report | `src/reporting/uat_report.py` |
| Evidence CSV export | `src/reporting/uat_evidence_export.py` |
| Evidence CSV validation | `src/reporting/evidence_csv.py` |
| Pilot gate | `src/sweep/pilot_gate_check.py` |
| Trend harness | `src/reporting/trend_calibration.py` |
| Forward PnL replay | `src/reporting/forward_pnl.py` |
| B-class CLI | `src/reporting/calibration_cli.py` |

**Done**: same inputs → same hash (with fills); sweep restores config; `uat_report` parses backtest logs; app **161** tests green (`python run_tests.py`)；FT-001 Phase 4 landed (DEC/EXEC in contracts + determinism); UAT evidence export + Pilot gate automation; `backfilldata` historical cache CLI.

### UAT execution

[`docs/uat/KERNEL.md`](../../docs/uat/KERNEL.md) + [`docs/uat/APP.md`](../../docs/uat/APP.md)（含 Pilot Readiness Gate）。

## Install (monorepo)

From repo root:

```bash
bash scripts/setup-dev.sh
```

Or path editable only:

```bash
pip install -r apps/trading-app/requirements.txt
```

模組邊界與資料流：見本檔開頭 **In scope** 表、**Dependency direction**、§Integration contracts。依賴契約：[`packages/trading-engine/SPEC.md`](../../packages/trading-engine/SPEC.md)、[`packages/trading-backtest/SPEC.md`](../../packages/trading-backtest/SPEC.md)。

## Status

**v0.1.2** — UAT-ready reference deployment with P0/P4-13 live guards. `simulation: true` default in `config/config.yaml`. Live / Pilot requires human Go/No-Go per [`docs/uat/APP.md`](../../docs/uat/APP.md)（含量化 Pilot Readiness Gate）。