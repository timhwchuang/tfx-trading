---
id: FT-003
slug: ai-backtest-tuning
status: InProgress
opened: 2026-06-26
owner: human+agent
target: Pilot-prep
phases: [0, 1, 2, 3, 4, 5]
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

## 算力與排程

| 環境 | 建議                                  |
| ---- | ------------------------------------- |
| 本機 | 一次跑一個 agent 的 sweep             |
| GCE  | 08:30-14:00 留給 UAT；盤後跑 backtest |
| 並行 | MVP 兩位 **串行** 即可                |

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

## 參考

- **Agent 編制（AI SSOT）**：[`AGENT_ROSTER.md`](AGENT_ROSTER.md)
- 契約：[`SPEC.md`](SPEC.md)
- 交易員身份：[`senior-trading-professional.md`](../../../prompts/roles/senior-trading-professional.md)
