---
id: FT-007
slug: momentum-exhaustion-reversal
status: MVPClosed
opened: 2026-06-28
owner: human+agent
target: Pilot-prep
stable_contract: packages/strategies/momentum-exhaustion-reversal/SPEC.md
audit_schema_version: 1
---

# FT-007 — Momentum Exhaustion / Absorption Reversal（Thesis D）

> **SPEC** = 1m 脈衝衰竭 + tick 吸收反轉 thesis。與 v1（VWAP 回踩順勢）、FT-004/005（armed/timeout 延續）、FT-006（靜態 VWAP fade）**分離**。

## 1. Summary

**問題**：v1 entered 子集在脈衝**回吐**相位進場虧損；timeout 子集顯示脈衝延續真，但 FT-004/005 追價 No-Go；FT-006 純 VWAP fade holdout 未過。

**目標**：觀察 **1m 連續強勢 K + 大量** → **衰竭（climax 壓縮）** → **tick 吸收確認** → **逆勢短線搶彈**；出場 **短 TP / 緊 SL / 時間停**（scalp）。

**使用者**：Phase 0 pilot → plugin（若過關）→ baseline **01–04** 合計 gate + **05 holdout**。

## 2. 現況 vs 目標

| 面向 | v1 / FT-004～006 | **FT-007** |
|------|------------------|------------|
| Setup | 1s spike 或 VWAP z | **1m 脈衝序列** |
| 進場相位 | 回踩 / 即時 / 延伸 fade | **脈衝末端衰竭 + 吸收** |
| 持倉 | 分鐘～十分鐘 | **30～120s scalp** |
| 出場 | 固定點數或 ATR trail | **短固定點數 TP/SL** |

## 3. 進場契約（MUST）

### 3.1 Impulse leg（1m kbars）

1. 連續 `impulse_bars`（初探 3～4）根同向 1m K（全陽或全陰）。
2. Σ body ≥ `impulse_body_atr_k × ATR(20)`（初探 1.0）。
3. 每根 vol ≥ 當日 1m vol 的 `impulse_vol_pct`（初探 p70）。

### 3.2 Exhaustion（衰竭）

最後一根脈衝 K 滿足其一：

- **climax_compress**：vol ≥ p80 且 range < 0.55 × 前段平均 range  
- **climax_body_shrink**：vol ≥ p80 且 body < 0.5 × 前段平均 body  

### 3.3 Absorption（tick，bar 收盤後 `absorb_window_sec`）

- 逆脈衝方向成交量 `against_vol ≥ absorb_min_vol`（初探 80）  
- 窗口內 `|Δprice| ≤ absorb_max_move_atr_k × ATR`（初探 0.25）  

### 3.4 Entry

- 方向：**fade 脈衝**（上脈衝 → Short）  
- `cooldown_sec`（初探 180）內不重複  
- Audit：`reason=impulse_absorption_fade`（plugin 階段）

## 4. 出場契約（Phase 0 scalp sim）

| 參數 | 初探 |
|------|------|
| `tp_points` | 12 |
| `sl_points` | 10 |
| `max_hold_sec` | 120 |

## 5. Go / No-Go Gates

### Phase 0（pilot 5 日）

存在至少一組（`impulse_bars` × 時段）`gross_mean > 5`、`net_mean > 0`、`n ≥ 20` → 才開 plugin。

### Phase 2（01–04 合計）

| Gate | 條件 |
|------|------|
| **G1** | 01–04 合計 gross/趟 **> 5** |
| **G2** | net/趟 **> 0**（摩擦 5 點） |
| **G3** | trade_count **< 400**（四個月合計；等效 <100/月） |
| **G4** | QSL **< 25%** |
| **G5** | 任一月 net **≥ −2/趟**（防單月崩） |

**Holdout**：2026-05 封印至 Phase 2 通過後解封一次。

產物：[`workspaces/mer-baseline/gate_report.md`](../../../workspaces/mer-baseline/gate_report.md)。

## 6. Definition of Done

- [x] `ft007_impulse_absorption_counterfactual.py` + pilot JSON
- [x] Phase 0 決策（**未過** — pilot n=2，全 SL）
- [ ] ~~plugin~~ — **取消**（Phase 0 No-Go）
- [ ] ~~baseline 01–04~~ — **取消**
- [x] 本 SPEC + PLAN

## 8. §Decision — Phase 0 No-Go（2026-06-28）

| 欄位 | 值 |
|------|-----|
| 結論 | **放棄 — Thesis D MVPClosed**（`thesis_d_abandoned`） |
| v1 pilot | 2 事件，gross −10/趟 |
| **v2 pilot** | **108** 筆；buy_setups **164** / flips **153**；合計 gross **+1.25**、net **−3.75** |
| v2 亮點 | buy→Short **close_1h** n=14 gross **+5.5** net **+0.5**（n<20） |
| **v3 sweep** | 見 [`counterfactual_flow_flip_v3_sweep.json`](../../../workspaces/mer-baseline/reports/counterfactual_flow_flip_v3_sweep.json) |
| v3 最佳 | **v3_all**（三項合併）n=15 gross **+4.93** net **−0.07**；buy close_1h n=8 gross **+5.0** net **0** |
| Plugin | **未實作**；**不**跑 01–04、不開 plugin |
| 人類 | **放棄**（2026-06-28） |

產物 SSOT：[`workspaces/mer-baseline/gate_report.md`](../../../workspaces/mer-baseline/gate_report.md)。

## 參考

- PLAN：[`PLAN.md`](PLAN.md)
- 診斷：[`strategy_diagnosis.md`](../../../workspaces/strategy_diagnosis.md) §6–§7
- 切分：[`DATA_SPLIT.md`](../../../workspaces/DATA_SPLIT.md)
