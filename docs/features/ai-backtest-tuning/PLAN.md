---
id: FT-003
slug: ai-backtest-tuning
status: InProgress
opened: 2026-06-26
owner: human+agent
target: Pilot-prep
phases: [0, 1, 2, 3, 4, 5, 6]
blockers: []
---

# FT-003 — AI 輔助回測調參（PLAN）

> **PLAN** = 怎麼交付 SPEC。
> **給 AI 的第一份文件**：先讀 [`AGENT_ROSTER.md`](AGENT_ROSTER.md)（你是哪位、假說、grid 邊界、開工 prompt），再讀本檔 Phase 順序。

## 給 AI Agent 的閱讀順序（MUST）

1. [`AGENT_ROSTER.md`](AGENT_ROSTER.md) — 確認你的 **#編號、slug、職稱** 與 **開工 Prompt**
2. [`prompts/roles/senior-trading-professional.md`](../../../prompts/roles/senior-trading-professional.md) — **身份全文**（資深台指期交易員）
3. [`SPEC.md`](SPEC.md) §3-§4 — live vs backtest、overfitting、§4.4 預算
4. [`workspaces/SHARED_ASSUMPTIONS.md`](../../../workspaces/SHARED_ASSUMPTIONS.md) — 跨 agent 假設 SSOT
5. `workspaces/<slug>/BRIEF.md` — 本 workspace 捷徑
6. 本檔 — 執行 Phase 2→3→3.4

**你只有一個 workspace**。不要代操其他 agent 的目錄，除非人類明確指派協調任務。

## 競賽編制摘要

| #   | Slug                 | 職稱             | MVP      |
| --- | -------------------- | ---------------- | -------- |
| 1   | `agent-conservative` | 資本保全調參師   | **必跑** |
| 2   | `agent-execution`    | 執行品質調參師   | **必跑** |
| 3   | `agent-risk-exit`    | 出場與風控調參師 | 擴充     |
| 4   | `agent-regime`       | 市況濾網研究員   | 擴充     |

細節、假說、允許/禁止 tune 的 keys、完整 copy-paste prompt → **[`AGENT_ROSTER.md`](AGENT_ROSTER.md)**。

## Scope

- `workspaces/` 多 agent 隔離調參（**身份 = senior-trading-professional**）
- `param_sweep` / `-m backtest --report` 標準化跑法
- train / valid / holdout 防 overfitting
- 產出 `elected_config.yaml`（候選，非自動上線）

## Out of scope

- 修改 UAT/live 的 `apps/trading-app/config/config.yaml`（Phase 1 Pass + 人類簽核前）
- Docker / K8s（MVP 不做）
- 保證獲利或替代 Pilot gate
- **全能單 agent** tune 全表

## Dependencies & blockers

| 項目                           | 狀態                                                            |
| ------------------------------ | --------------------------------------------------------------- |
| tick_cache 2026-01～05         | 就緒（tick: 1月21 / 2月14 / 3月22 / 4月20 / 5月20；合計 97 日） |
| `param_sweep` / `backtest` CLI | 就緒                                                            |
| UAT Phase 1                    | 進行中 — **不阻塞** 本 ft                                       |
| Agent 編制表                   | [`AGENT_ROSTER.md`](AGENT_ROSTER.md)                            |

## Phases

### Phase 0 — 開 ft（文件）✅

- [x] SPEC、PLAN、AGENT_ROSTER
- [x] `workspaces/agent-conservative`、`agent-execution` + `BRIEF.md`
- [x] features README、DOC_MAP、CHANGELOG

### Phase 1 — Workspace 就緒

**人類 / 協調 agent**：

- [x] `workspaces/_template/`、`DATA_SPLIT.md`
- [x] MVP 兩位：`agent-conservative`、`agent-execution`（各含 `config/`、`logs/`、`reports/`、`grid.json`、`BRIEF.md`、`analysis.md`）
- [x] 擴充：`agent-risk-exit`、`agent-regime`（同上結構；對照 ROSTER §4–§5）
- [ ] `cache_audit` PASS、`determinism_check` PASS

**每位調參 agent 開工前**（自檢）：

- [ ] 已讀 ROSTER 中**自己的 §**
- [ ] 已載入 `senior-trading-professional.md`
- [ ] 確認未改 `apps/trading-app/config/config.yaml`
- [ ] 對 `grid.json` **每個 key** 跑 `overlay_smoke`（KPI 須改變，或執行/計時類 key 須通過 overlay 讀回驗證；見 `overlay_smoke.OVERLAY_SMOKE_KPI_OPTIONAL_KEYS`）

```bash
source .venv/bin/activate
export PYTHONPATH=apps/trading-app/src
cd apps/trading-app/src
python -m storage.cache_audit --code TMFR1
python -m sweep.determinism_check --date 2026-01-02 --mode hash
# 範例：確認 min_atr_threshold 會改變回測 KPI
python -m sweep.overlay_smoke --key min_atr_threshold --values 22 36 --date 2026-03-02
# 範例：pending_timeout_sec 等執行類 key — overlay 讀回即可（單日 KPI 可能不變）
python -m sweep.overlay_smoke --key pending_timeout_sec --values 30 120 --date 2026-03-02
```

### Phase 2 — Baseline（各 agent 獨立）

**目的**：在**預設參數**下建立 valid（2026-04）基線，供 sweep 對照。
**執行者**：各 agent 自己（或人類代跑，但 `analysis.md` 仍由該 agent 撰寫）。

```bash
export MONOREPO_ROOT="$(git rev-parse --show-toplevel)"
export AGENT=agent-conservative   # 或 agent-execution
export CONFIG_PATH="$MONOREPO_ROOT/workspaces/$AGENT/config/config.yaml"
export LOG_FILE="$MONOREPO_ROOT/workspaces/$AGENT/logs/baseline_valid.log"
export PYTHONPATH="$MONOREPO_ROOT/apps/trading-app/src"

cd "$MONOREPO_ROOT/apps/trading-app/src"
python -m backtest \
  --dates-from-cache \
  --cache-dir "$MONOREPO_ROOT/tick_cache" \
  --from-date 2026-04-01 \
  --to-date 2026-04-30 \
  --report \
  --log-file "$LOG_FILE"
```

**交易員產出（MUST）**：將 `reports/*.json` KPI 填入 `analysis.md` §Baseline，並用 **一句話**評論基線是否值得進入 sweep（樣本量、秒停損、MDD）。

Checklist：

- [ ] `agent-conservative` baseline 完成 + `analysis.md` §Baseline
- [ ] `agent-execution` baseline 完成 + `analysis.md` §Baseline

### Phase 3 — Sweep 競賽（各 agent 獨立）

**目的**：在**各自允許的 grid** 內搜尋；valid 區間排名。
**SSOT**：`grid.json` → `sweep_result.jsonl` → `analysis.md`（禁止手改 config 繞過 sweep）。

#### 3.1 設計 grid（交易員工作）

依 ROSTER 你的 §「允許 tune 的 keys」編輯 `workspaces/<slug>/grid.json`，並在 `analysis.md` §角色與假說 寫明：

- 要證明/否證什麼
- 為何選這些範圍（市況、流動性、風控）
- 預期 trade-off

範例見各 workspace 內既有 `grid.json`。

#### 3.2 執行 sweep（工程）

從 **tick_cache 實際檔名** 解析交易日（勿用含週末的曆日 generator）：

```bash
cd "$MONOREPO_ROOT"
export PYTHONPATH=apps/trading-app/src
export CONFIG_PATH="$MONOREPO_ROOT/workspaces/$AGENT/config/config.yaml"
python - <<'PY'
import json
from pathlib import Path
from storage.tick_loader import resolve_cli_tick_cache_dates
from sweep.holdout_guard import assert_dates_unsealed
from sweep.param_sweep import sweep

root = Path(".").resolve()
agent = "agent-conservative"  # 改成你的 slug
grid = json.loads((root / "workspaces" / agent / "grid.json").read_text())
cache = root / "tick_cache"

train = resolve_cli_tick_cache_dates(
    explicit=None, from_cache=True, code="TMFR1", cache_dir=cache,
    from_date="2026-01-01", to_date="2026-03-31",
)
valid = resolve_cli_tick_cache_dates(
    explicit=None, from_cache=True, code="TMFR1", cache_dir=cache,
    from_date="2026-04-01", to_date="2026-04-30",
)
assert_dates_unsealed(train + valid)  # 2026-05 holdout 封印；Phase 4 才設 FT003_HOLDOUT_UNSEAL=1
rows = sweep(grid, train, valid, code="TMFR1", cache_dir=cache,
             output_path=root / "workspaces" / agent / "sweep_result.jsonl")
print("days train/valid:", len(train), len(valid))
print("top valid_score:", rows[0]["valid_score"] if rows else None)
print("top params:", rows[0]["params"] if rows else None)
PY
```

#### 3.3 解讀與 analysis（交易員工作）

1. 讀 `sweep_result.jsonl` Top-3 + 最差組合
2. 完成 `analysis.md` **五段式**（ROSTER §1.5；含 SHARED_ASSUMPTIONS vX 合規聲明）
3. 自評 `train_valid_divergence` 與 overfitting

Checklist：

- [ ] `agent-conservative`：`sweep_result.jsonl` + `analysis.md` 五段式
- [ ] `agent-execution`：同上

### Phase 3.4 — 交叉審核（MVP 必做，**leaderboard 之前**）

**目的**：降低 tuning agent 自我合理化；檢查跨 agent 假設矛盾。  
**時序**：`analysis.md` 完成後 **立即** 執行；**不得** 在未完成 peer_review 前 append leaderboard。

**模板**：[`workspaces/_template/peer_review.md`](../../../workspaces/_template/peer_review.md)（ROSTER §1.6）

| 審核者               | 產出                                |
| -------------------- | ----------------------------------- |
| `agent-conservative` | `peer_review_agent-execution.md`    |
| `agent-execution`    | `peer_review_agent-conservative.md` |

Checklist：

- [ ] `agent-conservative/peer_review_agent-execution.md`
- [ ] `agent-execution/peer_review_agent-conservative.md`
- [ ] （擴充）`agent-risk-exit/peer_review_agent-regime.md`
- [ ] （擴充）`agent-regime/peer_review_agent-risk-exit.md`
- [ ] 雙方 `analysis.md` 底部 Phase 3.4 checklist 已勾；質疑已回覆（若有）

### Phase 3.5 — Leaderboard（peer_review 完成後）

1. Append `workspaces/leaderboard.jsonl`（格式 ROSTER §6）

Checklist：

- [ ] `agent-conservative` leaderboard 一行
- [ ] `agent-execution` leaderboard 一行
- [ ] （擴充）`agent-risk-exit`、`agent-regime` 各一行

**禁止**：在 Phase 3 查看或討論 2026-05 holdout 結果。

### Phase 4 — Holdout 解封與選舉（人類觸發 + 獨立裁判）

**僅人類宣布解封 holdout 後**執行（`export FT003_HOLDOUT_UNSEAL=1`）：

1. [ ] 對 leaderboard valid 冠軍（+ 人類指定亞軍）跑 **2026-05** 一次 backtest
2. [ ] Tuning agent（或人類）撰寫 `workspaces/election_report.md`（模板 [`_template/election_report.md`](../../../workspaces/_template/election_report.md)；含 valid vs holdout、overfit 判定）
3. [ ] **新開獨立 AI 對話**（零 Phase 3 上下文）執行 **agent-election-judge**（ROSTER §8）→ `workspaces/judge_opinion.md`
   - **首選 Claude 4.8**；fallback 見 ROSTER §8.2
4. [ ] 人類填寫 `election_report.md` **§5 人類最終決策記錄**（採納 / 部分採納 / 推翻 judge + 理由）；可參考 `judge_opinion.md` 與 `peer_review_*.md`
5. [ ] 通過 → `elected_config.yaml`；否則 `status: overfit_suspect`

### Phase 5 — UAT Phase 1 Pass 後套用（人類）

- [ ] UAT Phase 1 Pass
- [ ] 人類審閱 `election_report.md` + `judge_opinion.md`
- [ ] 可選：`compare_fill_audits`
- [ ] 合併至 UAT config（單次 PR）

### Phase 6 — 長歷史穩健性驗證（Post-MVP，2022+）

> **定位**：在 **Phase 0～5（2026 五個月競賽）完成後** 才開工。  
> **目的**：在已有 `elected_config`（或 documented 拒絕）之後，多一道 **穩健性關卡** — 不是「補完 2022 就更有信心上線」。  
> **產物**：`robustness_report.md`（各 fold 表 + 人工 KPI），**不是**第二個 `leaderboard.jsonl`。  
> **SSOT**：本節；fold 日期細節待 `workspaces/DATA_SPLIT.md` 擴充（Phase 6 啟動時）。

#### 啟動門檻（Gate — MUST）

| 條件 | 動作 |
|------|------|
| MVP **Phase 4 holdout 已跑完** 且 **非** `overfit_suspect` | 可開 **P1** 補檔與 Phase 6 pilot |
| MVP holdout **崩潰** / `overfit_suspect` | 長歷史僅作**診斷**（探索性回測）；**不跑**第二輪 grid sweep |
| Phase 6 pilot 通過（見下「縮 scope 第一版」） | 人類批准後才擴 fold / 補 2022 |

#### 與現有 MVP 的關係

| 問題 | MVP（Phase 3～4） | Phase 6 |
|------|-------------------|---------|
| 選參依據 | 2026 Q1 train + **4 月 valid** + **5 月 holdout 一次** | 多段 rolling valid + **Phase 6 封印 holdout 一次** |
| 能否調 grid | 每 agent **一輪** sweep（SPEC §4.4） | **固定 grid** 跑完所有 fold 後才可申請第二輪 |
| 探索性全段回測 | 禁止用於 leaderboard | 允許診斷，**禁止**用全段結果選參 |
| 對 Pilot 意義 | 產出 `elected_config` 候選 | **不能**跳過 UAT fill + qty=1 對帳 |

#### 四個會卡住的點（MUST 讀）

**① TMFR1 2022 可能不存在或不可比**

- 微台若 2022 無連續資料 → 改 **MXFR1/TXFR1**，或僅做**邏輯驗證**（摩擦/點值分開，見 SHARED_ASSUMPTIONS §1）。
- **交易員結論**：長歷史驗的是「策略邏輯 + 參數敏感度」，不是「微台 2026 參數在 2022 複製貼上」。
- 若商品不同，Phase 6 產物標為 **「邏輯穩健性報告」** — **不得**直接當 `elected_config` v2 上微台。

**② 算力與時間 — 必須用雲端盤後 / overnight**

粗算（以現行 bulk sweep 節奏：一組 combo ≈ train 54d + valid 20d ≈ **4 分鐘**）：

| 工作負載 | 粗估 |
|----------|------|
| Phase 6 全量（例：4 fold × 9 combo × ~310 日/fold） | 單 agent **~15–25 小時** |
| MVP 兩位 agent **串行** | **~1–2 個盤後夜** |

- **MUST**：Phase 6 批次跑在 **GCE（或等同雲端 VM）** — 08:30–14:00 留給 UAT live；本機僅監看 log / 收結果。
- **MUST**：有 `ft003_walkforward`（或批次腳本）；禁止純手動 36+ 次 backtest（易抄錯日期、漏 `holdout_guard`）。
- 排程：[`ops/HYBRID_DEPLOY.md`](../../ops/HYBRID_DEPLOY.md) — rsync `tick_cache` 上雲一次；跑完 rsync `robustness_report.md` + fold 產物回地端。

**③ 歷史 tick 補檔是 P1 真正瓶頸**

- `backfilldata date` 逐日補 3–4 年：收盤後跑、**勿與 live 同時 login** — 工程可行，**營運慢**。
- **不要**一次追求 2022→2025 全滿。啟動時先定：最少幾個 fold、補到哪一年。
- **建議**：先 **2024–2025 兩年、2–3 fold** 做 **Phase 6 pilot**；通過再決定是否 worth 補 2022。

**④ MVP 冠軍 vs Phase 6 v2 — 治理決策樹**

| 情況 | 決策 |
|------|------|
| MVP 冠軍在 **≥3/4 fold** 仍 Top-3 | **強化信心**；可維持 `elected_config` **v1** |
| 跨 fold 冠軍 **≠** MVP 冠軍 | v2 **僅候選**；須再跑 **Phase 6 封印 holdout 一次**（或人類指定新封印段） |
| 想用 fold 結果直接取代 MVP 2026-05 holdout | **禁止** — 否則變成「用更長樣本偷偷再 tune 一輪」 |

#### 實務優先順序（交易員視角）

| 優先 | 動作 | 產出 | 狀態 |
|------|------|------|------|
| **P0** | 完成 Phase 3 sweep + Phase 4 holdout（2026-05） | `elected_config.yaml` 或 `overfit_suspect` | 進行中 |
| **P1** | 補齊歷史 `tick_cache`（tick + kbars）；`cache_audit` 無 FAIL | 可信多年樣本 | 待做（**Gate 後**） |
| **P2** | 設計 rolling fold；寫入 `DATA_SPLIT.md` | fold SSOT | 待做 |
| **P3** | **固定 grid**、**雲端**跑完所有 fold | `robustness_report.md` | 待做 |
| **P4** | 依決策樹判定 v1 / v2 候選 | 人類簽核 | 待做 |
| **P5** | UAT `compare_fill_audits` | 執行校準 | 待做 |
| **P5.5** | **Phase 6.5** Shadow/Paper ≥2–4 週 + fill 對照 | `shadow_report` / 報告 §11 | 待做（**Phase 6 後**） |
| **P6** | Pilot qty=1 + 帳戶對帳 | Live gate | 見 [`uat/APP.md`](../../uat/APP.md) |

> **現行 MVP sweep**：valid 全負只代表「此 grid 在 2026 Q2 不賺」，**不影響** Phase 6 設計是否正確。

#### 縮 scope 第一版（Phase 6 pilot）

在擴到 4 fold + 2022 之前：

- [ ] **2–3 fold** + **1 年** Phase 6 holdout（封印）
- [ ] 驗證流程、雲端批次、報告模板
- [ ] pilot 通過 → 人類批准擴 scope

#### P1 — 資料準備

1. **確認商品年限**（見 ①）。
2. **補檔**（收盤後；勿與 live 同時 login）：

```bash
cd apps/trading-app/src
python -m backfilldata date YYYY-MM-DD
python -m storage.cache_audit --code TMFR1
python -m storage.cache_repair --code TMFR1 --fix   # 若有 FAIL
```

3. 每年須同時有 `{code}_{date}.csv` 與 `{code}_kbars_{date}.csv`。

#### P2 — Rolling walk-forward（建議架構 — **殘酷版**）

> **禁止**只做「一次 train → 一次 valid」就宣稱穩健。Phase 6 **MUST** 多段滾動 re-train + re-validate。

```text
例 A（季滾，pilot 最小）：12 個月 train + 3 個月 valid，每季往前滾

2022-01～2022-12  train  →  2023-Q1  valid   (fold 1)
2022-04～2023-03  train  →  2023-Q2  valid   (fold 2)
…
最後封印：例如 2025 全年  →  Phase 6 holdout（僅跑一次）

例 B（月滾，完整版 — 更嚴）：每月 re-train 視窗 + 下月 valid（或 rolling 1M OOS）
→ fold 數 ↑、算力 ↑；pilot 通過後人類批准才開
```

- **排名**：各 fold `valid_score`（**淨摩擦** `friction.enabled: true`，見 SHARED_ASSUMPTIONS §3.1）；冠軍 = 跨 fold **平均/中位排名** 最佳。
- **撮合假設**：回測仍用 MockBroker + 固定 `ioc_slippage_points` tier；**不得**在 Phase 6 關掉摩擦。滑價 tier 須與 workspace config 一致並寫入 `robustness_report.md` §1。
- **人工必看 KPI**：`expectancy_net`、`sharpe_net`、`quick_stop_loss_rate`、`max_drawdown_points`（淨）、`trade_count`/月、各年 net PnL 分布。
- **禁止**：封印前年全當 train 挑最佳；看完 fold 再改 grid（須人類批准新一輪）。

##### Walk-forward Gate 通過條件（MUST — 人類簽核門檻）

Pilot 啟動前，人類在 `robustness_report.md` §1 **簽核數值**（勿用 AI 自訂寬鬆門檻）。建議起點（可調嚴、不可調鬆而不記錄）：

| 條件 | 建議檢查（每 fold **與** 跨 fold 彙總） | 未過 → |
|------|----------------------------------------|--------|
| Net Sharpe | `sharpe_net` **>** 簽核值 X（例：0 或 0.3） | **FAIL** — 不進 v2 / 不宣稱穩健 |
| Net MDD | `max_drawdown_points` **<** 簽核值 Y（點數；依 qty=1 資本假設） | **FAIL** |
| 交易頻率穩定 | 各 fold `trade_count`/月 變異係數 **<** 簽核值；無「某月 0 筆、某月暴增」 | **WARN/FAIL**（人類裁定） |
| 淨期望 | 跨 fold **中位** `expectancy_net` **≥** 0（摩擦已扣） | 未過則僅診斷，不得上線敘事 |
| QSL | `quick_stop_loss_rate` 不劣於 MVP baseline 簽核上限 | 未過 → 執行/出場假設重審 |

**殘酷原則**：任一 fold 觸發 **FAIL** → 整體 Phase 6 **不得**標 `robustness_pass`；僅能 `diagnostic_only` 或重跑固定 grid（新 run_id，不得偷改 holdout）。

#### P2b — 穩健性深度檢查（`robustness_report.md` MUST）

模板 §7–§10；**固定 params**（MVP 冠軍或跨 fold 冠軍）上執行，**禁止**用這些檢查結果再 tune grid：

| 檢查 | 做法 | 通過直覺 |
|------|------|----------|
| **參數擾動** | 各連續參數 **±10–20%**（或 grid 步長一檔）重跑 valid 區間 | `valid_score` / `expectancy_net` 衰退在簽核範圍內；非「尖峰」單點 |
| **市況子樣本** | 依 ATR / 趨勢強度切分：高波、低波、趨勢、震盪（定義寫入報告） | 無單一市況獨撐全部淨利 |
| **壓力情境** | 歷史或合成：flash 跳空、連續停損週、低量日（流動性枯竭 proxy） | MDD / QSL 在可接受範圍；無「理論上會爆倉」盲點 |
| **策略相關性** | 與**其他已上線或 paper 策略**日收益相關係數 | 避免同因子同向暴倉（ρ 過高須人類說明分散） |

#### Phase 6.5 — Shadow / Paper Live Realism Gate（Post-Phase 6，**不可只在 backtest 收工**）

> **命名**：此為 **FT-003 Phase 6.5**；與 [`uat/APP.md`](../../uat/APP.md)「UAT Phase 6（切 CA）」不同層級。

| 項目 | MUST |
|------|------|
| 形式 | **真實即時報價** + **模擬下單**（Shioaji 模擬 API）；`max_position_qty: 1` **硬限制**不變 |
| 最短週期 | **≥ 2–4 週** 完整交易日（含不同市況） |
| Fill 對照 | **強制** `compare_fill_audits`（或同等工具）：backtest replay fill vs paper/shadow fill |
| 產物 | `shadow_report.md`（或 `robustness_report.md` §11）；偏差摘要：滑價、miss、延遲、部分成交 |
| Gate | paper 淨期望與回測差異在簽核範圍；否則 **調執行假設**，不得直接 live |

Phase 6 backtest 通過 **≠** Pilot 候選；**Phase 6 + 6.5 + UAT fill 校準** 才構成 live 前真實性鏈。

#### 風險控管與運維（Phase 6 / 6.5 MUST — 交易員視角）

| 項目 | 要求 | SSOT / 現況 |
|------|------|-------------|
| **Kill switch / 緊急平倉** | 演練：HALT、`block_new_entry`、市價收斂平倉、日切恢復 | [`ops/LIVE_SAFETY.md`](../../ops/LIVE_SAFETY.md)、engine P0-5 |
| **單口硬上限** | `max_position_qty: 1`；entry 不得以 stale flat 重複下單 | config + engine 已落地 |
| **每日 / 每週報告** | PnL（net）、MDD、trade frequency、異常單（CRITICAL / HALT） | `reports/day*.json`、DAILY_SUMMARY；Phase 3 起週報 |
| **券商對帳** | 自動或半自動 reconciliation（部位、日損益） | UAT Phase 3 `broker_reconciliation.csv`；[`uat/APP.md`](../../uat/APP.md) |
| **盤中禁長批** | 08:30–14:00 不跑 walk-forward / sweep | 本 PLAN §算力 |

#### P2 — 工程缺口

- [ ] `ft003_walkforward.py`（或 `ft003 --fold-spec`）— **雲端批次必備**
- [ ] `holdout_guard` 可設定封印區間
- [ ] `DATA_SPLIT.md` 長歷史 fold 表
- [ ] 模板 [`workspaces/_template/robustness_report.md`](../../../workspaces/_template/robustness_report.md)

#### 落實性自評

| 維度 | 判斷 |
|------|------|
| 方法論 | ✅ WFO + 封印 holdout |
| 文件 | ✅ 可執行、分工清楚 |
| 工程 | 🟡 MVP 工具夠用；Phase 6 需 walkforward + 可配置 holdout_guard（短期可試算表頂 **1 輪 pilot**） |
| 資料 | 🟡 TMFR1 年限 + 補檔工時是主風險 |
| 對 Pilot 價值 | 🟡 過 Phase 6 仍須 UAT fill；長歷史**不能**跳過 P6 CAL |

#### Phase 6 驗收

- [ ] Gate：MVP holdout 非 `overfit_suspect`
- [ ] `DATA_SPLIT.md` 含 fold + Phase 6 holdout（含月滾 / 季滾 spec）
- [ ] `cache_audit` 覆蓋 fold 內所有交易日
- [ ] 雲端跑完約定 fold 數（pilot：2–3；完整：≥4；完整版可含月滾）
- [ ] `workspaces/<agent>/robustness_report.md`（模板 §1–§10 全填）
- [ ] **Walk-forward Gate**：Sharpe / MDD / trade_count 穩定 — 人類簽核門檻已記錄且通過
- [ ] 決策樹：v1 維持 / v2 候選 + Phase 6 holdout 一次
- [ ] **Phase 6.5**：Shadow/Paper ≥2–4 週 + backtest vs paper fill 對照
- [ ] Kill switch / emergency flatten **演練證據**（log 或 checklist）
- [ ] 仍須 UAT fill 校準後才可宣稱 Pilot 候選

## 算力與排程

| 階段 | 環境 | 建議 |
| ---- | ---- | ---- |
| **MVP Phase 3 sweep** | 本機或 GCE 盤後 | 一次一個 agent；`sweep.lock` 單實例 |
| **Phase 6 walk-forward** | **GCE 盤後 / overnight（MUST）** | 08:30–14:00 **禁止**長批次；本機只監看 |
| UAT live | GCE asia-east1 | 與回測分時 |
| 並行 | MVP 兩位 agent **串行**；Phase 6 同理 |

**GCE Phase 6 最小 SOP**（盤後）：

1. `rsync` 地端 `tick_cache/` → VM（fold 所需日期子集即可）
2. `export PYTHONPATH=apps/trading-app/src`；`cd apps/trading-app/src`
3. 跑 `ft003_walkforward`（就緒後）或核准的批次腳本；`nohup` / `screen` 掛 overnight
4. 監看 `workspaces/<agent>/logs/sweep_progress.log`（JSONL）
5. 收工 `rsync` `robustness_report.md`、fold 彙總回地端

見 [`ops/HYBRID_DEPLOY.md`](../../ops/HYBRID_DEPLOY.md)、[`ops/LinuxOps.md`](../../ops/LinuxOps.md) §GCE。

## Acceptance

- [ ] MVP 兩位 agent Phase 3 + **3.4 peer_review** checklist 全勾
- [ ] `judge_opinion.md`（Phase 4）或 documented 跳過理由
- [ ] `elected_config.yaml` 或 documented 拒絕理由
- [ ] 未在 UAT Phase 1 前改 live config

## Risks

| 風險                  | 緩解                                                                            |
| --------------------- | ------------------------------------------------------------------------------- |
| AI 混淆角色           | ROSTER 固定 4 職；每人只寫自己 workspace                                        |
| Overfitting           | holdout 封印；交易員 MUST 寫自評                                                |
| 無窮演算 / token 燒光 | SPEC §4.4 上限；`param_sweep` combo≤36；holdout_guard 接線；每 agent 一輪 sweep |
| Grid 品質 / 假設分裂  | `SHARED_ASSUMPTIONS.md`；analysis §1 邊界理由 + 參數交互                        |
| 分析偏誤 / 過度樂觀   | Phase 3.4 peer_review；Phase 4 `agent-election-judge`（Claude 4.8）             |
| 回測樂觀              | senior-trading-professional 必提 SPEC §9                                        |
| Phase 6 商品不可比    | 跨商品標邏輯穩健性；不直接 v2 上微台（PLAN Phase 6 ①）                            |
| Phase 6 算力          | **MUST** GCE overnight；需 `ft003_walkforward`（PLAN Phase 6 ②）                  |
| 補檔工時              | 先 2024–2025 pilot；勿一次補滿 2022（PLAN Phase 6 ③）                             |
| v2 治理               | fold 冠軍 ≠ MVP → v2 須 Phase 6 holdout；禁止偷換 holdout（PLAN Phase 6 ④）       |
| WFO 門檻過鬆          | 人類簽核 Sharpe/MDD/trade_count；多段滾動非單次 WFO（PLAN P2 殘酷版）                 |
| 回測≠live             | Phase 6.5 Shadow/Paper + fill 對照 MUST（PLAN Phase 6.5）                           |
| 運維缺口              | kill switch 演練、日/週報、券商 reconciliation（PLAN 風險控管表）                     |

## 參考

- **Agent 編制（AI SSOT）**：[`AGENT_ROSTER.md`](AGENT_ROSTER.md)
- 契約：[`SPEC.md`](SPEC.md)
- **長歷史驗證（Post-MVP）**：[`PLAN.md`](PLAN.md) Phase 6
- 交易員身份：[`senior-trading-professional.md`](../../../prompts/roles/senior-trading-professional.md)
