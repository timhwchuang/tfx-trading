---
id: FT-001
slug: audit-event-replay
status: Draft
opened: 2026-06-17
owner: human+agent
target: UAT-Pilot
phases: [0, 1, 2, 3, 4]
blockers: []
---

# FT-001 — Audit 事件回放（PLAN）

> 實作順序與驗收。SPEC 契約見 [`SPEC.md`](SPEC.md)。

## Scope

- 合格 audit：strategy 決策 + kernel 執行 + 成交的**可關聯**事件流
- `vwap-momentum` 為首個實作策略；契約設計可擴到其他 strategy plugin
- Episode 回放工具（`uat_report --episodes`）
- Determinism hash 擴充（不破壞現行 gate）

## Out of scope

- 逐 tick 全量 dump（用 `tick_cache`）
- 即時 dashboard / UI
- 改動 `simulation` / live 啟動流程
- 非 audit 的效能優化

## Dependencies & blockers

| 項目 | 狀態 |
|------|------|
| 現行 `SIGNAL_AUDIT` / `FILL_AUDIT` 契約 | 已有（app SPEC） |
| UAT tick 樣本 | 待人類 API；不擋 Phase 1–3 程式 |
| `trend_veto` 遷移 | Phase 4；過渡期 dual-parse |

## Phases

### Phase 0 — 開 ft（文件）

- [x] `docs/features/README.md`（feature board + SOP）
- [x] `docs/features/_template/{SPEC,PLAN}.md`
- [x] `docs/features/audit-event-replay/SPEC.md`
- [x] `docs/features/audit-event-replay/PLAN.md`
- [x] `docs/DOC_MAP.md` §Features
- [x] `docs/AGENTS.md` §3 ft 紀律
- [x] `CHANGELOG.md` [Unreleased]

### Phase 1 — Schema + 高價值缺口

**目標**：單 episode 可從 `momentum_armed` → entry SIGNAL → FILL 串起。

- [ ] `DecisionAudit` dataclass + `format_decision_audit()`（engine 或 app 層，SPEC 實作時定案）
- [ ] `VWAPMomentumStrategy._try_activate_momentum` → `DECISION_AUDIT` `momentum_armed` + `episode_id` 生成
- [ ] `build_exit_audit`  enrichment：`entry_price`, `hold_ticks`, `in_grace`, stop levels, `trailing_peak`
- [ ] `SignalAudit` optional 欄位：`episode_id`, `signal_id`, `elapsed_since_arm_sec`, `dist_vwap`
- [ ] `FillAudit` optional：`signal_id`；entry 加 `episode_id`
- [ ] 單元測試：strategy 發 `momentum_armed`；exit audit 新欄位

**主要檔案**：

- [`packages/trading-engine/src/trading_engine/core/audit/signal_audit.py`](../../../packages/trading-engine/src/trading_engine/core/audit/signal_audit.py)
- [`packages/strategies/vwap-momentum/src/strategy_vwap_momentum/strategy.py`](../../../packages/strategies/vwap-momentum/src/strategy_vwap_momentum/strategy.py)
- [`apps/trading-app/src/observability.py`](../../../apps/trading-app/src/observability.py)

### Phase 2 — Kernel EXEC + ID 貫穿

**目標**：pending cancel 出現在 timeline，不需 regex。

- [ ] Kernel 產生 `signal_id`（每個 `OrderSignal`）
- [ ] `EXEC_AUDIT`：`pending_armed`, `pending_cancelled`, `pending_timeout`, `position_sync`
- [ ] `TradingAppTelemetryPort` 轉發 EXEC（若 emitter 在 app 層）
- [ ] `episode_id` 從 armed 貫穿至 entry FILL
- [ ] 測試：mock pending cancel 產出 EXEC_AUDIT

**主要檔案**：

- [`packages/trading-engine/src/trading_engine/order_executor.py`](../../../packages/trading-engine/src/trading_engine/order_executor.py)
- [`apps/trading-app/src/integrations/telemetry_port.py`](../../../apps/trading-app/src/integrations/telemetry_port.py)

### Phase 3 — Reporting 回放工具

**目標**：`python -m reporting <log> --episodes` 輸出人類可讀 timeline。

- [ ] `uat_report.parse_decision_audit_line` / `parse_exec_audit_line`
- [ ] `build_episode_timeline(audits, fills, execs) -> list[Episode]`
- [ ] CLI `--episodes` / `--episode-id`
- [ ] `tests/reporting/test_episode_replay.py`
- [ ] `build_tuning_hints` 改用 episode funnel（減少 regex 依賴）

**主要檔案**：

- [`apps/trading-app/src/reporting/uat_report.py`](../../../apps/trading-app/src/reporting/uat_report.py)
- 可選新檔 `apps/trading-app/src/reporting/episode_replay.py`

### Phase 4 — 遷移、契約落地、關 ft

**目標**：雙真相消除；ft → **Landed**。

- [ ] `trend_veto` / `momentum_timeout` 遷至 `DECISION_AUDIT`
- [ ] `uat_report` / `trend_calibration` dual-parse 一版後移除 legacy 路徑
- [ ] `determinism_check` 納入 DECISION/EXEC
- [ ] 併入 [`apps/trading-app/SPEC.md`](../../../apps/trading-app/SPEC.md) §Integration contracts
- [ ] 更新 [`packages/strategies/vwap-momentum/SPEC.md`](../../../packages/strategies/vwap-momentum/SPEC.md) §7 指向新契約
- [ ] `CHANGELOG.md` 行為變更條目
- [ ] 執行 **Land checklist**（下節）

## Acceptance（關閉整張 ft）

- [ ] SPEC §9 Definition of Done 全勾
- [ ] `bash scripts/run-all-tests.sh` 全綠
- [ ] 至少 1 份合成 log fixture 通過 `--episodes` 快照測試

## Risks

| 風險 | 緩解 |
|------|------|
| Log 量暴增（pullback_candidate） | 每 episode 節流 1 筆 closest |
| determinism hash 漂移 | 新欄位 optional；schema_version；專用測試 |
| 雙真相（feature SPEC vs app SPEC） | Phase 4 強制併入；Landed 後 feature SPEC 僅留設計考古 |
| `SIGNAL_AUDIT` 語意過載 | 非 order 事件遷至 `DECISION_AUDIT` |

## Land checklist（併入 app SPEC 前必勾）

- [ ] [`apps/trading-app/SPEC.md`](../../../apps/trading-app/SPEC.md) §Integration contracts 已含 DECISION/EXEC 與新欄位表
- [ ] [`CHANGELOG.md`](../../../CHANGELOG.md) `trading-app` 已記 audit 契約變更
- [ ] [`docs/features/README.md`](../README.md) FT-001 Status → **Landed**
- [ ] 本檔 + SPEC frontmatter `status: Landed`
- [ ] 上方 Phase 1–4 checkbox 全勾

## 參考

- SPEC：[`SPEC.md`](SPEC.md)
- Feature board：[`../README.md`](../README.md)