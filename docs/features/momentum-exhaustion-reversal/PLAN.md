---
id: FT-007
slug: momentum-exhaustion-reversal
status: Draft
opened: 2026-06-28
phases: [0, 1, 2, 3]
blockers: []
---

# FT-007 — Momentum Exhaustion Reversal（PLAN）

> **PLAN** = 怎麼交付 [`SPEC.md`](SPEC.md)。

## Phases

### Phase 0 — Pilot counterfactual（5 日）

- [x] `docs/features/momentum-exhaustion-reversal/{SPEC,PLAN}.md`
- [x] `impulse_absorption_counterfactual.py` + `ft007_impulse_absorption_counterfactual.py`
- [x] `workspaces/mer-baseline/reports/counterfactual_pilot.json`

**Phase 0 結果**：**未過** — 5 日合計 2 事件，gross −10/趟。

**Pilot 日**：2026-01-15、02-20、03-12、04-08、04-22

**Phase 0 通過**：任一（`impulse_bars` × bucket）`gross_mean > 5`、`net_mean > 0`、`n ≥ 20`。

```bash
cd apps/trading-app/src
$env:PYTHONPATH="."
python scripts/ft007_impulse_absorption_counterfactual.py --pilot
```

### Phase 1 — Plugin（Phase 0 過關後）

- [ ] `packages/strategies/momentum-exhaustion-reversal/`

### Phase 2 — Baseline 01–04

- [ ] `mer-baseline/config` + `ft007_run_baseline.py`
- [ ] 合計 + 分月 `gate_report.md`

### Phase 3 — Go/No-Go

- [x] gate_report + 人類 **放棄**（v3 全未過；不跑 01–04）

## 資料切分（本 thesis）

| 區間 | 用途 |
|------|------|
| Pilot 5 日 | Phase 0 現象驗證 |
| 01–03 | 開發 / 單軸掃描（若需要） |
| **01–04 合計** | **Gate G1–G5 主報表** |
| 05 | Holdout（封印） |

## Workspace

```
workspaces/mer-baseline/
  reports/counterfactual_pilot.json
  gate_report.md
```
