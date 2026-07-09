---
id: FT-014
slug: morning-vwap-hold-pullback
status: MVPClosed
thesis_class: mean_robust
proposal_id: P-004
opened: 2026-06-28
closed: 2026-06-28
outcome: mvhp_fingerprint_fail
phases: [0]
blockers: []
design_review: senior-trader 2026-06-28 — Phase 0a GO
---

# FT-014 — Morning VWAP Hold Pullback Long（PLAN）

> **Holdout**：v2.2.1 · train 2025 · valid 2026 Q1 · holdout 2026 Q2  
> **封印 MUST**：[`SPEC.md`](SPEC.md) §5.1 · **診斷順序 / post_entry**：§5.2–§5.3  
> **結案**：[`gate_report.md`](../../../workspaces/mvhp-baseline/gate_report.md) · `mvhp_fingerprint_fail` · train n=7（W30 med +38 但 n<30）

## Phase 0a — Counterfactual（不得跑 train）

- [x] SPEC + PLAN（本檔）
- [x] 資深 TXF 設計審閱 P0/P1 入 SPEC（2026-06-28）
- [x] `reporting/morning_vwap_hold_pullback_counterfactual.py`（hold · first touch · MUST-1/2/3 · funnel · **post_entry hook**）
- [x] `scripts/ft014_mvhp_counterfactual.py`（`--fingerprint-only` · `--grid`）
- [x] `tests/reporting/test_morning_vwap_hold_pullback_counterfactual.py`
- [x] 對照 VTP CF：確認 **無** stretch/recency 路徑混入
- [x] SPEC §5.0b **`atr_barrier_900s`** 與 CF 一致

### 優先測試

| # | Case | 狀態 |
|---|------|------|
| 1 | hold 未滿 `hold_min_bars` → 無 touch | ok |
| 2 | 第二 touch **忽略**（first only） | ok |
| 3 | **09:15** 第一根可計入 hold 邊界 | ok |
| 4 | **10:30** 邊界 bar（`>= 10:30` 不 arm） | ok |
| 5 | **hold + VWAP slope 交互** | ok |
| 6 | **deep wick、close 仍在 buffer 內** | ok |
| 7 | vol shrink 門檻 | ok |
| 8 | funnel 五階段 + **絕對數** | ok |
| 9 | exit = `simulate_atr_barrier_exit` · **`max_hold_sec=900`** | ok |
| 10 | payload 含 `post_entry_diagnosis_by_param` | ok |

## Phase 0b — Code review（MUST 先於 train）

- [x] Agent MUST review PASS（2026-06-28 · 見 gate_report §0b）
- [x] MUST-1 hold / slope / first touch / session VWAP
- [x] MUST-2 摩擦 5 · raw close entry
- [x] MUST-3 1 筆/日 · funnel 絕對數
- [x] **post_entry_diagnosis** hook · 非 gate
- [x] §5.2 fingerprint / grid 路徑分離

## Phase 0c — Train 2025（兩段 · 禁止跳步）

### 0c-1 Fingerprint — **未過 · 2026-06-28**

| 指標 | 值 |
|------|-----|
| n | **7**（G3 min 30 不過） |
| W30 stop-less gross median | **+38.0** |
| barrier gross/趟 | 24.0 |
| funnel | hold_pass=164 → entry=7（vol_shrink 瓶頸） |
| post_entry verdict | `direction_ok_margin_thin` |
| 結案 | **MVPClosed** · 不跑 0c-2 |

```bash
cd apps/trading-app
python src/scripts/ft014_mvhp_counterfactual.py --fingerprint-only
```

**通過線**：n≥30 · **W30 stop-less gross median > 0**  
**未過原因**：n=7 < 30 → `mvhp_fingerprint_fail`（§5.4）

### 0c-2 Grid — **跳過**（0c-1 未過）

## 產物（`workspaces/mvhp-baseline/`）

| 檔案 | 內容 |
|------|------|
| `gate_report.md` | 0b + 0c-1 結案敘事 |
| `reports/counterfactual_mvhp_fingerprint.json` | train 2025 fingerprint |
| `reports/counterfactual_mvhp_valid.json` | valid 2026 Q1 參考（n=0） |
| ~~`counterfactual_mvhp_train.json`~~ | 未產（grid 跳過） |

## Phase 1 — Plugin

- [ ] **取消** — MVPClosed
