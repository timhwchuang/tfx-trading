---
id: FT-022
slug: unified-strategy-loading
status: Landed
opened: 2026-07-01
owner: human+agent
target: UAT
phases: [0, 1, 2, 3, 4, 5]
blockers: []
---

# FT-022 — 統一策略載入（PLAN）

> **PLAN** = 怎麼交付 [`SPEC.md`](SPEC.md)。**一次 PR 只做一個 Phase**（Agent MUST）。

## Scope

- `strategy.name` config 解析 + `build_strategy_session()`
- `integrations/strategy_bootstrap.py`（GUDT backtest 離線 + live staged）
- `python -m backtest --config` / `python -m live` 統一接線
- FT baseline scripts 薄 wrapper
- Parity / reporting 合併（Phase 5）

## Out of scope

- 策略交易邏輯（FT-021）
- 盤中熱切換
- `StrategyDescriptor` / `strategy.params` dict / engine indicator 條件更新（§Follow-up）
- Kernel PnL = CF PnL

## Dependencies & blockers

| 項目 | 狀態 |
|------|------|
| FT-021 plugin + `load_named_strategy("gudt_route_a")` | 已存在 |
| `gudt_replay_planner.build_replay_plans_for_range` | 已存在 |
| `ft021_parity_check.py`（+1781 oracle） | 已存在 |
| Live staged 設計（SPEC §6） | 本 ft Phase 4 實作 |

## Phases

### Phase 0 — 開 ft（文件）

- [x] `docs/features/unified-strategy-loading/SPEC.md`
- [x] `docs/features/unified-strategy-loading/PLAN.md`
- [x] `docs/features/README.md` board FT-022
- [x] `DOC_MAP.md` §Features
- [x] `CHANGELOG.md` [Unreleased]
- [x] FT-021 SPEC §4 parity 數字同步 +1781

**Gate**：Phase 0 審閱 → Phase 1 開工。

### Phase 1 — Config + 策略工廠

**觸及檔案**：`config.py`、`core/runtime_config.py`、`integrations/engine_wiring.py`、`workspaces/*/config/config.yaml`（5）、`tests/test_engine_wiring.py`

- [x] `Settings.strategy_name` ← `strategy.get("name", "vwap_momentum")`
- [x] GUDT flat 鍵進 `Settings` + `TradingAppRuntimeConfig`
- [x] `build_strategy_session()`；`resolve_strategy_bootstrap()` 非 gudt → `{}`
- [x] 未知 name → `LookupError`
- [x] Workspace configs 補 `strategy.name`
- [x] `test_build_strategy_session_smoke`：五 entry point

**Agent prompt 模板**：

> 實作 FT-022 PLAN Phase 1 only。依 `docs/features/unified-strategy-loading/SPEC.md` §4–§5。  
> MUST NOT 實作 `strategy_bootstrap` GUDT 邏輯、不得改 `backtest/__main__.py` 或 `live/__main__.py`、不得改 `strategy_gudt_route_a` package。

### Phase 2 — GUDT backtest bootstrap

**觸及檔案**：`integrations/strategy_bootstrap.py`（新）、`integrations/gudt_replay_planner.py`（可選 re-export）、`tests/test_strategy_bootstrap.py`

- [x] `bootstrap_gudt_route_a(..., mode="backtest")` 抽取自 `ft021_run_baseline.py`
- [x] `resolve_strategy_bootstrap` 對 `gudt_route_a` 呼叫 bootstrap
- [x] skip / 非 GUDT 日：結構化 log（SPEC §6.3）
- [x] 可選寫出 `workspaces/<ws>/reports/day_plans.json`
- [x] 單元測試：plans 非空、skipped day、log 含 `skip_reason`

**Agent prompt 模板**：

> 實作 FT-022 PLAN Phase 2 only。backtest 離線 bootstrap；live 可先 stub `NotImplementedError` 或空 coordinator。  
> MUST NOT 改 backtest/live CLI。不得改 `GudtRouteAStrategy` 本體（除測試需要的 log hook）。

### Phase 3 — 統一 Backtest CLI

**觸及檔案**：`backtest/__main__.py`、`backtest/engine.py`（確認已注入 strategy 時不 fallback）、`scripts/ft021_run_baseline.py`、`tests/test_backtest_config_switch.py`

- [x] `--config PATH`（與 `CONFIG_PATH` 等價）
- [x] `load_config` → `build_strategy_session(..., mode="backtest")` → `BacktestEngine`
- [x] `ft021_run_baseline.py` → 薄 wrapper
- [x] `test_backtest_config_switch`：`CONFIG_PATH=mc-baseline` 載入 MC

**Agent prompt 模板**：

> 實作 FT-022 PLAN Phase 3 only。`python -m backtest --config` 走 `build_strategy_session`。  
> MUST NOT 實作 live wiring 或 reporting bundle。

### Phase 4 — Live wiring + staged bootstrap

**觸及檔案**：`live/__main__.py`、`integrations/strategy_bootstrap.py`、`integrations/gudt_live_bootstrap.py`（新，名稱可調）、`strategy_gudt_route_a/strategy.py`（`apply_intraday_plan`）、`docs/ops/LIVE_SAFETY.md`

- [x] `live/__main__.py`：`load_config` + `build_strategy_session(mode="live")`
- [x] `GudtLiveBootstrapCoordinator`：SPEC §6 狀態機；probe **不在** engine lock 內
- [x] `apply_intraday_plan(day, plan)`：mid-day 重載 events
- [x] `awaiting_atr` 節流 5 分鐘；`not_gudt_day` 當日停止 probe
- [x] LIVE_SAFETY 補 GUDT 前置：prior_close kbars、當日 kbars+tick、parity 全綠

**Agent prompt 模板**：

> 實作 FT-022 PLAN Phase 4 only。依 SPEC §6 狀態機與 skip_reason enum。  
> MUST NOT 改 backtest CLI。不得將 `simulation` 改 false。Live 只改 wiring + coordinator，不改 TradingEngine 核心 loop。

### Phase 5 — 測試、parity、reporting

**觸及檔案**：`scripts/ft021_parity_check.py`、`backtest/__main__.py`（emit 擴充）、`reporting/`（contributor 可選）、根 `SPEC.md` §4、`workspaces/gudt-baseline/ROUTE_A_UAT_STACK.md`

- [x] `ft021_parity_check` 經 `build_strategy_session` 路徑全綠
- [x] `--report` 可選 `research.json` / `parity.json`；`baseline.json` 過渡保留
- [x] `param_sweep` 讀 `strategy.name`（可選 5b）
- [x] 根 SPEC §4「已接線」；FT-022 → **Landed** checklist

**Agent prompt 模板**：

> 實作 FT-022 PLAN Phase 5 only。parity oracle：+1781 / extend=4 / flip=2（`ft021_parity_check.py`）。  
> MUST NOT 實作 Phase 6 `StrategyDescriptor`。

## Acceptance（關閉整張 ft）

- [ ] SPEC §10 Definition of Done 全勾
- [ ] `bash scripts/run-all-tests.sh` 全綠
- [ ] 統一 CLI 重現 GUDT baseline（見 Reproduce）

## Risks

| 風險 | 緩解 |
|------|------|
| Live 誤以為盤前可算完 plan | SPEC §6 staged；09:14 後 qualify |
| `config.py` 欄位膨脹 | Phase 1 flat；dict schema 留 Follow-up |
| 舊 FT scripts 破壞 | 薄 wrapper + 同一 helper；CI smoke |
| Mid-day `set_day_plans` 不重載 events | `apply_intraday_plan` 契約 + 測試 |
| Reporting vwap 欄位誤導 GUDT | kernel / research 分檔 |

## Reproduce

```bash
# Phase 3+ 目標 UX
cd apps/trading-app/src

# VWAP 預設
python -m backtest --dates-from-cache --report

# GUDT +1781 stack
CONFIG_PATH=../../../workspaces/gudt-route-a-baseline/config/config.yaml \
  python -m backtest --config ../../../workspaces/gudt-route-a-baseline/config/config.yaml \
  --dates-from-cache --from-date 2025-05-01 --to-date 2026-06-30 --report

# Parity（Phase 5）
PYTHONPATH=. python scripts/ft021_parity_check.py --from 2025-05-01 --to 2026-06-30
```

## Follow-up — Phase 6 modularity（另開 ft，blocked_by: FT-022 Landed）

> 來源：unified loading 架構診斷；**不得與 Phase 1–5 同 PR**。

- `StrategyDescriptor` + factory entry points
- `strategy.params` dict config（縮減 flat Settings）
- Engine `needs_indicators` 條件更新
- `BacktestReportBundle` + `StrategyReportContributor` registry
- `CounterfactualOracle` 策略無關 parity harness

詳見 cursor plan「Phase 6 — 策略模組化」；落地時開 **FT-023**（slug TBD）。

## Land checklist（併入 app SPEC 前必勾）

- [ ] 穩定契約已寫入 `apps/trading-app/SPEC.md` §Integration contracts
- [ ] `CHANGELOG.md` 已記行為/API 變更
- [ ] `docs/features/README.md` Status → **Landed**
- [ ] SPEC/PLAN frontmatter `status: Landed`
- [ ] 本 PLAN 所有 Phase checkbox 已勾

## 參考

- SPEC：[`SPEC.md`](SPEC.md)
- FT-021：[`../gudt-route-a/`](../gudt-route-a/)
- 原始架構 plan：cursor `unified_strategy_loading` plan（Phase 6 節）
