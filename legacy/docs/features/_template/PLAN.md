---
id: FT-00N
slug: your-feature-slug
status: Draft
opened: YYYY-MM-DD
owner: human+agent
target: UAT
phases: [0, 1]
blockers: []
---

# FT-00N — &lt;Feature Title&gt;（PLAN）

> **PLAN** = 怎麼交付 SPEC。Phase checkbox 隨 PR 更新。

## Scope

- …

## Out of scope

- …

## Dependencies & blockers

| 項目 | 狀態 |
|------|------|
| … | … |

## Phases

### Phase 0 — 開 ft（文件）

- [ ] `docs/features/<slug>/SPEC.md`
- [ ] `docs/features/<slug>/PLAN.md`
- [ ] `docs/features/README.md` board 一列
- [ ] `DOC_MAP.md` §Features
- [ ] `CHANGELOG.md` [Unreleased]

### Phase 1 — …

- [ ] …

## Acceptance（關閉整張 ft）

- [ ] SPEC §7 Definition of Done 全勾
- [ ] `bash scripts/run-all-tests.sh` 全綠（若涉及程式）

## Risks

| 風險 | 緩解 |
|------|------|
| … | … |

## Land checklist（併入 app SPEC 前必勾）

- [ ] 穩定契約已寫入 `apps/trading-app/SPEC.md`（或對應 package SPEC）
- [ ] `CHANGELOG.md` 已記行為/API 變更
- [ ] `docs/features/README.md` Status → **Landed**
- [ ] SPEC/PLAN frontmatter `status: Landed`
- [ ] 本 PLAN 所有 Phase checkbox 已勾

## 參考

- SPEC：[`SPEC.md`](SPEC.md)