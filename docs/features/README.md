# Features（跨模組能力 ft）

> **一個 slug 一張 ft**：`docs/features/<slug>/` 收 SPEC（交付什麼）+ PLAN（怎麼交付）。  
> **落地後**契約併入 [`apps/trading-app/SPEC.md`](../apps/trading-app/SPEC.md) §Integration contracts（或對應 package SPEC），ft 標 **Landed**。

## Feature board

| ID | Slug | Status | Opened | Target | 文件 |
|----|------|--------|--------|--------|------|
| FT-001 | [audit-event-replay](audit-event-replay/SPEC.md) | **Landed** | 2026-06-17 | UAT→Pilot | [SPEC](audit-event-replay/SPEC.md) · [PLAN](audit-event-replay/PLAN.md) · [REVIEW](audit-event-replay/REVIEW.md) · **`/audit-event-replay`** |
| FT-002 | [smc-structure-filter](smc-structure-filter/SPEC.md) | **MVPClosed** | 2026-06-18 | — | [SPEC §12](smc-structure-filter/SPEC.md) · 工程 1–4 ✅ · **CAL-8 放棄** |
| FT-003 | [ai-backtest-tuning](ai-backtest-tuning/SPEC.md) | **MVPClosed** | 2026-06-26 | Strategy v2 | [SPEC](ai-backtest-tuning/SPEC.md) · [PLAN](ai-backtest-tuning/PLAN.md) · [**ROSTER**](ai-backtest-tuning/AGENT_ROSTER.md) · [`election_report.md`](../../workspaces/election_report.md) · [`workspaces/`](../../workspaces/) |
| FT-004 | [momentum-continuation](momentum-continuation/SPEC.md) | **MVPClosed** | 2026-06-27 | Pilot-prep | [SPEC](momentum-continuation/SPEC.md) §8 · [PLAN](momentum-continuation/PLAN.md) · [`gate_report`](../../workspaces/mc-baseline/gate_report.md) |
| FT-005 | [timeout-continuation](timeout-continuation/SPEC.md) | **MVPClosed** | 2026-06-28 | Pilot-prep | [SPEC](timeout-continuation/SPEC.md) §8 · [PLAN](timeout-continuation/PLAN.md) · [`gate_report`](../../workspaces/tc-baseline/gate_report.md) |
| FT-006 | [vwap-stretch-fade](vwap-stretch-fade/SPEC.md) | **MVPClosed** | 2026-06-28 | — | [SPEC](vwap-stretch-fade/SPEC.md) §8 · [`gate_report`](../../workspaces/vsf-baseline/gate_report.md) |
| FT-007 | [momentum-exhaustion-reversal](momentum-exhaustion-reversal/SPEC.md) | **MVPClosed** | 2026-06-28 | — | [SPEC](momentum-exhaustion-reversal/SPEC.md) §8 · [`gate_report`](../../workspaces/mer-baseline/gate_report.md) |
| FT-008 | [short-breakout](short-breakout/SPEC.md) | **MVPClosed** | 2026-06-28 | — | [SPEC §8](short-breakout/SPEC.md) · [`gate_report`](../../workspaces/sb-baseline/gate_report.md) |
| FT-009 | [opening-range-breakout](opening-range-breakout/SPEC.md) | **MVPClosed** | 2026-06-28 | — | [SPEC §8](opening-range-breakout/SPEC.md) · [PLAN](opening-range-breakout/PLAN.md) · [`gate_report`](../../workspaces/orb-baseline/gate_report.md) |
| FT-010 | [vwap-trend-pullback](vwap-trend-pullback/SPEC.md) | **MVPClosed** | 2026-06-28 | — | [SPEC §11](vwap-trend-pullback/SPEC.md) · [PLAN](vwap-trend-pullback/PLAN.md) · [`gate_report`](../../workspaces/vtp-baseline/gate_report.md) |
| FT-011 | [session-confluence-breakout](session-confluence-breakout/SPEC.md) | **MVPClosed** | 2026-06-28 | — | [SPEC §10](session-confluence-breakout/SPEC.md) · [PLAN](session-confluence-breakout/PLAN.md) · [`gate_report`](../../workspaces/scb-baseline/gate_report.md) |
| FT-012 | [regime-vwap-stretch-fade](regime-vwap-stretch-fade/SPEC.md) | **MVPClosed** | 2026-06-28 | — | [SPEC §8](regime-vwap-stretch-fade/SPEC.md) · [`gate_report`](../../workspaces/rvsf-baseline/gate_report.md) |
| FT-013 | [supertrend-flip](supertrend-flip/SPEC.md) | **MVPClosed** | 2026-06-28 | Alpha P0 | [gate_report](../../workspaces/stf-baseline/gate_report.md) · `stf_fingerprint_fail` |
| FT-014 | [morning-vwap-hold-pullback](morning-vwap-hold-pullback/SPEC.md) | **MVPClosed** | 2026-06-28 | Alpha P0 | [`mvhp_fingerprint_fail`](../../workspaces/mvhp-baseline/gate_report.md) · n=7 · W30 med +38 |
| FT-015 | [fvg-retest-pullback](fvg-retest-pullback/SPEC.md) | **MVPClosed** | 2026-06-28 | Alpha P0 | [`frp_fingerprint_fail`](../../workspaces/fvg-baseline/gate_report.md) · n=211 · W30 −0 |
| FT-016 | [gap-drive-continuation](gap-drive-continuation/SPEC.md) | **MVPClosed** | 2026-06-28 | Alpha P0 | [`gdc_fingerprint_pass_g1_fail`](../../workspaces/gdc-baseline/gate_report.md) · W30 +13 · G1 fail |
| FT-017 | [compression-flow-attack](compression-flow-attack/SPEC.md) | **MVPClosed** | 2026-06-28 | Alpha P0 | **`spec_anchor_mismatch`** · n=0 · compress 錨點錯位 · [`gate_report`](../../workspaces/cfa-baseline/gate_report.md) |
| FT-018 | [gap-up-drive-trail](gap-up-drive-trail/SPEC.md) | **Draft** | 2026-06-28 | Alpha P0 | [SPEC](gap-up-drive-trail/SPEC.md) · [PLAN](gap-up-drive-trail/PLAN.md) · P-011 **`draft-proposal`** · exit-led |
| FT-019 | [sweep-fvg-breakout-trail](sweep-fvg-breakout-trail/SPEC.md) | **Draft** | 2026-06-29 | Alpha P0 | [SPEC](sweep-fvg-breakout-trail/SPEC.md) · [PLAN](sweep-fvg-breakout-trail/PLAN.md) · P-012 **`draft-proposal`** · sweep+FVG trail |
| FT-020 | [bear-streak-flip-long](bear-streak-flip-long/SPEC.md) | **Draft** | 2026-06-29 | Alpha P0 | [SPEC](bear-streak-flip-long/SPEC.md) · [PLAN](bear-streak-flip-long/PLAN.md) · P-013 **`draft-proposal`** · 0-design Conditional PASS |

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
7. 新 **策略 thesis**（**FT-012+**）**MUST** 連結 [`HOLDOUT_CONTRACT_v2.md`](ai-backtest-tuning/HOLDOUT_CONTRACT_v2.md) **v2.2.1** 與 [`ALPHA_RESEARCH_PLAYBOOK.md`](ai-backtest-tuning/ALPHA_RESEARCH_PLAYBOOK.md)

**Alpha 提案**：Agent 草稿 → [`workspaces/THESIS_QUEUE.md`](../../workspaces/THESIS_QUEUE.md) → 人類 `human-approved` → 複製 [`THESIS_BRIEF.md`](_template/THESIS_BRIEF.md) 進 SPEC。

**命名**：slug 用 kebab-case、描述能力（例：`audit-event-replay`），不要用 `misc` 或日期。

## 文件紀律（Agent MUST）

- ft **Draft / InProgress** 期間：以 `docs/features/<slug>/SPEC.md` 為設計真相
- ft **Landed** 後：**MUST** 將穩定欄位併入 app SPEC + **MUST** 更新 `CHANGELOG.md`；更新本 board 的 Status
- **MUST NOT** 長期維護與 app SPEC 矛盾的雙真相

模板：[`_template/SPEC.md`](_template/SPEC.md)、[`_template/PLAN.md`](_template/PLAN.md)