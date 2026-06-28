---
id: FT-009
slug: opening-range-breakout
status: MVPClosed
opened: 2026-06-28
phases: [0, 1, 2, 3]
blockers: []
---

# FT-009 — Opening Range Breakout（PLAN）

## Phase 0 — Counterfactual（01–04 主判）

- [x] SPEC + PLAN
- [x] `orb_counterfactual.py` + `ft009_orb_counterfactual.py`
- [x] gate_report — **01–04 通過**

```bash
cd apps/trading-app/src
$env:PYTHONPATH="."
python scripts/ft009_orb_counterfactual.py --cache-dir ../../../tick_cache
```

## Phase 1 — Plugin

- [x] `strategy-opening-range-breakout` + `ft009_run_baseline.py`
- [x] 01–04 plugin 對帳（73 趟 net +1.29）
- [x] holdout 2026-05 — **未過**（MVPClosed）

## Workspace

```
workspaces/orb-baseline/
  reports/counterfactual_orb_0104.json
  reports/counterfactual_orb_valid.json
  gate_report.md
```
