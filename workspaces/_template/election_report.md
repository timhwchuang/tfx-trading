# Election Report — FT-003 Phase 4

**候選 agent**：  
**撰寫者**：（tuning agent / 人類）  
**日期**：YYYY-MM-DD  
**Holdout 區間**：2026-05

---

## 1. 候選與 Valid 排名

（leaderboard 冠軍 / 亞軍；`valid_score`、params、trade_count）

---

## 2. Holdout vs Valid KPI 對照

| 指標 | Valid（04） | Holdout（05） | 備註 |
|------|-------------|---------------|------|
| valid_score / holdout_score | | | |
| expectancy_net | | | |
| max_drawdown_points | | | |
| quick_stop_loss_rate | | | |
| trade_count | | | |

---

## 3. Overfit 判定（tuning agent 觀點）

（是否 overfit_suspect；train/valid/holdout 敘述）

---

## 4. 獨立裁判意見摘要

（`judge_opinion.md` 結論：`accept` / `conditional_accept` / `reject` + 一句話）

---

## 5. 人類最終決策記錄（MUST）

> 即使採納 `judge_opinion`，人類（或授權 AI 後由人類補簽）**MUST** 填寫本節，供日後稽核。

**對 judge_opinion 的態度**（擇一並簡述理由）：

- [ ] **採納** — 與 judge 結論一致，理由：
- [ ] **部分採納** — 採納哪些、不採納哪些，理由：
- [ ] **推翻** — judge 建議與最終決策不同，理由：

**最終決策**：

- [ ] **Accept** → 產出 `elected_config.yaml`
- [ ] **Reject** → `status: overfit_suspect` 或 `rejected`
- [ ] **Conditional Accept** — 條件：

**簽核**：（人類姓名 / 日期；若全權交 AI 裁判，寫「採納 judge_opinion 全文，人類複核日期」）
