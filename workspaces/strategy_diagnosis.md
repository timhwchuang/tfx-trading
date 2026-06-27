# Strategy Diagnosis — FT-003 Phase 3.6

**撰寫日期**：2026-06-27  
**Phase 3**：四位 sweep + analysis + peer_review + leaderboard — ✅ 完成  
**Phase 3.6**：市場尺度診斷 — 進行中（`cache_audit`、§C 進場漏斗待補）  
**資料 SSOT**：[`VOLATILITY_BASELINE.md`](VOLATILITY_BASELINE.md)

> 本檔合成四 agent sweep + 市場尺度診斷；**不是** leaderboard、**不是** `elected_config`。  
> 契約：[`SPEC.md`](../docs/features/ai-backtest-tuning/SPEC.md) §4.6 · [`PLAN.md`](../docs/features/ai-backtest-tuning/PLAN.md) Phase 3.6

---

## 1. 四平面 sweep 摘要

| Agent | 冠軍 valid_score | 淨期望/趟 | QSL | 結論（一句） |
|-------|------------------|-----------|-----|--------------|
| agent-conservative | -18.83 | -4.94 | 27.8% | 進場濾網相對最佳，九組仍全負；valid 毛點 +10 但淨 -800 |
| agent-execution | -16.14 | -6.48 | 19.3% | trail=6 + IOC=3 壓低 QSL，毛點仍深度為負 |
| agent-risk-exit | -14.21 | -5.80 | 16.8% | 四軸 valid_score 最佳；出場結構主效應，淨期望仍負 |
| agent-regime | -21.32 | -5.10 | 32.5% | grid 無辨識力、veto 占位；不建議開 filter |

**全平面是否淨負**：☑ 是（已完成 grid 內冠軍淨期望皆 < 0） ☐ 否

---

## 2. 摩擦 vs gross edge

- **摩擦**：5 點/趟（SHARED_ASSUMPTIONS v1.2 §3）。
- **conservative 冠軍**：valid 毛 PnL **+10** 點 / 162 趟 → 毛期望約 **+0.06/趟**；淨 **-4.94/趟** → 摩擦主導。
- **execution 冠軍**：valid 毛 **-221.5** / 150 趟 → 毛期望約 **-1.48/趟**；淨 **-6.48/趟**。
- **baseline（預設 config）**：毛 -48、淨 -798（150 趟）→ 策略邏輯在 valid 區間亦無正 gross edge。

**結論**：即使個別平面改善 QSL 或 valid_score，**淨期望無一為正**；問題非單一平面可解，需尺度與出場結構重設。

---

## 3. 尺度錯配（stop ÷ ATR）

引用 [`VOLATILITY_BASELINE.md`](VOLATILITY_BASELINE.md) §A：

| 月 | ATR p50 | stop_ratio (HS6) | 備註 |
|----|---------|------------------|------|
| 2026-01 | 15.7 | 38% | 停損約 0.4×ATR |
| 2026-04 valid | 25.7 | 23% | sweep 評估區間 |
| 2026-05 holdout | 33.8 | 18% | 僅風險敘事 |

固定 `hard_stop_points=6`、`trail_points=8` 相對 4 月 ATR 僅 **0.23–0.31×**；相對 1m range p50（25 點）`range_ratio≈0.24`，停損常落在分鐘噪音內。QSL 28–33%（baseline）與 §D 秒停損結構一致。

---

## 4. Holdout 風險（不得引用 5 月回測實績）

- 5 月 ATR p50（33.8）> 4 月 valid（25.7）；`stop_ratio` 降至 **18%**。
- 若維持固定點數出場，holdout 預期 **更緊停損、QSL 升、淨期望惡化**（敘事 only，未跑 5 月回測）。
- 指數 med Close 41k+ vs 4 月 37k → regime 與波動雙漂移。

---

## 5. 建議

- [x] **不推薦** `elected_config` / 標 `grid_no_viable_solution`
- [ ] 仍跑 Phase 4 holdout（`diagnostic_only`）— 待人類決策
- [ ] 申請第二輪 grid → 見 [`round2_proposal.md`](round2_proposal.md)（**草案已備**；待人類 §Approval）

**第二輪方向（草案 → [`round2_proposal.md`](round2_proposal.md)）**：

1. `agent-risk-exit`：`hard_stop_points` 10–16 × `trail_points` 6/8 × `fixed_tp_points` 20/24（16 combos）
2. 鎖定 conservative 進場 + execution IOC；不併入 regime
3. 否證標準見 proposal §4；批准後才替換 `grid.json` 並 sweep

---

## §Decision（人類簽核）

| 欄位 | 值 |
|------|-----|
| 簽核人 | _待 Phase 3.6 診斷補全後填寫_ |
| 日期 | |
| 決策 | 採納 / 部分採納 / 推翻 |
| 備註 | Phase 3.6 診斷產出禁止用於本輪 leaderboard 選參 |
