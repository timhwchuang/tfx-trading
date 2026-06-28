---
id: FT-018
slug: gap-up-drive-trail
status: Draft
thesis_class: skew
proposal_id: P-011
opened: 2026-06-28
phases: [0]
blockers: [FT-017-0c, human-approved-P-011]
design_review: senior-trader 2026-06-29 — Conditional PASS (P0 sealed)
parent_ft: FT-016
---

# FT-018 — Gap Up Drive Trail（PLAN）

> **Holdout**：v2.2.1 · train 2025 · valid 2026 Q1 · holdout 2026 Q2  
> **class**：**skew** · G3S n≥15 · §3.2 · **fingerprint W900**  
> **封印 MUST**：[`SPEC.md`](SPEC.md) §5.0–§5.1 · **診斷順序**：§5.2  
> **Workspace**：[`gudt-baseline/`](../../../workspaces/gudt-baseline/)  
> **Milestone**：**0-design 完成**（2026-06-29 · 資深 TXF Conditional PASS）· **本檔下一里程碑 = Phase 0a**（CF + tests · **不含** 0c train）

## Phase 0-design — SPEC/PLAN 審閱

- [x] SPEC + PLAN（本檔）
- [x] 資深 TXF 審閱 **Conditional PASS** → SPEC §8 · YAML `design_review`（2026-06-29 · P0 已併入 SPEC）
- [x] P0 檢查：long-only 後置 filter · entry reuse bit-identical · W900 primary · trail 狀態機 · prior_close inline
- [ ] P1（0b 前）：`exit_gap` · `pct_mfe_ge_1atr` · slippage {0,1,2}

**開工前提**：P-011 **`human-approved`**（建議 FT-017 0c-1 結案後 Pick）· **0-design PASS** 後才 Phase 0a。

## 給 Agent 的 Phase 0a 開工 prompt（複製用）

> Playbook §7 為**新 FT 寫 SPEC/PLAN** 用；**0-design 完成後**接 Phase 0a → 用本段。

```text
任務：FT-018 / P-011 Phase 0a（CF + tests · 不得跑 train）。

MUST 先確認（未過 → 停）：
1. THESIS_QUEUE P-011 狀態 = human-approved（仍 draft-proposal → 停，等人 Pick）
2. 建議 FT-017 0c-1 已結案（queue 建議 · 非程式硬 gate）

MUST 讀：
- docs/features/gap-up-drive-trail/SPEC.md §5.0–§5.2 · §5.1b entry reuse
- docs/features/gap-up-drive-trail/PLAN.md Phase 0a（本檔）
- ALPHA_RESEARCH_PLAYBOOK.md §2（0a 不得 train · 0b 先於 0c）
- apps/trading-app/src/reporting/gap_drive_continuation_counterfactual.py（entry P0 模板）
- apps/trading-app/src/scripts/ft016_gdc_counterfactual.py（CLI 模板）

MUST 實作：
- simulate_atr_trail_skew_exit（SPEC §5.0b 每 tick 狀態機 + tie-break）
- gap_up_drive_trail_counterfactual.py（GDC entry builder + long-only 後置 filter）
- ft018_gudt_counterfactual.py（--fingerprint-only · --grid）
- tests/reporting/test_simulate_atr_trail_skew_exit.py
- tests/reporting/test_gap_up_drive_trail_counterfactual.py（PLAN trail + CF case 表）

MUST NOT：
- 跑 0c train（須 Phase 0b code review PASS）
- 修改 gap_drive_continuation_counterfactual.py 內 P0 定義
- 0c-1 fingerprint 讀 W1800/W30 legacy（FT-018 gate = W900 · SPEC §5.0c）
- 每次 CF 前全庫 cache_audit（見 workspaces/CACHE_AUDIT.md）

驗收：
- PLAN trail T1–T8 + CF case 1–10 全綠
- case 10：fp gk1_rt0p4 · GDC long entries = GUDT entries（bit-identical）
- 0a 結束 → 停等 0b review · 不得自跑 train
```

## Phase 0a — Counterfactual（不得跑 train）

- [ ] `reporting/gap_up_drive_trail_counterfactual.py`（entry reuse GDC · **`simulate_atr_trail_skew_exit`** · W900 fingerprint · funnel · post_entry · skew_gate）
- [ ] `reporting/simulate_atr_trail_skew_exit.py` 或 `armed_forward_counterfactual.py` 內新函式
- [ ] `scripts/ft018_gudt_counterfactual.py`（`--fingerprint-only` · `--grid`）
- [ ] `tests/reporting/test_gap_up_drive_trail_counterfactual.py`
- [ ] `tests/reporting/test_simulate_atr_trail_skew_exit.py`
- [ ] 對照 [`gap_drive_continuation_counterfactual.py`](../../../apps/trading-app/src/reporting/gap_drive_continuation_counterfactual.py)：entry P0 比特一致（long-only 子集）

### Trail sim 優先測試（0a · MUST 先於 CF 整合）

| # | Case |
|---|------|
| T1 | 進場後未觸 BE · 先觸 `k_sl×ATR` stop → gross = −k_sl×ATR |
| T2 | 浮盈達 **1×ATR** · stop 抬至 entry · 回撤觸 BE → gross **0** |
| T3 | 浮盈達 **2×ATR** · trail arm · peak 再升 1×ATR · trail dist 0.5×ATR → 出場 gross ≈ peak−0.5×ATR−entry |
| T4 | 浮盈達 **4×ATR** hard TP → gross = **4×ATR**（若封印 hard_tp） |
| T5 | 同 tick stop 與 TP 同觸 → **stop 優先** |
| T6 | `max_hold_sec=900` 時間出場 · 無 BE/trail 觸發 |
| T7 | BE 後 peak 未達 trail arm · 回落觸 BE stop |
| T8 | `min_atr_pts=25` floor 套用於 stop/trail 距離 |

### CF 整合測試

| # | Case |
|---|------|
| 1 | gap-down 日 → **整日 skip**（long-only） |
| 2 | flat gap → skip |
| 3 | gap-up qualify · retrace fail → 無 break |
| 4 | break @ 09:50 · entry OK · trail sim 跑完 |
| 5 | break @ **≥10:30** → break_signal 可計 · **無** entry |
| 6 | funnel 五階絕對數 · `gap_qualify_up` |
| 7 | fingerprint 讀 **W900** · 非 W30 legacy |
| 8 | payload 含 `post_entry_diagnosis_by_param` · `exit_gap` · `pct_mfe_ge_1atr` |
| 9 | 第二筆 break 同日 → 忽略（1 筆/日） |
| 10 | entry builder 與 FT-016 fp 參數 **gk1_rt0p4** 同日 entry 集合一致（long 子集） |

## Phase 0b — Code review（MUST 先於 train）

- [ ] Bugbot / 人類 review PASS
- [ ] MUST-1 entry reuse · long-only · 無 P0 漂移
- [ ] MUST-2 trail sim · BE/trail/TP 順序 · tie-break
- [ ] MUST-3 W900 fingerprint · 與 post_entry 一致
- [ ] MUST-4 摩擦 5 · skew_gate hook · exit_gap 附錄
- [ ] §5.2 fingerprint / grid 路徑分離

## Phase 0c — Train 2025（兩段 · 禁止跳步）

### 0c-1 Fingerprint

凍結：`gap_k=1.0` · `retrace=0.40` · `k_sl=1.0` · `be=1.0` · `trail_arm=2.0` · `trail_dist=0.5` · `hard_tp=4.0` · `max_hold_sec=900` · `fingerprint_window_sec=900`

```bash
cd apps/trading-app/src
python scripts/ft018_gudt_counterfactual.py --cache-dir ../../../tick_cache --fingerprint-only
```

**通過線**：n≥**15** · **W900 stop-less gross median > 0**  
**未過** → `gudt_fingerprint_fail_direction` 或 `gudt_fingerprint_fail_n` · **不跑 0c-2**

### 0c-2 Grid（僅 fingerprint 過）

```bash
python scripts/ft018_gudt_counterfactual.py --cache-dir ../../../tick_cache --grid
```

產物：[`workspaces/gudt-baseline/`](../../../workspaces/gudt-baseline/) · `gate_report.md` · counterfactual JSON

## Phase 0 完成定義

- [ ] 0-design PASS · 0a tests green · 0b PASS · 0c gate_report 決策表
- [ ] outcome code 寫入 SPEC YAML · THESIS_QUEUE · DOC_MAP · CHANGELOG

## 參考

- 母 FT：[`gap-drive-continuation/SPEC.md`](../gap-drive-continuation/SPEC.md) · [`gate_report`](../../../workspaces/gdc-baseline/gate_report.md)
- Playbook §3.1b · §5.2 exit-led
- Corpse：[`CORPSE_ATLAS.md`](../../../workspaces/CORPSE_ATLAS.md) §Fingerprint 審計
