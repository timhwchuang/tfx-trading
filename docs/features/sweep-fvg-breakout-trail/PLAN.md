---
id: FT-019
slug: sweep-fvg-breakout-trail
status: MVPClosed
thesis_class: skew
proposal_id: P-012
opened: 2026-06-29
phases: [0]
blockers: [human-approved-P-012, FT-017-0c-serial]
design_review: senior-trader 2026-06-29 — Conditional PASS (P0 sealed)
parent_ft: FT-015
---

# FT-019 — Sweep FVG Breakout Trail（PLAN）

> **Holdout**：v2.2.1 · train 2025 · valid 2026 Q1 · holdout 2026 Q2  
> **class**：**skew** · G3S n≥15 · §3.2 · **fingerprint W900**  
> **封印 MUST**：[`SPEC.md`](SPEC.md) §5.0–§5.1 · **診斷順序**：§5.2  
> **Workspace**：[`sfbt-baseline/`](../../../workspaces/sfbt-baseline/)  
> **Milestone**：**0-design 完成**（2026-06-29 · 資深 TXF Conditional PASS）· 本档下一里程碑 = Phase 0a（CF + tests · **不含** 0c train）

## Phase 0-design — SPEC/PLAN 審閱

- [x] SPEC + PLAN（本档）
- [x] 資深 TXF 審閱 **Conditional PASS** → SPEC §8 · YAML `design_review`（2026-06-29 · P0 已併入 SPEC）
- [x] P0 檢查：long-only · 5m FVG · sweep→reclaim→breakout · fvg_mid trail · W900 · swing/FVG 时间序
- [ ] P1（0b 前）：`exit_gap` · `pct_hit_2R` · slippage {0,1,2}

**開工前提**：P-012 **`human-approved`**（建议 FT-017 0c-1 后 · 与 P-011 串行 Pick）· **0-design PASS** 後才 Phase 0a。

## 給 Agent 的 Phase 0a 開工 prompt（複製用）

> Playbook §7 為**新 FT 寫 SPEC/PLAN** 用；**0-design 完成後**接 Phase 0a → 用本段。

```text
任務：FT-019 / P-012 Phase 0a（CF + tests · 不得跑 train）。

MUST 先確認（未過 → 停）：
1. THESIS_QUEUE P-012 狀態 = human-approved（仍 draft-proposal → 停，等人 Pick）
2. 建議 FT-017 0c-1 已結案（queue 建議 · 非程式硬 gate）

MUST 讀：
- docs/features/sweep-fvg-breakout-trail/SPEC.md §5.0–§5.2 · §5.1 MUST-1
- docs/features/sweep-fvg-breakout-trail/PLAN.md Phase 0a（本档）
- ALPHA_RESEARCH_PLAYBOOK.md §2 · §3.1b · §5.2
- packages/strategies/vwap-momentum/src/strategy_vwap_momentum/structure.py（_detect_fvgs）
- apps/trading-app/src/reporting/fvg_retest_pullback_counterfactual.py（FVG 检测参考 · MUST NOT 复制 zone entry）

MUST 實作：
- simulate_fvg_mid_trail_skew_exit（SPEC §5.0b · initial stop=fvg_mid · risk_unit BE/trail）
- sweep_fvg_breakout_trail_counterfactual.py（sweep/reclaim/FVG/breakout · long-only · funnel · W900）
- ft019_sfbt_counterfactual.py（--fingerprint-only · --grid）
- tests/reporting/test_simulate_fvg_mid_trail_skew_exit.py
- tests/reporting/test_sweep_fvg_breakout_trail_counterfactual.py（PLAN case 表）

MUST NOT：
- 跑 0c train（須 Phase 0b code review PASS）
- FT-015 式 zone 内 tick entry 或 vol_p40 quiet entry
- 固定 1:2 作主 exit
- structure_tf_min=15 作主 TF
- 0c-1 fingerprint 讀 W1800 legacy
- 修改 FT-015 CF 或在其上改 exit 重跑

驗收：
- PLAN trail T1–T8 + CF case 1–12 全綠
- funnel 六階絕對數 · outcome 细分 sfbt_*
- 0a 結束 → 停等 0b review · 不得自跑 train
```

## Phase 0a — Counterfactual（不得跑 train）

- [ ] `reporting/simulate_fvg_mid_trail_skew_exit.py`（**须新函式** · **不得**与 FT-018 共用 ATR 初始 stop 实作 · fvg_mid · risk_unit BE/trail）
- [ ] `reporting/sweep_fvg_breakout_trail_counterfactual.py`（MUST-1–4 · W900 fingerprint · skew_gate）
- [ ] `scripts/ft019_sfbt_counterfactual.py`
- [ ] `tests/reporting/test_simulate_fvg_mid_trail_skew_exit.py`
- [ ] `tests/reporting/test_sweep_fvg_breakout_trail_counterfactual.py`
- [ ] 對照 FRP：entry **不得** bit-identical（breakout ≠ zone touch）

### Trail sim 優先測試（0a · MUST 先於 CF 整合）

| # | Case |
|---|------|
| T1 | 初始 stop = **fvg_mid** · 未 BE · 触 mid → gross = −(entry−mid) |
| T2 | 浮盈 ≥ **1×risk_unit** · BE · 回落触 entry → gross **0** |
| T3 | Trail arm（risk 阈值先触发）· peak 升 · trail dist 0.5×ATR 出场 |
| T4 | Trail arm（ATR 阈值先触发）· 同 tick 与 risk 阈值 · 取 **先触发** |
| T5 | Hard TP **4×risk_unit** 触发 |
| T6 | stop vs TP 同 tick → **stop 优先** |
| T7 | `max_hold_sec=900` 时间出场 |
| T8 | `risk_unit < min_risk_pts（8）` → CF **无 entry** |

### CF 整合測試

| # | Case |
|---|------|
| 1 | 无 sweep → 整日无信号 |
| 2 | sweep 无 reclaim → 无 breakout |
| 3 | reclaim OK · 无 bullish FVG → 无 entry |
| 4 | FVG 在 sweep **前** 形成 → **skip**（MUST-1 BOS 序） |
| 5 | tick close **在 zone 内** 未破 fvg_high → **无 entry**（非 FRP） |
| 6 | breakout OK · risk_unit OK · trail sim 完成 |
| 7 | breakout **≥ 12:30** → 无 entry |
| 8 | fingerprint 读 **W900** |
| 9 | funnel 六階絕對數 |
| 10 | payload 含 `exit_gap` · `pct_hit_2R` |
| 11 | 第二笔 breakout 同日 → 忽略（1 笔/日） |
| 12 | **long-only** · 无 short 信号路径 |

## Phase 0b — Code review（MUST 先於 train）

- [ ] Bugbot / 人類 review PASS
- [ ] MUST-1 sweep/reclaim/FVG 序 · breakout 非 retest
- [ ] MUST-2 fvg_mid trail 状态机 · risk_unit · tie-break
- [ ] MUST-3 W900 fingerprint
- [ ] MUST-4 摩擦 5 · skew_gate · exit_gap 附錄
- [ ] §5.2 fingerprint / grid 路径分离

## Phase 0c — Train 2025（兩段 · 禁止跳步）

### 0c-1 Fingerprint

凍結：`sweep_lb=45` · `sweep_k=0.25` · `reclaim=120` · `swing_lb=3` · `fvg_age=6` · `be_risk=1.0` · `trail_arm_risk=2.0` · `trail_arm_atr=1.5` · `trail_dist=0.5` · `hard_tp_risk=4.0` · `max_hold_sec=900` · `fingerprint_window_sec=900`

```bash
cd apps/trading-app/src
python scripts/ft019_sfbt_counterfactual.py --cache-dir ../../../tick_cache --fingerprint-only
```

**通過線**：n≥**15** · **W900 stop-less gross median > 0**  
**未過** → `sfbt_fingerprint_fail_direction` 或 `sfbt_fingerprint_fail_n` · **不跑 0c-2**

### 0c-2 Grid（僅 fingerprint 過）

```bash
python scripts/ft019_sfbt_counterfactual.py --cache-dir ../../../tick_cache --grid
```

產物：[`workspaces/sfbt-baseline/`](../../../workspaces/sfbt-baseline/) · `gate_report.md` · counterfactual JSON

## Phase 0 完成定義

- [ ] 0-design PASS · 0a tests green · 0b PASS · 0c gate_report 決策表
- [ ] outcome code 寫入 SPEC YAML · THESIS_QUEUE · DOC_MAP · CHANGELOG

## 參考

- 母 FT：[`fvg-retest-pullback/SPEC.md`](../fvg-retest-pullback/SPEC.md) · [`gate_report`](../../../workspaces/fvg-baseline/gate_report.md)
- Trail 状态机参考：[`gap-up-drive-trail/SPEC.md`](../gap-up-drive-trail/SPEC.md) §5.0b
- Playbook §3.1b · §5.2
