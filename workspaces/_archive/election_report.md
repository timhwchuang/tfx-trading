# Election Report — FT-003 Phase 4（MVP 收尾 · diagnostic_only）

**候選 agent**：無（`grid_no_viable_solution`）  
**撰寫者**：Tim（人類）  
**日期**：2026-06-27  
**Holdout 區間**：2026-05 — **未解封、未回測**（`diagnostic_only` 收尾）

> **結論**：本輪 MVP **不產出** `elected_config.yaml`；四平面 valid 冠軍淨期望全負，Phase 3.6 診斷已足。下一階段：**Strategy v2 重設計**（Option A，見 [`strategy_diagnosis.md`](strategy_diagnosis.md) §7）。

**診斷 SSOT**：[`strategy_diagnosis.md`](strategy_diagnosis.md) · [`VOLATILITY_BASELINE.md`](VOLATILITY_BASELINE.md) · [`reports/entry_funnel.json`](reports/entry_funnel.json)

---

## 1. 候選與 Valid 排名

| Agent | valid_score | 淨期望/趟 | trade_count | 備註 |
|-------|-------------|-----------|-------------|------|
| agent-risk-exit | -14.21 | -5.80 | 113 | 四平面 valid_score 最佳，仍淨負 |
| agent-execution | -16.14 | -6.48 | 150 | QSL 改善，毛點深度為負 |
| agent-conservative | -18.83 | -4.94 | 162 | 毛點 +10 / valid，摩擦主導 |
| agent-regime | -21.32 | -5.10 | 151 | grid 無辨識力 |

**leaderboard 狀態**：四筆均 `valid_submitted`；**無** `valid_leader`（無淨正候選可晉級 holdout）。

**Phase 3.6 合成結論**（[`strategy_diagnosis.md`](strategy_diagnosis.md)）：

- 全平面淨期望 < 0；conservative 毛期望 ≈ **+0.06/趟**，淨 **-4.94/趟** → 摩擦 + 無 gross edge
- 進場漏斗：瓶頸在「價格不回 VWAP」（timeout 67% 從未 near_vwap）；entered 子集 armed 後逆勢漂移
- 尺度：`hard_stop=6` ≈ **0.23×ATR**（4 月 valid），與 pullback_depth p50 ≈ 1×ATR 雙重 squeeze
- **Round 2** 出場 grid：**已否決**（[`round2_proposal.md`](round2_proposal.md)）

---

## 2. Holdout vs Valid KPI 對照

| 指標 | Valid（2026-04） | Holdout（2026-05） | 備註 |
|------|------------------|-------------------|------|
| valid_score / holdout_score | 最佳 -14.21 | **N/A** | holdout **未跑** |
| expectancy_net | 全 grid 淨負 | **N/A** | |
| quick_stop_loss_rate | 17–33% | **N/A** | |
| trade_count | 113–162 | **N/A** | |

**Holdout 決策**：`diagnostic_only` — 5 月僅作 **風險敘事**（ATR p50 33.8 > valid 25.7，`stop_ratio` 降至 18%），見 [`strategy_diagnosis.md`](strategy_diagnosis.md) §4。  
**不為完整性解封 2026-05**：`FT003_HOLDOUT_UNSEAL` 未設；診斷已支持 `grid_no_viable_solution`，再跑 holdout 不改結論。

---

## 3. Overfit 判定

| 項目 | 判定 |
|------|------|
| 典型 overfit（valid 好、holdout 崩） | **不適用**（無 holdout 實績） |
| Grid 內泛化 | 九組 / 四平面 **淨期望皆負** → 非 overfit，是 **edge 不存在** |
| 結論標籤 | **`grid_no_viable_solution`**（非 `overfit_suspect`） |

根因（§Decision）：gross edge ≈ 0 + 進場逆向選擇 + 固定點數出場尺度錯配 + 摩擦 5 點/趟；**非**單一 knob 可解。

---

## 4. 獨立裁判意見摘要

**跳過** — 無 holdout 候選、無 Accept/Reject 對象。

依 [`PLAN.md`](../docs/features/ai-backtest-tuning/PLAN.md) Phase 4：`agent-election-judge` 適用於 valid 冠軍 holdout 選舉；本輪以 Phase 3.6 **`grid_no_viable_solution`** 直接收尾，**不產** `judge_opinion.md`。

---

## 5. 人類最終決策記錄（MUST）

**對 judge_opinion 的態度**：

- [x] **N/A — 跳過裁判** — 無可選 config；Phase 3.6 診斷 + leaderboard 已足

**最終決策**：

- [ ] Accept → 產出 `elected_config.yaml`
- [x] **Reject / MVP 收尾** → **`grid_no_viable_solution`** + **`diagnostic_only`**
- [ ] Conditional Accept

**後續**（非本檔範圍）：

1. **Strategy v2** — thesis 二選一（breakout 延續 vs 純均值回歸）；出場 ATR-scaled；valid 毛期望/趟 > 5 再 sweep
2. 保留 engine / backtest / FT-003 診斷工具 / `tick_cache`；**凍結** vwap-momentum hybrid 作 Pilot 候選
3. Post-MVP Phase 6 長歷史：待 v2 或人類另開；**不以**本輪 MVP holdout 作 Gate

**簽核**：Tim · 2026-06-27
