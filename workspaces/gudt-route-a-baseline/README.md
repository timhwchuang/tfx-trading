# FT-021 gudt-route-a-baseline

Plugin backtest for GUDT Route A UAT stack (B′+br5 + 5m EMA + distribution confirm flip).

## Run

```bash
cd apps/trading-app/src

# Unified backtest (FT-022)
CONFIG_PATH=../../../workspaces/gudt-route-a-baseline/config/config.yaml \
  python -m backtest --config ../../../workspaces/gudt-route-a-baseline/config/config.yaml \
  --dates-from-cache --from-date 2025-05-01 --to-date 2026-06-30 --report

# Thin wrapper (same path)
PYTHONPATH=. python scripts/ft021_run_baseline.py --from 2025-05-01 --to 2026-06-30

# Parity oracle (+1781 / extend=4 / flip=2) — unified bootstrap path
PYTHONPATH=. python scripts/ft021_parity_check.py --from 2025-05-01 --to 2026-06-30
```

## Parity SSOT

- Counterfactual: `workspaces/gudt-baseline/reports/gudt_route_a_uat_stack_*.md`
- Research: `workspaces/gudt-baseline/ROUTE_A_UAT_STACK.md`
