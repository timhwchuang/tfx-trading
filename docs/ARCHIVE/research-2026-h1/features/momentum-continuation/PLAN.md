---
id: FT-004
slug: momentum-continuation
status: MVPClosed
closed: 2026-06-28
closure: thesis_a_no_go
phases: [0, 1, 2, 3]
blockers: []
---

# FT-004 — Momentum Continuation（PLAN）

> **PLAN** = 怎麼交付 [`SPEC.md`](SPEC.md)。Phase checkbox 隨 PR 更新。

## Scope

- 新 plugin `packages/strategies/momentum-continuation/`
- Workspace `workspaces/mc-baseline/`（config、logs、reports、gate）
- Counterfactual 腳本（Phase 0）
- Baseline 回測 2026-04 valid + 對照 v1 KPI

## Out of scope

- UAT live 切換 plugin（須 G2 + 人類）
- FT-003 leaderboard / round2 grid
- trend / structure filter 預設開啟
- Phase 4 sweep（G1 通過後另開）

## Dependencies

| 項目 | 狀態 |
|------|------|
| FT-003 `grid_no_viable_solution` 收尾 | ✅ |
| `tick_cache` 2026-01～05 | ✅ |
| `entry_funnel` / armed forward 統計 | ✅ |
| `trading-engine` Strategy Protocol | ✅ |

## Phases

### Phase 0 — 文件 + Counterfactual

- [x] `docs/features/momentum-continuation/{SPEC,PLAN}.md`
- [x] Feature board + DOC_MAP + TODO + CHANGELOG
- [x] `ft004_armed_forward_counterfactual.py`
- [x] `workspaces/mc-baseline/reports/counterfactual_armed_forward.json`

```bash
cd apps/trading-app/src
$env:PYTHONPATH="."
python scripts/ft004_armed_forward_counterfactual.py \
  --log ../../../workspaces/agent-conservative/logs/baseline_valid.log \
  --cache-dir ../../../tick_cache \
  --from-date 2026-04-01 --to-date 2026-04-30
```

### Phase 1 — Plugin

- [x] `packages/strategies/momentum-continuation/`（`MomentumContinuationStrategy`）
- [x] `setup-dev.sh` / `run-all-tests.sh` / `apps/trading-app` 依賴
- [x] `engine_wiring.load_named_strategy("momentum_continuation")`
- [x] Settings：`hard_stop_atr_k`, `tp_atr_k`, `max_adverse_atr_k`（app + engine + SWEEP）
- [x] 單元測試

### Phase 2 — Baseline 回測

- [x] `workspaces/mc-baseline/config/config.yaml`
- [x] `scripts/ft004_run_baseline.py`（2026-04 valid + 可選 diagnostic 月）
- [x] `workspaces/mc-baseline/reports/baseline_valid.json`
- [x] `workspaces/mc-baseline/gate_report.md`（G1–G4 填寫）

### Phase 3 — 人類 Go/No-Go

- [x] Agent 填寫 `gate_report.md`（G1–G4 + v1 對照 + counterfactual 分層）
- [x] 記錄於 [`docs/WeeklyStatus.md`](../../WeeklyStatus.md)
- [x] **人類簽核** — **No-Go**；§a arm 調參 + §b adverse guard 已試
- [x] **本回合收尾** — 見 SPEC §8；**不** Phase 4 sweep / holdout

### Phase 4–5 — 已取消

- [x] ~~sweep / holdout~~ — Thesis A 未過 G1，依 SPEC §6 不執行

## 收尾狀態

| 項目 | 狀態 |
|------|------|
| Feature status | **MVPClosed**（`thesis_a_no_go`） |
| Live / UAT plugin | `strategy-vwap-momentum`（凍結）；**勿**切 `momentum_continuation` |
| 證據目錄 | [`workspaces/mc-baseline/`](../../../workspaces/mc-baseline/) |
| 下一方向 | timeout-selective thesis（**未開**新 ft 文件） |

## Workspace 路徑

```
workspaces/mc-baseline/
  config/config.yaml
  logs/baseline_valid.log
  reports/baseline_valid.json
  reports/counterfactual_armed_forward.json
  gate_report.md
```

## Acceptance（關閉 Draft → MVPClosed）

- [x] Phase 0–3 產物齊全 + 測試全綠
- [x] `gate_report.md` 含 G1–G4、調參歷程、**No-Go §Decision**
- [x] SPEC §8 本回合收尾聲明
