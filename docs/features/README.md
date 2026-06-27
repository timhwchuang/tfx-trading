# Features（跨模組能力 ft）

> **一個 slug 一張 ft**：`docs/features/<slug>/` 收 SPEC（交付什麼）+ PLAN（怎麼交付）。  
> **落地後**契約併入 [`apps/trading-app/SPEC.md`](../apps/trading-app/SPEC.md) §Integration contracts（或對應 package SPEC），ft 標 **Landed**。

## Feature board

| ID | Slug | Status | Opened | Target | 文件 |
|----|------|--------|--------|--------|------|
| FT-001 | [audit-event-replay](audit-event-replay/SPEC.md) | **Landed** | 2026-06-17 | UAT→Pilot | [SPEC](audit-event-replay/SPEC.md) · [PLAN](audit-event-replay/PLAN.md) · [REVIEW](audit-event-replay/REVIEW.md) · **`/audit-event-replay`** |
| FT-002 | [smc-structure-filter](smc-structure-filter/SPEC.md) | **Draft** | 2026-06-18 | UAT | [SPEC](smc-structure-filter/SPEC.md) · [PLAN](smc-structure-filter/PLAN.md) · [REVIEW](smc-structure-filter/REVIEW.md) |
| FT-003 | [ai-backtest-tuning](ai-backtest-tuning/SPEC.md) | **MVPClosed** | 2026-06-26 | Strategy v2 | [SPEC](ai-backtest-tuning/SPEC.md) · [PLAN](ai-backtest-tuning/PLAN.md) · [**ROSTER**](ai-backtest-tuning/AGENT_ROSTER.md) · [`election_report.md`](../../workspaces/election_report.md) · [`workspaces/`](../../workspaces/) |

## 狀態定義

| Status | 意義 |
|--------|------|
| **Draft** | 僅文件；SPEC/PLAN 審閱中 |
| **InProgress** | 至少一個 Phase 已開程式 PR |
| **MVPClosed** | MVP 目標達成或 documented 收尾（如 `grid_no_viable_solution`）；後續可另開 v2 |
| **Landed** | 全 Phase 完成；穩定契約已併入 app/package SPEC |
| **Archived** | 可選；僅保留設計考古 |

```mermaid
stateDiagram-v2
  direction LR
  Draft --> InProgress: Phase1_start
  InProgress --> Landed: merge_app_SPEC
  Landed --> Archived: optional
```

## 與其他文件分工

| 文件 | 角色 |
|------|------|
| [`TODO.md`](../TODO.md) | 全專案 open items（可連結 ft，不取代 PLAN） |
| `docs/features/<slug>/` | 單一跨模組能力的設計 + 實作計劃 |
| app / package `SPEC.md` | **已落地**的穩定契約（runtime 真相） |
| [`ARCHIVE/`](../ARCHIVE/) | 已完成且已併入、僅供考古的舊 standalone spec |

## 開新 ft（SOP）

1. 複製 [`_template/`](_template/) → `docs/features/<slug>/`
2. 填 `SPEC.md` / `PLAN.md` 頂部 YAML frontmatter（`id`, `slug`, `status`, `opened`, `target`）
3. 在本表 **Feature board** 新增一列（下一個 ID：`FT-00N`）
4. 更新 [`DOC_MAP.md`](../DOC_MAP.md) §Features
5. 可選：在 [`TODO.md`](../TODO.md) 加一行連結至 PLAN
6. Phase 0 結束時 commit；`CHANGELOG.md` 記 docs 條目

**命名**：slug 用 kebab-case、描述能力（例：`audit-event-replay`），不要用 `misc` 或日期。

## 文件紀律（Agent MUST）

- ft **Draft / InProgress** 期間：以 `docs/features/<slug>/SPEC.md` 為設計真相
- ft **Landed** 後：**MUST** 將穩定欄位併入 app SPEC + **MUST** 更新 `CHANGELOG.md`；更新本 board 的 Status
- **MUST NOT** 長期維護與 app SPEC 矛盾的雙真相

模板：[`_template/SPEC.md`](_template/SPEC.md)、[`_template/PLAN.md`](_template/PLAN.md)