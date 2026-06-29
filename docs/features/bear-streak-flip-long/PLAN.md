---
id: FT-020
slug: bear-streak-flip-long
status: Draft
thesis_class: mean_robust
proposal_id: P-013
opened: 2026-06-29
phases: [0]
blockers: [human-approved-P-013]
design_review: senior-trader 2026-06-29 — Conditional PASS (P0 sealed)
parent_ft: null
---

# FT-020 — Bear Streak Flip Long（PLAN）

> **Holdout**：v2.2.1 · train 2025 · valid 2026 Q1 · holdout 2026 Q2  
> **class**：**mean_robust** · G3 n≥30 · §3.1 · **fingerprint W900**  
> **封印 MUST**：[`SPEC.md`](SPEC.md) §5.0–§5.2 · **診斷順序**：§5.2  
> **Workspace**：[`bsfl-baseline/`](../../../workspaces/bsfl-baseline/)  
> **Milestone**：**0-design Conditional PASS**（2026-06-29 · P0 封印）· **下一里程碑 = P-013 human-approved → Phase 0a**

## Phase 0-design — SPEC/PLAN 審閱

- [x] SPEC + PLAN（本檔）
- [x] §E.4 Preflight 填表 → **PASS**（2026-06-29 · stall_price 列 · Senior 簽數字）
- [x] 更新 [`THESIS_QUEUE.md`](../../../workspaces/THESIS_QUEUE.md) P-013 · [`features/README.md`](../README.md) · [`DOC_MAP.md`](../../DOC_MAP.md)
- [x] 資深 TXF 0-design **Conditional PASS** → SPEC §8 · YAML `design_review`（2026-06-29 · P0 已併入）
- [x] P0 檢查：streak 無 repaint · reversal 收盤後 tick confirm · stall core gate · structure stop floor · W900 primary

**開工前提**：P-013 **`human-approved`**（**不**與 P-011 並行 Pick · 建議 P-011 0c-1 後）· **0-design P0 已 PASS** → 可 copy Phase 0a prompt。

## 給 Agent 的 Phase 0a 開工 prompt（複製用）

> Playbook §7 為**新 FT 寫 SPEC/PLAN** 用；**0-design 完成後**接 Phase 0a → 用本段。

```text
任務：FT-020 / P-013 Phase 0a（CF + tests · 不得跑 train）。

MUST 先確認（未過 → 停）：
1. THESIS_QUEUE P-013 狀態 = human-approved（仍 draft-proposal → 停，等人 Pick）
2. SPEC YAML design_review = Conditional PASS (P0 sealed)
3. 建議 P-011 0c-1 已結案（queue 建議 · 非程式硬 gate）

MUST 讀：
- docs/features/bear-streak-flip-long/SPEC.md §5.0–§5.2 · §5.1 MUST-1–5
- docs/features/bear-streak-flip-long/PLAN.md Phase 0a（本檔）
- ALPHA_RESEARCH_PLAYBOOK.md §2（0a 不得 train · 0b 先於 0c）
- apps/trading-app/src/reporting/flow_flip_counterfactual.py（RollingFlowWindow）
- apps/trading-app/src/reporting/supertrend_flip_counterfactual.py（1m session · kbar 模板）
- apps/trading-app/src/reporting/armed_forward_counterfactual.py（barrier sim 模板）

MUST 實作：
- simulate_structure_r_barrier_exit（SPEC §5.0b · structure stop + R-multiple TP）
- bear_streak_flip_long_counterfactual.py（streak · reversal · tick flip · funnel · post_entry）
- ft020_bsfl_counterfactual.py（--fingerprint-only · --grid）
- tests/reporting/test_simulate_structure_r_barrier_exit.py（R1–R6）
- tests/reporting/test_bear_streak_flip_long_counterfactual.py（case 1–15）

MUST NOT：
- 跑 0c train（須 Phase 0b code review PASS）
- intra-bar reversal 進場 · reversal bar 內 tick 預判
- 0c-1 fingerprint 讀 W1800 作 primary gate
- 每次 CF 前全庫 cache_audit（見 workspaces/CACHE_AUDIT.md）

驗收：
- PLAN R1–R6 + CF case 1–15 全綠
- funnel 六階：session → streak_ok → reversal_bar → stall_pass → flip_confirm → entry
- 0a 結束 → 停等 0b review · 不得自跑 train
```

## Phase 0a — Counterfactual（不得跑 train）

- [ ] `reporting/simulate_structure_r_barrier_exit.py`
- [ ] `reporting/bear_streak_flip_long_counterfactual.py`（streak · flip confirm · **`simulate_structure_r_barrier_exit`** · W900 · funnel · post_entry）
- [ ] `scripts/ft020_bsfl_counterfactual.py`（`--fingerprint-only` · `--grid`）
- [ ] `tests/reporting/test_simulate_structure_r_barrier_exit.py`
- [ ] `tests/reporting/test_bear_streak_flip_long_counterfactual.py`

**Reuse**：`RollingFlowWindow` from `flow_flip_counterfactual.py`；kbar session from `supertrend_flip_counterfactual.py` / `orb_counterfactual.py`。

### Structure R-barrier sim 測試（0a · MUST 先於 CF 整合）

| # | Case |
|---|------|
| R1 | 進場後觸 `effective_stop` → gross = −risk_unit |
| R2 | 觸 TP @ `entry + 2×risk_unit` → gross = +2×risk_unit |
| R3 | 同 tick stop 與 TP → **stop 優先** |
| R4 | `max_hold_sec=900` 時間出場 |
| R5 | stop floor：`min_stop_atr_k × ATR` 寬於 structure low |
| R6 | `risk_unit = min_stop_pts` floor 生效 |

### CF 整合測試

| # | Case |
|---|------|
| 1 | 4 bear + bull + flip confirm → entry OK |
| 2 | 4 bear + doji → streak 中斷 · 無 entry |
| 3 | 4 bear + bull · buy_ratio 不足 → 無 entry |
| 4 | stop = last bear low（structure · 無 floor 加寬） |
| 5 | stop floor：`min_stop_atr_k × ATR` 生效 |
| 6 | TP @ 2R 觸發 · gross 正確 |
| 7 | fingerprint 讀 **W900** · 非 W1800 primary |
| 8 | funnel：session → streak_ok → reversal_bar → **stall_pass** → flip_confirm → entry |
| 9 | `max_trades_per_day=3` 封頂 |
| 10 | confirm tick @ **≥12:00** → skip |
| 11 | payload 含 `post_entry_diagnosis_by_param` · `exit_gap` |
| 12 | `cooldown_bars=5` 防重複 setup |
| 13 | stall 超過 `stall_atr_k×ATR` → 無 entry（MUST-2 core · P1） |
| 14 | `flip_confirm_timeout_sec=120` 逾時 → 放棄 setup（P1） |
| 15 | reversal arm @ **≥11:45** → 不 arm（MUST-1 邊界 · P1） |

## Phase 0b — Code review（MUST 先於 train）

- [ ] Bugbot / 人類 review PASS
- [ ] MUST-1 streak/reversal · 無 partial-bar · 無 lookahead
- [ ] MUST-2 tick confirm **僅** reversal 收盤後
- [ ] MUST-3 structure stop + floor · R-multiple TP
- [ ] MUST-4 W900 fingerprint · friction 5 · funnel · post_entry
- [ ] §5.2 fingerprint / grid 路徑分離

## Phase 0c — Train 2025（兩段 · 禁止跳步）

### 0c-1 Fingerprint

凍結：`min_streak=4` · `flip_window_sec=45` · `flip_buy_ratio_min=0.55` · `flip_vol_min=25` · `stall_atr_k=0.35` · `tp_r=2.0` · `min_stop_atr_k=0.75` · `max_hold_sec=900` · `fingerprint_window_sec=900`

```bash
cd apps/trading-app/src
python scripts/ft020_bsfl_counterfactual.py --cache-dir ../../../tick_cache --fingerprint-only
```

**通過線**：n≥**30** · **W900 stop-less gross median > 0**  
**未過** → `bsfl_fingerprint_fail_direction` 或 `bsfl_fingerprint_fail_n` · **不跑 0c-2**

### 0c-2 Grid（僅 fingerprint 過）

```bash
python scripts/ft020_bsfl_counterfactual.py --cache-dir ../../../tick_cache --grid
```

Grid 軸：`min_streak × flip_buy_ratio_min × tp_r`（**禁止**同時改 exit 族）

產物：[`workspaces/bsfl-baseline/`](../../../workspaces/bsfl-baseline/) · `gate_report.md` · counterfactual JSON

## Phase 0 完成定義

- [ ] 0-design PASS · 0a tests green · 0b PASS · 0c gate_report 決策表
- [ ] outcome code 寫入 SPEC YAML · THESIS_QUEUE · DOC_MAP · CHANGELOG

## 參考

- 近親 FT-007：[`momentum-exhaustion-reversal/SPEC.md`](../momentum-exhaustion-reversal/SPEC.md) · [`gate_report`](../../../workspaces/mer-baseline/gate_report.md)
- Playbook §3.1b · §4 負面圖書館（fade 族 · MER）
- Corpse：[`CORPSE_ATLAS.md`](../../../workspaces/CORPSE_ATLAS.md)
