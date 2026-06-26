# Robustness Report — FT-003 Phase 6

**Agent**：  
**商品 / 資料區間**：（例：TMFR1 2024–2025；若跨商品註明「邏輯穩健性 only」）  
**撰寫日期**：YYYY-MM-DD  
**MVP 對照**：`elected_config` v1 params = …  
**Phase 6 holdout**：（封印區間；解封日；僅跑一次）  
**摩擦 / 滑價**：`friction.enabled: true`（5 點/趟 SSOT）；`ioc_slippage_points` = …

> **本檔不是 leaderboard。** 用於跨年 **多段滾動** WFO 穩健性；不得取代 MVP 2026-05 holdout 結論。  
> Phase 6 通過後仍須 **Phase 6.5 Shadow/Paper**（見 PLAN Phase 6.5）。

---

## 1. Gate 與 scope

| 項目 | 值 |
|------|-----|
| MVP holdout 結果 | `holdout_pass` / `overfit_suspect` |
| Phase 6 pilot / 完整 | pilot（2–3 fold）/ 完整（≥4 fold；可含月滾） |
| WFO 架構 | 季滾 / **月滾**（spec 見 `DATA_SPLIT.md`） |
| 算力環境 | GCE overnight（日期） |
| fold spec SSOT | `DATA_SPLIT.md` §… |

### 1.1 Walk-forward Gate 門檻（人類簽核 — MUST）

| 門檻 | 簽核值 | 跨 fold 結果 | Pass? |
|------|--------|--------------|-------|
| `sharpe_net` > X | | | |
| `max_drawdown_points` (net) < Y | | | |
| `trade_count`/月 穩定（CV < …） | | | |
| 中位 `expectancy_net` ≥ 0（淨摩擦後） | | | |
| `quick_stop_loss_rate` ≤ 上限 | | | |

**整體**：`robustness_pass` / `diagnostic_only` / `fail`（任一 fold FAIL → 不得 `robustness_pass`）

---

## 2. 各 fold KPI 表

| Fold | Train | Valid | Top params | valid_score | expectancy_net | sharpe_net | QSL rate | MDD (net) | trade_count |
|------|-------|-------|------------|-------------|----------------|------------|----------|-----------|-------------|
| 1 | | | | | | | | | |
| 2 | | | | | | | | | |
| 3 | | | | | | | | | |

**跨 fold 排名**：（平均/中位排名；MVP 冠軍是否 ≥3/4 fold Top-3）

---

## 3. Train vs Valid divergence

| Fold | 現象 | Overfitting 風險（低/中/高） |
|------|------|------------------------------|
| 1 | | |

---

## 4. v1 / v2 治理決策（MUST）

- [ ] MVP 冠軍在 ≥3/4 fold Top-3 → **維持 v1**
- [ ] 跨 fold 冠軍 ≠ MVP 冠軍 → **v2 候選**；已跑 Phase 6 holdout：是 / 否 / 待跑
- [ ] 禁止：用 fold 結果直接取代 MVP holdout

**建議**：（維持 v1 / v2 候選 + holdout / 僅診斷、不換參）

---

## 5. Phase 6 holdout（若 v2 候選）

| 指標 | Valid（末 fold） | Phase 6 Holdout | 備註 |
|------|------------------|-----------------|------|
| valid_score | | | |
| expectancy_net | | | |
| sharpe_net | | | |
| quick_stop_loss_rate | | | |
| max_drawdown_points | | | |
| trade_count | | | |

---

## 6. 交易員結論（五段式摘要）

1. **假說**：  
2. **證據**：  
3. **風險**：  
4. **對 Pilot**：長歷史 **不能** 跳過 Phase 6.5 + UAT fill / qty=1 對帳  
5. **免責**：回測 net ≠ live 獲利預測（SHARED_ASSUMPTIONS §2）

---

## 7. 參數擾動（±10–20%）

**固定 params**：（不得用本節結果再 tune）

| 參數 | 基準 | 擾動 | valid_score | expectancy_net | 衰退可接受? |
|------|------|------|-------------|----------------|-------------|
| | | −10% | | | |
| | | +10% | | | |

**結論**：（尖峰單點 / 平坦高原 / 過敏）

---

## 8. 市況子樣本

| 子樣本 | 定義（ATR/趨勢/…） | 日數 | expectancy_net | trade_count | 備註 |
|--------|-------------------|------|----------------|-------------|------|
| 高波動 | | | | | |
| 低波動 | | | | | |
| 趨勢 | | | | | |
| 震盪 | | | | | |

**結論**：（是否單一市況獨撐）

---

## 9. 壓力情境

| 情境 | 資料 / 合成方式 | MDD (net) | QSL rate | 備註 |
|------|-----------------|-----------|----------|------|
| Flash / 大跳空 | | | | |
| 連續停損週 | | | | |
| 低量 / 流動性枯竭 proxy | | | | |

**結論**：（爆倉盲點有 / 無）

---

## 10. 與其他策略相關性

| 對照策略 | 期間 | 日收益 ρ | 同向暴倉風險 | 備註 |
|----------|------|----------|--------------|------|
| （已上線 / paper / 其他 agent） | | | | |

**結論**：（分散足夠 / 需人類說明）

---

## 11. Phase 6.5 — Shadow / Paper（Post-Phase 6）

| 項目 | 值 |
|------|-----|
| 期間 | YYYY-MM-DD ～ （≥2–4 週） |
| 環境 | 模擬 API；`max_position_qty: 1` |
| Fill 對照工具 | `compare_fill_audits` / … |

| 指標 | Backtest（同期） | Paper/Shadow | 偏差 |
|------|------------------|--------------|------|
| 平均滑價 (pts) | | | |
| Miss / 超時率 | | | |
| 淨期望 (pts/trade) | | | |

**Phase 6.5 Gate**：Pass / Fail — （偏差在簽核範圍內？）

---

## 12. 運維與風控演練

- [ ] Kill switch / HALT / `block_new_entry` 演練（日期、log 引用）
- [ ] Emergency flatten / 市價收斂平倉演練
- [ ] 日報 / 週報自動化（PnL、MDD、trade freq、CRITICAL）
- [ ] 券商 reconciliation（`broker_reconciliation` 或同等）

**備註**：
