---
id: FT-008
slug: short-breakout
status: MVPClosed
opened: 2026-06-28
phases: [0, 1, 2, 3]
blockers: []
---

# FT-008 — Short Breakout（PLAN）

> **PLAN** = 怎麼交付 [`SPEC.md`](SPEC.md)。

## Phases

### Phase 0 — Counterfactual（v1 全時段）

- [x] `docs/features/short-breakout/{SPEC,PLAN}.md`
- [x] `short_breakout_counterfactual.py` + `ft008_short_breakout_counterfactual.py`
- [x] `workspaces/sb-baseline/reports/counterfactual_short_breakout.json`
- [x] 01–04 合計 — **未過**

### Phase 0 v2 — close_1h_only

- [x] `--close-1h-only` + `ft008_short_breakout_v2_close_1h.py`
- [x] valid **通過**；01–04 **未過**
- [x] [`gate_report_v2.md`](../../../workspaces/sb-baseline/gate_report_v2.md)

```bash
cd apps/trading-app/src
$env:PYTHONPATH="."
python scripts/ft008_short_breakout_v2_close_1h.py --cache-dir ../../../tick_cache
```

### Phase 1 — Plugin

- [ ] **暫緩** — 01–04 未過（overfit 風險）

### Phase 2 — Baseline

- [ ] `sb-baseline/config` + `ft008_run_baseline.py`

### Phase 3 — Go/No-Go

- [ ] holdout 2026-05（若未來重開）

## Workspace

```
workspaces/sb-baseline/
  reports/counterfactual_short_breakout.json
  reports/counterfactual_v2_close_1h_valid.json
  reports/counterfactual_v2_close_1h_0104.json
  gate_report.md
  gate_report_v2.md
```
