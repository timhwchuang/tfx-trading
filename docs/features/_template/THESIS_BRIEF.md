# Thesis Brief（FT-012+ 必填 · Pre-register）

> 複製本檔內容到 `docs/features/<slug>/SPEC.md` §1–§3。  
> **CF 開跑前** queue 狀態 MUST 為 `human-approved`。  
> Playbook：[`ALPHA_RESEARCH_PLAYBOOK.md`](../ai-backtest-tuning/ALPHA_RESEARCH_PLAYBOOK.md)

---

## A. 一句話 thesis

（例：僅在早盤前 90 分鐘、VWAP 上方 k×ATR 過度延伸且 1m 波動分位 < p30 時做空 fade，目標回歸 VWAP。）

## B. 錯價因果（為什麼會賺）

- **誰在錯**：___
- **何時**：交易所時間 ___:___ – ___:___
- **機制**：continuation / mean-reversion / liquidity / other ___

## C. 與已死 thesis 的本質差異

| 最接近的舊 FT | 為何不是同一個 |
|---------------|----------------|
| FT-___ | ___ |

## D. 進出規則（可程式化）

| 項目 | 定義 |
|------|------|
| 方向 | Long-only / Short-only / 雙向 |
| 進場 | ___ |
| 停損 | `k_sl × ATR`（k = ___） |
| 停利 / trail | ___ |
| 時間出場 | ___ |
| 日內 flatten | 是 / 否 |

## E. 頻率與摩擦粗算

| 項目 | 估計 |
|------|------|
| train 2025 預期 n | ___（須 ≥ 30） |
| 預期 gross/趟 | ___（須 > 5 才有機會 net 正） |
| 預期 net/趟（扣 5 點） | ___ |

## F. Pre-register grid（僅 2025 train）

| 參數 | 值 / 範圍 |
|------|-----------|
| ___ | ___ |

**封印**：valid `2026-01-01`～`2026-03-31`、holdout `2026-04-01`～`2026-06-30` — **不得**依結果增刪參。

## G. Falsify 條件（什麼結果算 thesis 錯了）

- train net ≤ 0 → MVPClosed
- train 過、valid net ≤ 0 → `overfit_suspect`
- median / 單邊 disqualify → §3.1
- ___

## H. 人類簽核

| 欄位 | 值 |
|------|-----|
| 簽核人 | |
| 日期 | |
| 決策 | approved / rejected / revise |

## I. CF code review（Phase 0b · train 前必填）

| 欄位 | 值 |
|------|-----|
| Review 方式 | Bugbot / 人類 |
| Review 日期 | |
| 審查檔案 | `reporting/*_counterfactual.py` · `tests/reporting/test_*` |
| 結果 | PASS / FAIL |
| 備註 | （修正項摘要） |
