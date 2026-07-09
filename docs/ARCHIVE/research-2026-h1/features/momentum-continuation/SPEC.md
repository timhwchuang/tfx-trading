---
id: FT-004
slug: momentum-continuation
status: MVPClosed
closed: 2026-06-28
closure: thesis_a_no_go
opened: 2026-06-27
owner: human+agent
target: Pilot-prep
stable_contract: packages/strategies/momentum-continuation/SPEC.md
audit_schema_version: 1
---

# FT-004 — Momentum Continuation（Armed Forward Entry）

> **SPEC** = Thesis A 策略交付契約。舊 `strategy-vwap-momentum`（回踩 hybrid）**凍結**為研究參考；本 ft 為獨立 plugin。

## 1. Summary

**問題**：FT-003 Phase 3.6 顯示 v1 在 armed 後等 VWAP 回踩進場，造成**逆向選擇**（成交子集逆勢、順勢子集 timeout）；valid 毛期望 ≈ 0，淨虧由摩擦主導。

**目標**：新 plugin `strategy-momentum-continuation` — **武裝當 tick 順勢進場**（*Armed Forward Entry*），出場 **預設全 ATR-scaled**（hard stop / trail / TP），驗證 valid 2026-04 是否具正 gross edge（G1）。

**使用者**：回測 / sweep（`workspaces/mc-baseline`）；UAT 切換須 G2 + 人類 Go。

## 2. 現況 vs 目標

| 面向 | v1 (`strategy-vwap-momentum`) | FT-004 |
|------|------------------------------|--------|
| 進場 | armed → 等 VWAP + vol 枯竭 | armed **同 tick** entry（`reason=continuation`） |
| 出場 | 固定點數為主（HS6/TP20） | **ATR k** 為主（`hard_stop_atr_k` / `tp_atr_k` / `trail_atr_k`） |
| VWAP stop | 可開 | **預設關** |
| Pilot 候選 | 否（`grid_no_viable_solution`） | **否**（Thesis A No-Go，見 §8） |

## 3. 進場契約（MUST）

1. **武裝條件**（與 v1 相同語意）：`vol_1s ≥ threshold` 且 `buy_ratio` / `sell_ratio` 通過。
2. **同 tick 進場**：條件滿足即 `SIGNAL_AUDIT reason=continuation`；**禁止** pullback / `exhaustion_vol` / `entry_band_points` 進場路徑。
3. **Guards**：`min_atr_threshold`、session、`RiskGate`（pending、cooldown、`block_new_entry` 等）。
4. **Audit**：`DECISION_AUDIT event_type=momentum_armed` 與 entry 同 episode；`episode_id` 格式同 v1。
5. **濾網**：`trend_filter_enabled` / `structure_filter_enabled` **預設 false**（Phase 2 後再評估）。

## 4. 出場契約（MUST — ATR 預設）

| 參數 | 語意 | 基準初值（4 月 ATR p50≈25.7） |
|------|------|-------------------------------|
| `hard_stop_atr_k` | 硬停距離 = max(floor, k×ATR) | 0.75（≈19 點） |
| `tp_atr_k` | 止盈距離 | 2.0（≈51 點） |
| `trail_atr_k` + `atr_trailing_enabled=true` | 移動停 | 0.6（≈15 點） |
| `exit_grace_sec` | grace 內僅 hard ATR stop | 10（短於 v1） |

- grace 內 **僅** hard ATR stop；grace 外 hard + trail + TP。
- **無** VWAP stop（`atr_vwap_stop_enabled=false`）。

## 5. Audit / log

| 事件 | 類型 | reason / event_type |
|------|------|---------------------|
| 武裝+進場 | SIGNAL | `continuation` |
| 武裝診斷 | DECISION | `momentum_armed` |
| 出場 | SIGNAL | `stop_loss`, `take_profit`, `trailing_stop`, `session_force_flatten` |

## 6. Go / No-Go Gates

| Gate | 條件 | 未過 |
|------|------|------|
| **G1** | valid 2026-04 gross expectancy/趟 **> 5** | 不 sweep |
| **G2** | net expectancy/趟 **> 0**（摩擦 5 點/趟） | 僅診斷 |
| **G3** | trade_count **< 100**/月（valid） | 檢討過濾 |
| **G4** | quick_stop_loss_rate **< 25%** | 調 `hard_stop_atr_k` 單軸 |

產物：[`workspaces/mc-baseline/gate_report.md`](../../../workspaces/mc-baseline/gate_report.md)。

## 7. Definition of Done

- [x] `strategy-momentum-continuation` plugin + entry point `momentum_continuation`
- [x] `ft004_armed_forward_counterfactual.py` + JSON 產物
- [x] `workspaces/mc-baseline` baseline 回測 + `gate_report.md`
- [x] 單元測試全綠；`setup-dev.sh` / `run-all-tests.sh` 含新 package
- [x] 本 SPEC + PLAN；feature board FT-004

## 8. §Decision — 本回合收尾（2026-06-28）

| 欄位 | 值 |
|------|-----|
| 結論 | **Thesis A（armed 當 tick 全 cohort 即時進場）No-Go** — 不作 Pilot、sweep、holdout |
| 最終 baseline（r1b+r2） | gross **+1.89**/趟、net **-3.11**/趟、187 趟；G1/G2/G3 未過；G4 過 |
| 診斷 | Counterfactual 分層：timeout 子集強（+27～+36）、entered 子集負（-17～-19）；全進場稀釋 edge |
| 調參 | §a vol/buy 略改善；§b `max_adverse_atr_k` 無增量 |
| Plugin 處置 | **凍結研究用**（同 v1）；**UAT/Live 不切換** `momentum_continuation` |
| 保留資產 | counterfactual / probe 腳本、`mc-baseline` 產物、ATR 出場實驗、engine 接線修復 |
| 下一 thesis（未開 ft） | **timeout-selective entry**（只吃 v1 未回踩子集）— 需新 SPEC，非本 plugin 微調 |

產物 SSOT：[`workspaces/mc-baseline/gate_report.md`](../../../workspaces/mc-baseline/gate_report.md)。

## 參考

- PLAN：[`PLAN.md`](PLAN.md)
- FT-003 診斷：[`workspaces/strategy_diagnosis.md`](../../../workspaces/strategy_diagnosis.md) §6
- v1 凍結：[`packages/strategies/vwap-momentum/SPEC.md`](../../../packages/strategies/vwap-momentum/SPEC.md)
