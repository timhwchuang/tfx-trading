# Judge Opinion — FT-003 Phase 4 獨立裁判

**裁判角色**：agent-election-judge（資深交易員獨立審核）  
**候選 agent**：  
**分析日期**：YYYY-MM-DD  
**使用模型**：（**首選 Claude 4.8** — 見 ROSTER §8.2；fallback：GPT-5.x High Reasoning，或 Composer 2.5 + §8.4 加嚴 checklist）

> **輸入 MUST**：候選 `analysis.md`、雙方 `peer_review_*.md`、`election_report.md`、holdout KPI  
> **禁止**：重新 sweep、修改參數、推翻整個實驗設計（除非方法論明顯錯誤）

---

## 1. Holdout vs Valid 衰退是否合理？

| 指標 | Valid（04） | Holdout（05） | 衰退幅度 | 可接受？ |
|------|-------------|---------------|----------|----------|
| valid_score / holdout_score | | | | |
| expectancy_net | | | | |
| max_drawdown_points | | | | |
| quick_stop_loss_rate | | | | |
| trade_count | | | | |

**評論**（是否超出正常市況波動可解釋範圍）：

---

## 2. Overfitting 跡象

- Train/Valid 是否已有 divergence？Holdout 是否再惡化？  
- 是否只在特定樣本區間表現好？  

**判斷**：低 / 中 / 高 overfitting 風險 — 理由：

---

## 3. 市況解釋力

（5 月與 4 月行情差異是否足以解釋衰退？是否更像參數過擬合？）

---

## 4. 資本保全觀點

- Holdout MDD 是否在可接受範圍？  
- 秒停損 / 連虧是否有尾部風險？  
- tuning agent 與 peer_review 是否漏報風險？  

---

## 5. 最終建議

- [ ] **accept** — 可作為 UAT 候選 config  
- [ ] **conditional_accept** — 條件：  
- [ ] **reject** — 主因：

**給人類的一句話**（若人類將裁判全權交給 AI，此節即決策依據）：

---

## 6. 免責

本意見 **不** 構成 Live Ready；人類保留最終 veto。若採納本裁判全文，人類須在 `election_report.md` 記錄。
