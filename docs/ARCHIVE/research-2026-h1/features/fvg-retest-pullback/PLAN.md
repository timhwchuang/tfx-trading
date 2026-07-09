---
id: FT-015
slug: fvg-retest-pullback
status: MVPClosed
thesis_class: skew
proposal_id: P-009
opened: 2026-06-28
closed: 2026-06-28
outcome: frp_fingerprint_fail
---

# FT-015 — FVG Retest Pullback（PLAN）

> **結案**：[`gate_report.md`](../../../workspaces/fvg-baseline/gate_report.md) · `frp_fingerprint_fail` · W30 med **−0.0** · n=211

## Phase 0a — Counterfactual

- [x] SPEC + PLAN
- [x] `reporting/fvg_retest_pullback_counterfactual.py`
- [x] `scripts/ft015_frp_counterfactual.py`
- [x] `tests/reporting/test_fvg_retest_pullback_counterfactual.py`
- [x] FT-002 §4.7 via `compute_structure`

## Phase 0b — Code review

- [x] MUST-1–4 PASS（2026-06-28 · gate_report §0b）
- [x] skew appendix hook

## Phase 0c

### 0c-1 Fingerprint — **未過 · 2026-06-28**

| 指標 | 值 |
|------|-----|
| n | **211**（G3S 過） |
| W30 stop-less med | **−0.0** |
| barrier gross/趟 | 0.33 |
| Long W30 med | +2.0（n=112） |
| Short W30 med | −2.0（n=99） |
| post_entry | `direction_weak` |
| 結案 | **MVPClosed** · grid 跳過 |

### 0c-2 Grid — **跳過**

## Phase 1 — Plugin

- [ ] **取消** — MVPClosed
