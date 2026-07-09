---
id: FT-005
slug: timeout-continuation
status: MVPClosed
closed: 2026-06-28
closure: thesis_b_phase0_no_go
opened: 2026-06-28
owner: human+agent
target: Pilot-prep
stable_contract: packages/strategies/timeout-continuation/SPEC.md
audit_schema_version: 1
---

# FT-005 — Timeout-Selective Continuation（Thesis B）

> **SPEC** = Thesis B 策略交付契約。FT-004（armed 即時進場）**MVPClosed**；v1 hybrid **凍結**為研究參考；本 ft 為獨立 plugin。

## 1. Summary

**問題**：FT-003/004 顯示 v1「回踩進場」造成逆向選擇（entered 子集負）；timeout 子集在 counterfactual 中具正 gross edge，但 FT-004 全 cohort 即時進場稀釋 edge（No-Go）。

**目標**：新 plugin `strategy-timeout-continuation` — 武裝後**禁止回踩**；`momentum_timeout` 當 tick **順勢進場**（`reason=timeout_continuation`），出場 **ATR-scaled**（沿用 FT-004），驗證 valid 2026-04 G1/G2。

**使用者**：回測 / `workspaces/tc-baseline`；UAT 切換須 G2 + 人類 Go。

## 2. 現況 vs 目標

| 面向 | v1 hybrid | FT-004 Thesis A | **FT-005 Thesis B** |
|------|-----------|-----------------|---------------------|
| 進場 | armed → VWAP 回踩 | armed **同 tick** | armed → **等 timeout** → 進場 |
| 回踩路徑 | 有 | 無 | **無** |
| 出場 | 固定點數 | ATR k | ATR k（同 FT-004） |
| Pilot 候選 | 否 | 否（No-Go） | **否**（Phase 0 No-Go，見 §8） |

## 3. 進場契約（MUST）

1. **武裝**：與 v1 相同（`vol_1s` + `buy_ratio` / `sell_ratio`）；`DECISION_AUDIT momentum_armed`。
2. **禁止回踩**：armed 期間 **不得** 因 `entry_band` + `exhaustion_vol` 進場。
3. **Episode 追蹤**：armed → timeout 期間記錄 `ever_near_vwap`（`|price - vwap| <= entry_band_points`）。
4. **Timeout 進場**：`elapsed > momentum_timeout_sec` 且仍 flat → 若 guards 通過 → `SIGNAL_AUDIT reason=timeout_continuation`；接著 `DECISION_AUDIT momentum_timeout`（與 v1 語意一致）。
5. **可選 guard**（預設關）：
   - `require_never_near_vwap`
   - `min_displacement_atr_k`
   - `max_adverse_atr_k`（FT-004 語意）

## 4. 出場契約（MUST — 繼承 FT-004）

| 參數 | 語意 | 基準初值 |
|------|------|----------|
| `hard_stop_atr_k` | 硬停 | 0.75 |
| `tp_atr_k` | 止盈 | 2.0 |
| `trail_atr_k` + `atr_trailing_enabled=true` | 移動停 | 0.6 |
| `exit_grace_sec` | grace 內僅 hard stop | 10 |

- **無** VWAP stop（`atr_vwap_stop_enabled=false`）。

## 5. Audit / log

| 事件 | 類型 | reason / event_type |
|------|------|---------------------|
| 武裝 | DECISION | `momentum_armed` |
| Timeout 進場 | SIGNAL | `timeout_continuation` |
| Timeout 診斷 | DECISION | `momentum_timeout` |
| 出場 | SIGNAL | `stop_loss`, `take_profit`, `trailing_stop`, `session_force_flatten` |

## 6. Go / No-Go Gates

| Gate | 條件 | 未過 |
|------|------|------|
| **G1** | valid 2026-04 gross expectancy/趟 **> 5** | 不 sweep |
| **G2** | net expectancy/趟 **> 0**（摩擦 5 點/趟） | 僅診斷 |
| **G3** | trade_count **< 100**/月 | 檢討過濾 |
| **G4** | quick_stop_loss_rate **< 25%** | 調 `hard_stop_atr_k` |

**Phase 0 預檢**（counterfactual `timeout_tick` 路徑，無 arm 濾網）：gross mean **> 5** 且 net mean **> 0** → 才開 plugin；否則 **MVPClosed at Phase 0**。

產物：[`workspaces/tc-baseline/gate_report.md`](../../../workspaces/tc-baseline/gate_report.md)。

## 7. Definition of Done

- [x] `ft005_timeout_entry_counterfactual.py` + JSON 產物
- [x] Phase 0 決策（CF 門檻）— **No-Go**
- [x] ~~`strategy-timeout-continuation` plugin~~ — **取消**（Phase 0 未過）
- [x] ~~`workspaces/tc-baseline` baseline~~ — **取消**
- [x] 單元測試全綠；counterfactual 模組
- [x] 本 SPEC + PLAN

## 8. §Decision — 本回合收尾（2026-06-28）

| 欄位 | 值 |
|------|-----|
| 結論 | **Thesis B（timeout 當 tick 進場）No-Go at Phase 0** — 不作 plugin、baseline、sweep、holdout |
| Phase 0 CF（timeout cohort · `timeout_tick`） | gross **+4.10**/趟（G1 未過）、net **-0.90**/趟（G2 未過）、n=83 |
| 診斷 | timeout 子集在 **armed tick** 仍強（+36/趟），但延遲至 timeout 進場 edge 消失 → 「等回踩失敗再追」不可行 |
| Plugin 處置 | **未實作**；UAT/Live 維持 `strategy-vwap-momentum` |
| 保留資產 | `timeout_entry_counterfactual`、[`tc-baseline/reports/`](../../../workspaces/tc-baseline/reports/)、[`gate_report.md`](../../../workspaces/tc-baseline/gate_report.md) |
| 下一 thesis（未開 ft） | 純均值回歸，或結構性早進（非 timeout 尾端） |

產物 SSOT：[`workspaces/tc-baseline/gate_report.md`](../../../workspaces/tc-baseline/gate_report.md)。

## 參考

- PLAN：[`PLAN.md`](PLAN.md)
- FT-004：[`../momentum-continuation/SPEC.md`](../momentum-continuation/SPEC.md) §8
- 診斷：[`workspaces/strategy_diagnosis.md`](../../../workspaces/strategy_diagnosis.md) §6–§7
- v1 凍結：[`packages/strategies/vwap-momentum/SPEC.md`](../../../packages/strategies/vwap-momentum/SPEC.md)
