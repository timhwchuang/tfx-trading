# FT-021 gudt-route-a-baseline

Plugin backtest for GUDT Route A UAT stack (B′+br5 + 5m EMA + distribution confirm flip).

## Three-layer reports

| Layer | Script | Artifact |
|-------|--------|----------|
| Decision parity | `ft021_parity_check.py` | `reports/parity_report_{label}.json` |
| Kernel replay | `ft021_run_baseline.py` | `logs/baseline_{label}.log`, `reports/day_plans_{label}.json` |
| **Execution parity** | `ft021_execution_parity.py` | `reports/execution_parity_{label}.json` + `.md` |

Hard gate (execution): **CF round count == kernel round count** (`n` must match).

## Date slices (default UAT_2m)

All `ft021_*` scripts share the same slice arguments. Priority: `--from/--to` > `--months` > `--spot-check` > `--slice` > default `UAT_2m` (2026-05-01 .. 2026-06-30).

```bash
cd apps/trading-app/src

# Daily UAT (default UAT_2m)
FT003_HOLDOUT_UNSEAL=1 PYTHONPATH=. \
  python scripts/ft021_execution_parity.py

# Baseline + execution report in one shot
FT003_HOLDOUT_UNSEAL=1 PYTHONPATH=. \
  python scripts/ft021_run_baseline.py --execution-report

# Single month spot audit
FT003_HOLDOUT_UNSEAL=1 PYTHONPATH=. \
  python scripts/ft021_execution_parity.py --months 2026-03

# Reproducible random month audit (excludes UAT_2m months)
FT003_HOLDOUT_UNSEAL=1 PYTHONPATH=. \
  python scripts/ft021_execution_parity.py --spot-check 2 --spot-seed 42

# Full oracle range (overnight, not UAT blocker)
FT003_HOLDOUT_UNSEAL=1 PYTHONPATH=. \
  python scripts/ft021_parity_check.py --slice full

# Compare-only (reuse existing log/plans)
PYTHONPATH=. python scripts/ft021_execution_parity.py --compare-only \
  --log ../../../workspaces/gudt-route-a-baseline/logs/baseline_UAT_2m.log \
  --plans ../../../workspaces/gudt-route-a-baseline/reports/day_plans_UAT_2m.json \
  --slice UAT_2m
```

Named slices: `UAT_2m`, `H1_2026`, `full` (see `reporting/date_slices.py`).

Backtest speed (GUDT): replay uses **reconcile fast-path** + **event-anchored tick jump** in `trading-backtest` (~4× faster vs full tick scan; UAT_2m ~78s, 6M H1 ~3min on this host).

## UAT workflow

1. **Required**: `--slice UAT_2m` → `EXECUTION_PARITY_PASS`, `n` consistent
2. **Recommended**: `--spot-check 2` or `--months YYYY-MM` on holdout months → same report format
3. **Optional**: `--slice full` for decision oracle only

Record spot-check results in `reports/SPOT_CHECK_LOG.md`.

### GCE Live（systemd）

VM 上 `/etc/tfx-trading/env` 預設應為：

```bash
CONFIG_PATH=/opt/tfx-trading/workspaces/gudt-route-a-baseline/config/config.yaml
```

換策略或改參數後：`sudo systemctl restart tfx-trading`。收盤 cron 與 post-session 見 [`docs/ops/LinuxOps.md`](../../docs/ops/LinuxOps.md)。

## Parity SSOT

- Counterfactual: `workspaces/gudt-baseline/reports/gudt_route_a_uat_stack_*.md`
- Research: `workspaces/gudt-baseline/ROUTE_A_UAT_STACK.md`
