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
| train 2025 預期 n | ___（mean_robust **≥30** · skew **≥15**） |
| 預期 gross/趟 | ___（須 **mean > 5** 才有機會 net 正；skew 可 median 負） |
| 預期 net/趟（扣 5 點） | ___ |

### E.1 粗算錨點（MUST · 避免 P-001 式幻想）

| 最接近同族 MVPClosed | 其 v2.1 train 實績（gross/net/median/n） |
|----------------------|------------------------------------------|
| FT-___ | ___ |

**規則**：若新 thesis 預期 gross 比錨點高 **>3 點** 且無新進場機制，人類應 **Reject** 不進 CF。

## E.2 進場機制標籤（MUST 勾一）

- [ ] **Continuation**（順勢 / breakout 後持有）
- [ ] **Mean-reversion**（fade / fill back）
- [ ] **Liquidity / microstructure**（量價失衡）
- [ ] **Other**：___

若勾 mean-reversion 且觸發含 VWAP z-score / fade → 對照 Playbook §4 **VWAP fade 整族已死**。

### E.3 Thesis class（v2.2 · MUST 勾一）

- [ ] **`mean_robust`**（預設）— Gate：[`HOLDOUT_CONTRACT_v2.md`](../ai-backtest-tuning/HOLDOUT_CONTRACT_v2.md) §3.1 · G3 n≥30
- [ ] **`skew`**（低頻厚尾）— Gate：§3.2 · G3S n≥15；**須** pre-register 下表

| 欄位（skew only） | pre-register 值 |
|-------------------|-----------------|
| `payoff_ratio_min` | ___（預設 2.5） |
| `tail_gross_min_pts` | ___（預設 15） |
| `max_consecutive_losses` | ___（預設 10） |
| `max_consecutive_loss_pts` | ___（預設 150） |
| `worst_month_net_pts` | ___（預設 −120） |
| `top3_win_gross_share_max` | ___（預設 0.65） |
| 預期 win_rate | ___% |
| `k_sl × ATR`（**≥ 0.5**） | k = ___ |

**Skew 禁止**：fade 整族 · 舊 FT 換皮 · 固定 6 點主 stop。

## F. Pre-register grid（僅 2025 train）

| 參數 | 值 / 範圍 |
|------|-----------|
| ___ | ___ |

**封印**：valid `2026-01-01`～`2026-03-31`、holdout `2026-04-01`～`2026-06-30` — **不得**依結果增刪參。

## G. Falsify 條件（什麼結果算 thesis 錯了）

- train net ≤ 0 → MVPClosed
- train 過、valid net ≤ 0 → `overfit_suspect`
- mean_robust：median / 單邊 → §3.1
- skew：G-SK1–SK5 任一未過 → disqualify；valid net≤0 → **不得 holdout**；holdout H3S/H4S 未過 → MVPClosed
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
