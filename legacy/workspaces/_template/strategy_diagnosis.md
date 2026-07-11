# Strategy Diagnosis — FT-003 Phase 3.6

**撰寫日期**：YYYY-MM-DD  
**Gate**：四位 agent sweep 完成 — ☐  
**資料 SSOT**：[`VOLATILITY_BASELINE.md`](../VOLATILITY_BASELINE.md) · Methods：[`ENTRY_FUNNEL_METRICS.md`](../docs/features/ai-backtest-tuning/ENTRY_FUNNEL_METRICS.md)

> 本檔合成四 agent sweep + **四平面**診斷（尺度 §A/B、**進場 §C**、出場 §D）；**不是** leaderboard、**不是** `elected_config`。  
> 契約：[`SPEC.md`](../docs/features/ai-backtest-tuning/SPEC.md) §4.6 · [`PLAN.md`](../docs/features/ai-backtest-tuning/PLAN.md) Phase 3.6

---

## 1. 四平面 sweep 摘要

| Agent | 冠軍 valid_score | 淨期望 | QSL | 結論（一句） |
|-------|------------------|--------|-----|--------------|
| agent-conservative | | | | |
| agent-execution | | | | |
| agent-risk-exit | | | | |
| agent-regime | | | | |

**全平面是否淨負**：☐ 是 ☐ 否

---

## 2. 摩擦 vs gross edge

（毛點是否接近 0、5 點/趟摩擦是否主導淨虧）

---

## 3. 尺度錯配（stop ÷ ATR）

（引用 VOLATILITY_BASELINE §A；4 月 valid vs 5 月 holdout ATR 差異）

---

## 4. Holdout 風險（不得引用 5 月回測實績）

（若 5 月 ATR > 4 月，固定點數停損預期更緊）

---

## 5. 建議

- [ ] **不推薦** `elected_config` / 標 `grid_no_viable_solution`
- [ ] 仍跑 Phase 4 holdout（`diagnostic_only`）
- [ ] 申請第二輪 grid → 見 [`round2_proposal.md`](../round2_proposal.md)（人類批准後）
- [ ] 主瓶頸在：☐ 進場漏斗 ☐ 出場結構 ☐ 摩擦 ☐ 尺度錯配（可複選）

---

## 6. 進場漏斗（armed / 回踩 / vol）

（引用 VOLATILITY_BASELINE §C）

### 6.1 脈衝是否順勢

（armed 後 W180 `close_delta` / MFE/MAE；分 entered vs timeout cohort 一句）

### 6.2 漏斗瓶頸

（band vs vol vs timeout：`blocked_*` 占比、轉化率、closest_vwap_distance）

### 6.3 vol_1s 門檻是否合理

（150 / 15 在分布中的分位；武裝是否過嚴 / 枯竭門檻是否過嚴）

### 6.4 與 §3 尺度錯配是否一致

（例：stop 偏緊 + 回踩深度 shallow → 雙重 squeeze）

---

## §Decision（人類簽核）

| 欄位 | 值 |
|------|-----|
| 簽核人 | |
| 日期 | |
| 決策 | 採納 / 部分採納 / 推翻 |
| 備註 | |
