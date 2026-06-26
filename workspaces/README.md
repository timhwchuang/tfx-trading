# Workspaces — AI 回測調參（FT-003）

> **AI 第一份文件**：[`docs/features/ai-backtest-tuning/AGENT_ROSTER.md`](../docs/features/ai-backtest-tuning/AGENT_ROSTER.md)（你是哪位、開工 prompt）  
> **執行步驟**：[`PLAN.md`](../docs/features/ai-backtest-tuning/PLAN.md)

## 競賽編制（四位）

| # | 目錄 | 職稱 | 開工讀 |
|---|------|------|--------|
| 1 | [`agent-conservative/`](agent-conservative/) | 資本保全調參師 | `BRIEF.md` + ROSTER §2 |
| 2 | [`agent-execution/`](agent-execution/) | 執行品質調參師 | `BRIEF.md` + ROSTER §3 |
| 3 | [`agent-risk-exit/`](agent-risk-exit/) | 出場與風控調參師 | `BRIEF.md` + ROSTER §4 |
| 4 | [`agent-regime/`](agent-regime/) | 市況濾網研究員 | `BRIEF.md` + ROSTER §5 |

**MVP 必跑**：#1、#2。**擴充**：#3、#4 目錄已就緒，可與 MVP 並行或盤後串行。

每位 session：**MUST** `@prompts/roles/senior-trading-professional.md` + [`SHARED_ASSUMPTIONS.md`](SHARED_ASSUMPTIONS.md) + `@workspaces/<slug>/BRIEF.md`。

Phase 3.4：**analysis 完成後、leaderboard 之前** — 雙向 `peer_review_*.md`（MVP：#1↔#2；擴充：#3↔#4；見 ROSTER §1.6）。  
Phase 4：**新開獨立 AI 對話** 執行 **agent-election-judge** → [`judge_opinion.md`](judge_opinion.md)（首選 **Claude 4.8**；fallback ROSTER §8.2）；人類填 `election_report.md` **§5**。

## 如何新增調參 Agent

1. 複製 `agent-conservative/`（或 `_template/` 內 analysis / peer_review 範本）為 `agent-<slug>/`
2. 撰寫 `BRIEF.md`（職能、grid 邊界、禁止事項）並在開頭引用 **SHARED_ASSUMPTIONS v1.1** + **PLAN.md**
3. 建立 `config/config.yaml`（僅改 workspace 內；**不得**改 `apps/trading-app/config/config.yaml`）
4. 開工前跑 `python -m sweep.overlay_smoke` 驗證每個 grid key
5. 完成 `analysis.md` 後執行 Phase 3.4 雙向 `peer_review_*.md`，再提交 leaderboard

## 共通

| 路徑 | 說明 |
|------|------|
| [`SHARED_ASSUMPTIONS.md`](SHARED_ASSUMPTIONS.md) | 滑價、ATR、流動性、跨 agent 邊界（開工必讀） |
| `DATA_SPLIT.md` | train / valid / holdout |
| `leaderboard.jsonl` | 競賽排名 |
| `_template/` | 範本（`analysis.md`、`peer_review.md`、`judge_opinion.md`、`election_report.md`） |

**UAT `apps/trading-app/config/config.yaml` 凍結至 Phase 1 Pass**；只改 `workspaces/` 內 config。
