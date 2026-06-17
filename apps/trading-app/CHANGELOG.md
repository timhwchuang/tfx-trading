# Changelog

All notable changes to `trading-app` are documented here.  
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).  
Versioning follows [SemVer](https://semver.org/) (0.x = API may still evolve).

## [Unreleased]

### Added / Changed (UAT to Pilot hardening)

- determinism_check.py 新增基本 CLI（`python -m sweep.determinism_check --date YYYY-MM-DD --mode hash --output ...`），支援 UAT 強制證據收集。
- UAT_CHECKLIST.md 大幅補強（v2）：
  - 執行環境統一說明 + 長期資料管理小節（TOP2 & TOP5）
  - 每個 Phase 強化 Evidence Collection + determinism CLI 用法
  - Phase 6 alerts 驗證具體可執行步驟（手動觸發 CRITICAL + 確認收到時間戳）（TOP3）
  - Phase 7 rollback 變成詳細可執行清單 + escalation matrix（TOP4）
  - Phase 5 可重現性命令範例 + 書面風險預案要求
- 所有改進直接對應上次 subagent review 的 TOP1~5（現階段可落地的部分已補進）。
- 強調從 monorepo 根執行 + git + determinism hash 作為強制紀律。

### Changed

- **重大重構**：`UAT_CHECKLIST.md` 改寫為**有時序性、可照表抄課**的完整 UAT→Pilot 循序指引。
  - 最上方新增「目前進度一目瞭然」表格（方便跨 AI session 追蹤）。
  - 改為 Phase 0 ~ Phase 7 的線性流程（Day 0 → Day 1 → 連續收集 → 指標驗證 → Gate 審核 → 上 CA → Pilot 執行）。
  - 把 MDD / Sharpe / Expectancy 明確放在 Phase 3 與 Phase 5 作為硬門檻。
  - 每個 Phase 都有明確的「完成條件 + 證據要求 + 建議命令」。
- BeforePilot.md 內容已完全整合，改為 redirect。
- 強化「專業交易員視角」的審慎態度（樣本穩定性、參數凍結、近期窗、零 Critical、書面審閱等）。

## [0.1.2] - 2026-06-17

### Added

- P4-13 `operations` config: reconnect warmup, disconnect limits, `atr_stale_multiplier`
- Cumulative MDD risk budget in `uat_report` / `performance_metrics` (`initial_capital_points`, `max_acceptable_mdd_points`)
- UPGRADE_RUNBOOK (now in ARCHIVE) — four-repo upgrade SOP (historical)

### Changed

- Pin `trading-engine@v0.2.2`, `strategy-vwap-momentum@v0.1.2`
- Docs sync: README, SPEC, UAT_CHECKLIST, Architecture, WeeklyStatus

[0.1.2]: https://github.com/timhwchuang/trading-app/releases/tag/v0.1.2

## [0.1.1] - 2026-06-16

### Changed

- Remove deprecated `theman_*` port / config aliases; use `trading_app_*` symbols only
- Alert prefix `[theman]` → `[trading-app]`
- Windows ops: `start-trading-app.ps1`, `register-task.ps1` default task `trading-app-vwap`
- Pin siblings: `trading-backtest@v0.1.1`, `strategy-vwap-momentum@v0.1.1`
- Docs sync: `TODO.md`, `WeeklyStatus.md`, `README.md`, `docs/*` ops paths

### Fixed

- Sweep tick helpers: `ReplayTick.close` as `str` (realistic CSV replay) — pairs with backtest `MockBroker` float coercion fix

[0.1.1]: https://github.com/timhwchuang/trading-app/releases/tag/v0.1.1

## [0.1.0] - 2026-06-16

First public release as **reference integrator app** (renamed from internal `theman`).

### Added

- `pyproject.toml`, `SPEC.md`, `LICENSE`, `.env.example`, `docs/RELEASE_CHECKLIST.md`
- `trading_app_engine_ports()` wiring for live, backtest, and tests
- `TradingAppTelemetryPort`, `TradingAppAlertPort`, `TradingAppArchivePort`, `TradingAppTrendRefresh`
- `reporting/` UAT log parser (`python -m reporting`)
- `storage/` tick/kbar archive + `sweep/` param research tooling
- CI: standalone clone via git-tagged sibling packages

### Changed

- Renamed from `theman` → `trading-app` (repo / docs / symbols)
- Dependencies: `trading-engine`, `trading-backtest`, `strategy-vwap-momentum` (no vendored kernel)
- Removed transitional re-export shims (`runtime/`, `strategy/`, `adapters/`, most of `core/`)
- App tests scoped to integration / storage / reporting / sweep (~30 tests)

### Notes

- **UAT-ready**, not Live-ready — see `docs/UAT_CHECKLIST.md`
- Pin siblings: `trading-engine@v0.2.0`, `trading-backtest@v0.1.0`, `strategy-vwap-momentum@v0.1.0`

[0.1.0]: https://github.com/timhwchuang/trading-app/releases/tag/v0.1.0