---
id: FT-005
slug: timeout-continuation
status: MVPClosed
closed: 2026-06-28
closure: thesis_b_phase0_no_go
phases: [0]
blockers: []
---

# FT-005 — Timeout-Selective Continuation（PLAN）

> **PLAN** = 怎麼交付 [`SPEC.md`](SPEC.md)。Phase checkbox 隨 PR 更新。

## Scope

- Phase 0 counterfactual（timeout 進場時點敏感度）
- ~~新 plugin~~ — **取消**（Phase 0 未過）
- Workspace `workspaces/tc-baseline/`（reports + gate only）

## Out of scope

- 修改 v1 `strategy-vwap-momentum` 或 UAT config
- FT-004 `momentum_continuation` 解凍
- Holdout

## Dependencies

| 項目 | 狀態 |
|------|------|
| FT-004 MVPClosed + counterfactual 基礎設施 | ✅ |
| v1 baseline log + `tick_cache` 2026-04 | ✅ |

## Phases

### Phase 0 — 文件 + Counterfactual

- [x] `docs/features/timeout-continuation/{SPEC,PLAN}.md`
- [x] Feature board + DOC_MAP + TODO + CHANGELOG
- [x] `timeout_entry_counterfactual.py` + `ft005_timeout_entry_counterfactual.py`
- [x] `workspaces/tc-baseline/reports/counterfactual_timeout_entry.json`
- [x] **Phase 0 決策：No-Go** — `timeout_tick` gross **4.10**、net **-0.90**

### Phase 1–2 — 已取消

- [x] ~~plugin~~ / ~~baseline~~ — Phase 0 未過預檢（見 SPEC §8）

### Phase 3 — 收尾

- [x] `gate_report.md` Phase 0 §Decision
- [x] WeeklyStatus + strategy_diagnosis §7

## 收尾狀態

| 項目 | 狀態 |
|------|------|
| Feature status | **MVPClosed**（`thesis_b_phase0_no_go`） |
| Live / UAT plugin | `strategy-vwap-momentum` |
| 證據目錄 | [`workspaces/tc-baseline/`](../../../workspaces/tc-baseline/) |

## Workspace 路徑

```
workspaces/tc-baseline/
  reports/counterfactual_timeout_entry.json
  gate_report.md
```
