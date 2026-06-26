# Analysis — agent-regime（市況濾網研究員）

**Agent**：agent-regime  
**Role**：市況濾網研究員  
**分析日期**：  
**Sweep 範圍**：Train 2026-01～03 / Valid 2026-04  
**Regime 線**：Trend / Structure（擇一；與 `grid.json` 一致）  
**Sweep 執行模型**：  
**分析撰寫模型**：

> **身份 MUST**：[`prompts/roles/senior-trading-professional.md`](../../prompts/roles/senior-trading-professional.md)  
> **共享假設 MUST**：[`SHARED_ASSUMPTIONS.md`](../SHARED_ASSUMPTIONS.md)  
> **編制**：[`AGENT_ROSTER.md`](../../docs/features/ai-backtest-tuning/AGENT_ROSTER.md) §5  
> **FT-002**：[`docs/features/smc-structure-filter/SPEC.md`](../../docs/features/smc-structure-filter/SPEC.md)

---

## 1. 角色與假說（Role & Hypothesis）

**SHARED_ASSUMPTIONS 合規聲明**：本次 sweep 完全遵守 SHARED_ASSUMPTIONS.md **v1.1**（2026-06-26）。

**本職能核心目標**：

**本次調參假說**：

**Regime 線與 grid 邊界理由**（CAL-8 前置；filter 預設關、研究 overlay 須註明互斥）：

**預期參數交互**（≥2 組）：
-

**預期 Trade-off**：

---

## 2. Baseline 表現（Baseline Performance）

| 指標 | Baseline 值 | 備註 |
|------|-------------|------|
| valid_score | | filter **關**（UAT 預設） |
| daily_pnl_points | | |
| trade_count | | |
| day_count | | |

**交易員一句話評論**：

**是否值得進入 Sweep**：  
- [ ] 是  
- [ ] 否

---

## 3. Sweep 結果與關鍵發現

| Rank | valid_score | params | veto 相關 | vs Baseline |
|------|-------------|--------|-----------|-------------|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |

**最差 1 組**：

**veto_metrics / structure_veto_metrics 解讀**（自 `sweep_result.jsonl`）：

| Combo | veto_rate / structure_veto_rate | delta_expectancy（若有） | 評論 |
|-------|--------------------------------|--------------------------|------|
| | | | |

**參數敏感度**：

**最有價值的一個發現**：

---

## 4. Overfitting 與穩健性評估

| 指標 | Train | Valid | Divergence | 評論 |
|------|-------|-------|------------|------|
| daily_pnl_points | | | | |
| trade_count | | | | |

**Overfitting 風險**：低 / 中 / 高 — 理由：

**Holdout 風險因子**：

**整體穩健性**：

---

## 5. 推薦與下一步

- [ ] 建議進入 Holdout 候選（**研究用**；非建議開 filter）  
- [ ] 不推薦

```yaml
recommended_params:
  # Trend 線範例；Structure 線請改對應 keys
  trend_filter_enabled:
  trend_min_strength:
  trend_slope_min:
```

**為什麼推薦 / 不推薦開 filter**：

### 協作備註（CAL-8、P6-1-CAL；不得寫 Pilot 直接開 filter）

### 免責與人類決策權

- 不構成 Pilot / Live Ready。Holdout：未跑。UAT 預設 filter 仍關。

---

## Phase 3.4 交叉審核 Checklist（leaderboard 前 MUST）

- [ ] 已完成 peer_review（`peer_review_agent-risk-exit.md`）
- [ ] 已回覆 peer_review 質疑（若有）

**回覆摘要**：
