# Workspaces — AI 回測調參（FT-003）

> **MVP 狀態（2026-06-27）**：**已收尾** — [`election_report.md`](election_report.md) 標 `grid_no_viable_solution` + `diagnostic_only`；**不產** `elected_config.yaml`。下一階段：**Strategy v2**（見 [`strategy_diagnosis.md`](strategy_diagnosis.md) §7 · [`docs/TODO.md`](../docs/TODO.md)）。

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
Phase 4（MVP）：**已收尾** — [`election_report.md`](election_report.md)（`diagnostic_only`；holdout 未跑）。Strategy v2 另開 workspace / grid。

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
| `logs/sweep_progress.log` | sweep JSONL 進度（預設 bulk + 60s heartbeat 含 `phase_elapsed_sec`；`--per-day` 才有逐日 `day` 事件）。`--heartbeat-sec` 最小 5s。勿 redirect |
| `logs/sweep.lock` | 單實例鎖；第二個 sweep 會 `FAILED exit=2`；程序被強殺可能殘留，下次啟動若 PID 已死會自動替換 |
| `sweep_result.jsonl` | 跑程中依 **完成順序** append（非排名）；`sweep_done` 後才依 `valid_score` 排序覆寫 |
| `robustness_report.md` | **Phase 6 only**（Post-MVP）；模板 [`_template/robustness_report.md`](_template/robustness_report.md) |
| [`VOLATILITY_BASELINE.md`](VOLATILITY_BASELINE.md) | **Phase 3.6** 四平面診斷數據 SSOT（§A/B 尺度 · **§C 進場漏斗** · §D 出場） |
| [`strategy_diagnosis.md`](strategy_diagnosis.md) | **Phase 3.6** 四 agent 合成診斷（含 §6 進場漏斗；§Decision Option A） |
| [`election_report.md`](election_report.md) | **Phase 4 MVP 收尾** — `grid_no_viable_solution` + `diagnostic_only` |
| [`round2_proposal.md`](round2_proposal.md) | Round 2 出場 grid — **已否決**（2026-06-27） |
| `reports/volatility_baseline.json` | Phase 3.6 §A/B 機器可讀 |
| `reports/entry_funnel.json` | Phase 3.6 §C 機器可讀（`ft003_episode_diagnosis.py`） |
| `_template/` | 範本（`analysis.md`、`peer_review.md`、`judge_opinion.md`、`election_report.md`、`robustness_report.md`） |

### Phase 3 sweep 啟動（`apps/trading-app/src`）

```powershell
python scripts\ft003_run_sweep.py agent-conservative
```

預設 **bulk**（快）。要逐日進度：`--per-day`。監看：`Get-Content ..\..\..\workspaces\agent-conservative\logs\sweep_progress.log -Wait -Tail 3`

**驗收**：第一行應為 `{"event":"sweep_start","run_id":...}`；結束為 `sweep_done`。若仍是 `param_sweep combo 1/9` 純文字，代表舊跑法或 Tee-Object，不是新版 tracker。

**強殺 / 中斷**：Task Manager 關閉可能無 `sweep_failed`——看最後一行 `event` 與 `sweep.lock` 是否殘留。中途 `sweep_result.jsonl` 勿當排名。

### Phase 3.6 四平面診斷（四位 sweep 完成後）

Methods SSOT：[`ENTRY_FUNNEL_METRICS.md`](../docs/features/ai-backtest-tuning/ENTRY_FUNNEL_METRICS.md)

```powershell
cd apps\trading-app\src
$env:PYTHONPATH="."
python scripts\ft003_volatility_baseline.py --markdown-out ..\..\..\workspaces\VOLATILITY_BASELINE.md
python scripts\ft003_episode_diagnosis.py --agent agent-conservative --from-date 2026-04-01 --to-date 2026-04-30 --markdown-append ..\..\..\workspaces\VOLATILITY_BASELINE.md --json-out ..\..\..\workspaces\reports\entry_funnel.json
python scripts\ft003_exit_diagnosis.py --agent agent-conservative --markdown-append ..\..\..\workspaces\VOLATILITY_BASELINE.md
```

見 [`PLAN.md`](../docs/features/ai-backtest-tuning/PLAN.md) Phase 3.6 · [`SPEC.md`](../docs/features/ai-backtest-tuning/SPEC.md) §4.6 · SHARED_ASSUMPTIONS **v1.3** §4.1–§4.2

### Round 2 出場尺度

**已否決** — 見 [`round2_proposal.md`](round2_proposal.md) · [`election_report.md`](election_report.md)。勿執行 `agent-risk-exit` round2 sweep。

**UAT `apps/trading-app/config/config.yaml` 凍結至 Phase 1 Pass**；只改 `workspaces/` 內 config。
