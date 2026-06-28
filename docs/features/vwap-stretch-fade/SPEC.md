---
id: FT-006
slug: vwap-stretch-fade
status: InProgress
opened: 2026-06-28
owner: human+agent
target: Pilot-prep
stable_contract: packages/strategies/vwap-stretch-fade/SPEC.md
audit_schema_version: 1
---

# FT-006 — VWAP Stretch Fade（Thesis C）

> **SPEC** = 均值回歸 thesis 交付契約。**完全拋開** 1s spike / `momentum_armed`。v1 hybrid、FT-004/005 **凍結**為研究參考。

## 1. Summary

**問題**：FT-003～005 顯示「爆量 + VWAP 回踩順勢」與「延續追價」均 No-Go；entered 子集虧損來自脈衝後**回吐**時順勢接刀。

**目標**：當價格相對 **5m VWAP** 過度延伸（`|price − vwap| ≥ stretch_k × ATR`）時 **反向**進場（fade），目標回歸 VWAP；出場 **ATR-scaled**（沿用 FT-004）。

**使用者**：回測 / `workspaces/vsf-baseline`；UAT 切換須 G2 + 人類 Go。

## 2. 現況 vs 目標

| 面向 | v1 / FT-004 / FT-005 | **FT-006** |
|------|----------------------|------------|
| 信號 | 1s vol spike + 回踩/延續 | **VWAP z-score 過度延伸** |
| 方向 | 順勢（回踩或追價） | **反向**（fade 回歸 VWAP） |
| spike | 核心或濾網 | **不使用** |
| 出場 | 固定點數或 ATR | ATR k（FT-004 語意） |

## 3. 進場契約（MUST）

1. **z-score**：`z = (price − vwap) / ATR`；VWAP = 5m 滾動（與 `IndicatorState` 同語意）；ATR = SMA(TR, 20) 對齊 engine。
2. **觸發**：flat 且 `|z| ≥ stretch_k`（初探 1.5 / 2.0 / 2.5）。
3. **方向**：`z > 0` → **Short**；`z < 0` → **Long**。
4. **去抖**：進場後直到 `|z| ≤ reset_z`（預設 0.5）才允許下一筆；`cooldown_sec`（預設 60）內不重複 arm。
5. **Audit**：`SIGNAL_AUDIT reason=vwap_stretch_fade`；**無** `momentum_armed`。
6. **濾網**：`trend_filter` / `structure_filter` 預設 **false**（Phase 2 後再評估）。

## 4. 出場契約（MUST — 繼承 FT-004）

| 參數 | 語意 | 基準初值 |
|------|------|----------|
| `hard_stop_atr_k` | 硬停 | 0.75 |
| `tp_atr_k` | 止盈（barrier sim） | 2.0 |
| `trail_atr_k` + `atr_trailing_enabled=true` | 移動停 | 0.6 |
| `exit_grace_sec` | grace 內僅 hard stop | 10 |

## 5. Go / No-Go Gates

| Gate | 條件 | 未過 |
|------|------|------|
| **G1** | valid 2026-04 gross expectancy/趟 **> 5** | 不 sweep |
| **G2** | net **> 0**（摩擦 5 點/趟） | 僅診斷 |
| **G3** | trade_count **< 100**/月 | 檢討過濾 |
| **G4** | QSL **< 25%** | 調 `hard_stop_atr_k` |

**Phase 0 預檢**：存在至少一組（`stretch_k` × 時段）`gross_mean > 5`、`net_mean > 0`、`n ≥ 30` → 才開 plugin；否則 **MVPClosed at Phase 0**。

產物：[`workspaces/vsf-baseline/gate_report.md`](../../../workspaces/vsf-baseline/gate_report.md)。

## 6. Definition of Done

- [x] `ft006_vwap_stretch_fade_counterfactual.py` + JSON
- [x] Phase 0 決策（通過）
- [x] `strategy-vwap-stretch-fade` plugin
- [x] `vsf-baseline` baseline + `gate_report.md`
- [x] 本 SPEC + PLAN

## 8. §Decision — valid G1–G4 通過（2026-06-28）

| 欄位 | 值 |
|------|-----|
| 結論 | **Thesis C valid 通過、holdout 未過** — overfit suspect；**勿**切 UAT、**勿** valid sweep |
| Plugin baseline（valid 月） | 82 趟；gross **+5.43**/趟、net **+0.43**/趟；QSL **6.1%** |
| Holdout（2026-05） | 123 趟；gross **+4.26**/趟、net **−0.74**/趟；G1/G2/G3 未過 |
| UAT/Live | **維持** `strategy-vwap-momentum` |
| 下一輪 | 新 thesis 或診斷 5 月 regime；**不**在 valid 上 tune |

產物 SSOT：[`workspaces/vsf-baseline/gate_report.md`](../../../workspaces/vsf-baseline/gate_report.md)。

## 參考

- PLAN：[`PLAN.md`](PLAN.md)
- 診斷：[`strategy_diagnosis.md`](../../../workspaces/strategy_diagnosis.md) §6–§7
- FT-004 出場：[`momentum-continuation/SPEC.md`](../momentum-continuation/SPEC.md) §4
