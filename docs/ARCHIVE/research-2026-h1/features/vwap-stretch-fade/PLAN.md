---
id: FT-006
slug: vwap-stretch-fade
status: InProgress
opened: 2026-06-28
phases: [0, 1, 2, 3]
blockers: []
---

# FT-006 — VWAP Stretch Fade（PLAN）

> **PLAN** = 怎麼交付 [`SPEC.md`](SPEC.md)。

## Phases

### Phase 0 — Counterfactual

- [x] `docs/features/vwap-stretch-fade/{SPEC,PLAN}.md`
- [x] `vwap_stretch_fade_counterfactual.py` + `ft006_vwap_stretch_fade_counterfactual.py`
- [x] `workspaces/vsf-baseline/reports/counterfactual_vwap_stretch_fade.json`

**Phase 0 通過**：任一（k × bucket）`gross_mean > 5`、`net_mean > 0`、`n ≥ 30`。

```bash
cd apps/trading-app/src
$env:PYTHONPATH="."
python scripts/ft006_vwap_stretch_fade_counterfactual.py \
  --code TMFR1 --cache-dir ../../../tick_cache \
  --from-date 2026-04-01 --to-date 2026-04-30
```

### Phase 1 — Plugin（Phase 0 過關後）

- [x] `packages/strategies/vwap-stretch-fade/`

### Phase 2 — Baseline

- [x] `vsf-baseline/config` + `ft006_run_baseline.py`

### Phase 3 — Go/No-Go

- [x] gate_report + WeeklyStatus + strategy_diagnosis §7（**Go — Pilot-prep**；人類簽核 + holdout 待辦）

## Workspace

```
workspaces/vsf-baseline/
  reports/counterfactual_vwap_stretch_fade.json
  gate_report.md
```
