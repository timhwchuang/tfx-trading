# Robustness Report — FT-003 Phase 6

**Agent**：  
**商品 / 資料區間**：（例：TMFR1 2024–2025；若跨商品註明「邏輯穩健性 only」）  
**撰寫日期**：YYYY-MM-DD  
**MVP 對照**：`elected_config` v1 params = …  
**Phase 6 holdout**：（封印區間；解封日；僅跑一次）

> **本檔不是 leaderboard。** 用於跨年 WFO 穩健性；不得取代 MVP 2026-05 holdout 結論。

---

## 1. Gate 與 scope

| 項目 | 值 |
|------|-----|
| MVP holdout 結果 | `holdout_pass` / `overfit_suspect` |
| Phase 6 pilot / 完整 | pilot（2–3 fold）/ 完整（≥4 fold） |
| 算力環境 | GCE overnight（日期） |
| fold spec SSOT | `DATA_SPLIT.md` §… |

---

## 2. 各 fold KPI 表

| Fold | Train | Valid | Top params | valid_score | expectancy_net | QSL rate | MDD (net) | trade_count |
|------|-------|-------|------------|-------------|----------------|----------|-----------|-------------|
| 1 | | | | | | | | |
| 2 | | | | | | | | |
| 3 | | | | | | | | |

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
| quick_stop_loss_rate | | | |
| max_drawdown_points | | | |
| trade_count | | | |

---

## 6. 交易員結論（五段式摘要）

1. **假說**：  
2. **證據**：  
3. **風險**：  
4. **對 Pilot**：長歷史 **不能** 跳過 UAT fill / qty=1 對帳  
5. **免責**：回測 net ≠ live 獲利預測（SHARED_ASSUMPTIONS §2）
