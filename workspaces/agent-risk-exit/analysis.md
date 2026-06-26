# Analysis — agent-risk-exit（出場與風控調參師）

**Agent**：agent-risk-exit  
**Role**：出場與風控調參師  
**分析日期**：  
**Sweep 範圍**：Train 2026-01～03 / Valid 2026-04  
**Sweep 執行模型**：  
**分析撰寫模型**：

> **身份 MUST**：[`prompts/roles/senior-trading-professional.md`](../../prompts/roles/senior-trading-professional.md)  
> **共享假設 MUST**：[`SHARED_ASSUMPTIONS.md`](../SHARED_ASSUMPTIONS.md)  
> **編制**：[`AGENT_ROSTER.md`](../../docs/features/ai-backtest-tuning/AGENT_ROSTER.md) §4

---

## 1. 角色與假說（Role & Hypothesis）

**SHARED_ASSUMPTIONS 合規聲明**：本次 sweep 完全遵守 SHARED_ASSUMPTIONS.md **v1.1**（2026-06-26）。

**本職能核心目標**：

**本次調參假說**：

**選擇這些 grid 邊界的理由**（對照 SHARED_ASSUMPTIONS §7；skew / 連虧心理底線）：

**預期參數交互**（≥2 組）：
-

**預期 Trade-off**：

---

## 2. Baseline 表現（Baseline Performance）

| 指標 | Baseline 值 | 備註 |
|------|-------------|------|
| valid_score | | |
| daily_pnl_points | | |
| expectancy_net | | |
| max_drawdown_points | | |
| quick_stop_loss_rate | | |
| trade_count | | |
| day_count | | |

**交易員一句話評論**：

**是否值得進入 Sweep**：  
- [ ] 是  
- [ ] 否

---

## 3. Sweep 結果與關鍵發現

| Rank | valid_score | params | max_drawdown_points | quick_stop_loss_rate | vs Baseline |
|------|-------------|--------|---------------------|----------------------|-------------|
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |

**最差 1 組**：

**參數敏感度**：

**最有價值的一個發現**（出場結構 / skew 語言）：

---

## 4. Overfitting 與穩健性評估

| 指標 | Train | Valid | Divergence | 評論 |
|------|-------|-------|------------|------|
| max_drawdown_points | | | | |
| expectancy_net | | | | |
| daily_pnl_points | | | | |
| trade_count | | | | |

**Overfitting 風險**：低 / 中 / 高 — 理由：

**Holdout 風險因子**（不得引用 5 月實數）：

**整體穩健性**：

---

## 5. 推薦與下一步

- [ ] 建議進入 Holdout 候選  
- [ ] 不推薦

```yaml
recommended_params:
  fixed_tp_points:
  trail_points:
  max_consecutive_loss:
```

**為什麼推薦**：

### 協作備註（與 agent-execution 的 trail 邊界、conservative 的進場密度）

### 免責與人類決策權

- 不構成 Pilot / Live Ready。Holdout：未跑。未放大 `max_daily_loss_points`。

---

## Phase 3.4 交叉審核 Checklist（leaderboard 前 MUST）

- [ ] 已完成 peer_review（`peer_review_agent-regime.md`）
- [ ] 已回覆 peer_review 質疑（若有）

**回覆摘要**：
