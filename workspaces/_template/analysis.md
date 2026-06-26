# Analysis — {agent-slug}（{職稱}）

**Agent**：{agent-slug}  
**Role**：{職稱}  
**分析日期**：YYYY-MM-DD  
**Sweep 範圍**：Train 2026-01～03 / Valid 2026-04（Holdout 2026-05 封印）  
**Sweep 執行模型**：（例：Composer 2.5 — 跑 backtest / param_sweep）  
**分析撰寫模型**：（例：Composer 2.5 或 Claude 4.8 — 填 analysis / 解讀 KPI）

> **身份 MUST**：[`prompts/roles/senior-trading-professional.md`](../../prompts/roles/senior-trading-professional.md)  
> **共享假設 MUST**：[`SHARED_ASSUMPTIONS.md`](../SHARED_ASSUMPTIONS.md)  
> **編制**：[`docs/features/ai-backtest-tuning/AGENT_ROSTER.md`](../../docs/features/ai-backtest-tuning/AGENT_ROSTER.md)  
> **日期切分**：[`DATA_SPLIT.md`](../DATA_SPLIT.md)

---

## 1. 角色與假說（Role & Hypothesis）

**SHARED_ASSUMPTIONS 合規聲明**（MUST）：  
本次 sweep 完全遵守 [`SHARED_ASSUMPTIONS.md`](../SHARED_ASSUMPTIONS.md) **v1.1**（2026-06-26）。

**本職能核心目標**（1～2 句）：  
（例：在控制 MDD 的前提下，提升 valid expectancy 的穩定性。）

**本次調參假說**（可證偽陳述）：  
（例：「提高 min_atr_threshold 可過濾低波動假突破，降低無效交易與摩擦侵蝕。」）

**選擇這些 grid 邊界的理由**（市況、流動性、風控；須對照 SHARED_ASSUMPTIONS §3–§5）：  
（說明為何是這個區間，而非更寬/更窄；提及台指期微結構或 Q1/Apr 特性。）

**預期參數交互**（至少 2 組）：  
- （例：`min_atr_threshold` ↑ × `entry_band_points` 不變 → 進場次數可能非線性下降）  
- （例：…）

**預期 Trade-off**：  
（例：犧牲交易頻率，換取較低 MDD 與較穩定 equity curve。）

---

## 2. Baseline 表現（Baseline Performance）

**Valid 期間（2026-04）預設參數 KPI**：

| 指標 | Baseline 值 | 備註 |
|------|-------------|------|
| valid_score | | composite |
| daily_pnl_points | | 毛點數合計 |
| expectancy_net | | `performance_aggregate` |
| sharpe_net | | 若有 |
| max_drawdown_points | | |
| quick_stop_loss_rate | | |
| trade_count | | exit 總數 |
| day_count | | 交易日數 |

**交易員一句話評論**：  
（樣本量、秒停損、MDD；是否值得進 sweep。）

**是否值得進入 Sweep**：  
- [ ] 是（理由）  
- [ ] 否（原因）

---

## 3. Sweep 結果與關鍵發現（Sweep Results & Key Findings）

**Valid Top-3**（依 valid_score）：

| Rank | valid_score | params（關鍵差異） | vs Baseline 改善 | 主要代價 |
|------|-------------|-------------------|------------------|----------|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |

**最差 1 組**（理解邊界行為）：  
| params | valid_score | 觀察 |

**參數敏感度**（至少 2～3 點）：  
- 哪個 knob 對 KPI 影響最大？  
- 是否有閾值 / 非線性？  
- 參數間交互？

**本次 Sweep 最有價值的一個發現**（交易員語言，非只報數）：  
（例：「min_atr 28→34 減少 18% 交易，Sharpe 僅降 0.12，低波動訊號多為噪音。」）

### 摩擦對策略的實際影響（MUST — SHARED_ASSUMPTIONS §3.1）

TMFR1 每趟 round-trip **淨扣 5 點**（手續費 + 稅；不含撮合滑價）。請討論：

- 摩擦如何改變 **盈虧比（payoff）** 與 **expectancy_net**（相對 gross）？
- 若提高進場門檻（如 `min_atr_threshold` ↑）減少交易次數，摩擦總成本是否下降足以抵銷機會損失？
- 本 sweep 推薦配置的 **break-even 勝率 / 平均獲利** 在扣摩擦後是否仍可行？

---

## 4. Overfitting 與穩健性評估（Overfitting & Robustness）

**Train vs Valid**（01～03 vs 04）：

| 指標 | Train | Valid | Divergence | 評論 |
|------|-------|-------|------------|------|
| daily_pnl_points | | | | |
| expectancy_net | | | | |
| max_drawdown_points | | | | |
| quick_stop_loss_rate | | | | |
| trade_count | | | | |

**Overfitting 風險**：**低 / 中 / 高**  
**理由**（至少 2 點）：

**可能影響 Holdout 的風險因子**（2～3 點；**不得**引用 2026-05 實際數字）：  
（例：5 月若出現類似 4 月中旬快速反轉，現配置可能…）

**整體穩健性評價**（1～2 句，資深交易員視角）：

---

## 5. 推薦與下一步（Recommendation & Next Steps）

**本次 Sweep 最終推薦**：  
- [ ] **建議進入 Holdout 候選**（見下方 params）  
- [ ] **不推薦**（主因）

**推薦配置（若有）**：

```yaml
recommended_params:
  # key: value
```

**為什麼推薦（交易員視角）**：  
（風控、實務可行性；非只 valid_score 最高。）

### 協作備註

（與其他 agent / UAT / compare_fill_audits 等。）

### 免責與人類決策權

- 本分析 **不** 構成 Pilot / Live Ready。  
- Holdout（2026-05）：Phase 4 前填「未跑」。  
- Overfitting 自評摘要：（low / medium / high + 一句話）

---

## Phase 3.4 交叉審核 Checklist（leaderboard 前 MUST）

- [ ] 已確認與 [`SHARED_ASSUMPTIONS.md`](../SHARED_ASSUMPTIONS.md) **v1.1** 及 [`PLAN.md`](../../docs/features/ai-backtest-tuning/PLAN.md) 一致
- [ ] 已完成 peer_review（由對方 agent 審核；見 `peer_review_*.md`）
- [ ] 已回覆 peer_review 提出的質疑（若有；寫於 §5 協作備註或本節下方）

**回覆摘要**（若無質疑可寫「無」）：

