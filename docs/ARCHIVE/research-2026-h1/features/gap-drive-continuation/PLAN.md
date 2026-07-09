---
id: FT-016
slug: gap-drive-continuation
status: MVPClosed
thesis_class: skew
proposal_id: P-005
opened: 2026-06-28
closed: 2026-06-28
outcome: gdc_fingerprint_pass_g1_fail
phases: [0]
design_review: senior-trader 2026-06-28 — PASS (P0 sealed)
---

# FT-016 — Gap Drive Continuation（PLAN）

> **結案**：[`gate_report.md`](../../../workspaces/gdc-baseline/gate_report.md) · `gdc_fingerprint_pass_g1_fail` · fingerprint W30 med **+13** · n=79 · grid 36/36 G1 fail · valid net **−9.28**

## Phase 0-design — SPEC/PLAN 審閱

- [x] SPEC + PLAN 草稿
- [x] 資深 TXF 審閱（2026-06-28 · Conditional PASS → P0 Revise → **PASS**）
- [x] SPEC §8 + YAML `design_review:` 更新
- [x] P0：`prior_close` · `open_0845` · retrace 一次性 · flat gap · skew valid 硬擋
- [x] P1：slippage {0,1,2} 診斷 · gate_report friction@7 / G-SK5

## Phase 0a — Counterfactual

- [x] `reporting/gap_drive_continuation_counterfactual.py`
- [x] `scripts/ft016_gdc_counterfactual.py`（`--fingerprint-only` · `--grid`）
- [x] `tests/reporting/test_gap_drive_continuation_counterfactual.py`
- [x] SPEC §5.1 MUST / §5.1a 與程式逐條對照（`open_0845` 08:46 edge tolerance 對齊 kbar cache）

## Phase 0b — Code review

- [x] MUST-1–4 PASS（2026-06-28 · gate_report §0b）
- [x] skew appendix hook

## Phase 0c

### 0c-1 Fingerprint — **通過 · 2026-06-28**

| 指標 | 值 |
|------|-----|
| n | **79**（G3S 過） |
| W30 stop-less med | **+13.0** |
| barrier gross/趟 | 3.29 · net/趟 −1.71 |
| funnel | 240 → gap_qualify=212 → retrace_ok=134 → break=95 → entry=79 |
| post_entry | `exit_kills_edge` — W30 順向但 barrier med −1 |
| Long W30 med | +21（n=53）· Short +6.5（n=26） |
| skew | payoff 1.415 · net@friction7 −3.71 |

### 0c-2 Grid — **全敗 · 2026-06-28**

36 combos · **best_passing=None** · 最高 gross/趟 4.3（仍 < G1 gross>5 或 net≤0）  
**結案**：**MVPClosed** · `gdc_fingerprint_pass_g1_fail` · valid Q1 net **−9.28** · holdout 硬擋

## 產物（`workspaces/gdc-baseline/`）

| 檔案 | 內容 |
|------|------|
| `gate_report.md` | 0b · fingerprint · grid · valid · §Decision |
| `reports/counterfactual_gdc_fingerprint.json` | train fingerprint |
| `reports/counterfactual_gdc_train.json` | train grid |
| `reports/counterfactual_gdc_valid.json` | valid Q1 參考 |

## Phase 1 — Plugin

- [ ] **取消** — MVPClosed
