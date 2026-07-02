# FT-023 — Plan

## Phases

- [x] Phase 1 — `wash_beta.py` + planner + ledger script
- [x] Phase 2 — `GudtWashBetaStrategy` + bootstrap + backtest hooks
- [x] Phase 3 — H1 2026 execution parity PASS (`44/44`)
- [ ] Phase 4 — LinuxOps CONFIG_PATH
- [ ] Phase 5 — Bugbot ≤3 rounds

## Commands

```bash
cd apps/trading-app/src
FT003_HOLDOUT_UNSEAL=1 PYTHONPATH=. python scripts/ft023_execution_parity.py \
  --from 2026-01-01 --to 2026-06-30 --append-spot-log
```

```bash
PYTHONPATH=. python -m pytest ../../../packages/strategies/gudt-route-a/tests/test_wash_beta.py -q
```
