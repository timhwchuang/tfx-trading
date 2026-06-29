# 文件職責地圖（tfx-trading monorepo）

> **單一入口**：每份 active 文件一個真相來源。
> **分層**：**高階**（根 `SPEC.md`、`TODO`、`AGENTS`）描述 monorepo 整合；**低階**（各 package `SPEC.md`）描述該模組 API，**只連依賴、不連回根 SPEC**。

## 1. 專案進度（先看）

| 文件 | 職責 |
| ---- | ---- |
| [`TODO.md`](TODO.md) | 未完成項、blocker、Phase gate 摘要（含 **§P6-1-CAL** Live gate checklist） |
| [`WeeklyStatus.md`](WeeklyStatus.md) | 人類週報、Follow-up（**讀最上方最新一節**）；CAL-8 決策紀錄 |
| [`../CHANGELOG.md`](../CHANGELOG.md) | 全 monorepo 版本歷史（按 package 分區） |

## 2. 架構掌握

| 文件 | 職責 |
| ---- | ---- |
| [`../SPEC.md`](../SPEC.md) | Monorepo 整合 SPEC（路徑、依賴、安裝、§7 架構與資料流、新策略、發布 SOP） |
| [`../README.md`](../README.md) | Clone、setup、快速連結 |

### 模組 SPEC（各 package 真相）

| Package | SPEC |
| ------- | ---- |
| trading-engine | [`packages/trading-engine/SPEC.md`](../packages/trading-engine/SPEC.md) |
| trading-backtest | [`packages/trading-backtest/SPEC.md`](../packages/trading-backtest/SPEC.md) |
| vwap-momentum | [`packages/strategies/vwap-momentum/SPEC.md`](../packages/strategies/vwap-momentum/SPEC.md) |
| trading-app | [`apps/trading-app/SPEC.md`](../apps/trading-app/SPEC.md) |

## 3. 執行與驗收

| 文件 | 職責 |
| ---- | ---- |
| [`uat/APP.md`](uat/APP.md) | App 層 UAT→Pilot 循序清單（**Pilot Phase 5 SSOT**） |
| [`../uat_evidence/README.md`](../uat_evidence/README.md) | UAT 證據歸檔 SOP + 範本 |
| [`uat/KERNEL.md`](uat/KERNEL.md) | Engine 整合 UAT 驗收 |
| [`ops/LIVE_SAFETY.md`](ops/LIVE_SAFETY.md) | 實盤失敗情境與 kernel 行為 |
| [`ops/HYBRID_DEPLOY.md`](ops/HYBRID_DEPLOY.md) | 地雲雙管：GCE Live + 地端回測、GCE 規格 |
| [`ops/LinuxOps.md`](ops/LinuxOps.md) | Linux/GCE systemd、cron、地端研究 |
| [`ops/WindowsOps.md`](ops/WindowsOps.md) | Windows 排程、告警、路徑 |
| [`AGENTS.md`](AGENTS.md) | AI 安全護欄、Callback MUST NOT、Production Gate |

## 4. 研究與 Gate（策略 thesis）

| 主題 | 文件 |
| ---- | ---- |
| **Holdout 契約 v2**（train/valid/holdout、median、方向、**skew 厚尾 v2.2**） | [`HOLDOUT_CONTRACT_v2.md`](features/ai-backtest-tuning/HOLDOUT_CONTRACT_v2.md) |
| 資料切分 SSOT | [`workspaces/DATA_SPLIT.md`](../workspaces/DATA_SPLIT.md) |
| 回測宿主契約 | [`packages/trading-engine/SPEC.md`](../packages/trading-engine/SPEC.md) §12 |
| MockBroker / 回放 | [`packages/trading-backtest/SPEC.md`](../packages/trading-backtest/SPEC.md) §5–10 |
| Audit log、determinism、sweep | [`apps/trading-app/SPEC.md`](../apps/trading-app/SPEC.md) §Integration contracts |
| AI 回測調參、multi-agent 競賽 | **FT-003** → [`features/ai-backtest-tuning/`](features/ai-backtest-tuning/) · **[`ALPHA_RESEARCH_PLAYBOOK.md`](features/ai-backtest-tuning/ALPHA_RESEARCH_PLAYBOOK.md)**（Alpha 儀式） · **[`GATE_COVERAGE_PREFLIGHT.md`](features/ai-backtest-tuning/GATE_COVERAGE_PREFLIGHT.md)**（0-design Preflight） · **[`HOLDOUT_CONTRACT_v2.md`](features/ai-backtest-tuning/HOLDOUT_CONTRACT_v2.md)**（策略 thesis gate） · [`workspaces/THESIS_QUEUE.md`](../workspaces/THESIS_QUEUE.md) · [`workspaces/DATA_SPLIT.md`](../workspaces/DATA_SPLIT.md) · [`VOLATILITY_BASELINE.md`](../workspaces/VOLATILITY_BASELINE.md) · [`ENTRY_FUNNEL_METRICS.md`](features/ai-backtest-tuning/ENTRY_FUNNEL_METRICS.md) |
| 歷史 tick/kbar 快取補洞 | [`apps/trading-app/src/backfilldata/SPEC.md`](../apps/trading-app/src/backfilldata/SPEC.md) |
| tick_cache 品質稽核 / 修復 | [`workspaces/CACHE_AUDIT.md`](../workspaces/CACHE_AUDIT.md)（何時重跑）；`storage.cache_audit` / `storage.cache_repair` |

## 5. 考古（勿當現行流程）

| 路徑 | 說明 |
| ---- | ---- |
| [`ARCHIVE/`](ARCHIVE/) | 舊設計稿（DESIGN/STRATEGY）、BACKTEST_IMPLEMENTATION、RELEASE_CHECKLIST、四-repo 發布紀錄；[`ARCHIVE/specs/`](ARCHIVE/specs/) 為已併入 package SPEC 的舊 standalone 規格 |
| [`ARCHIVE/UPGRADE_RUNBOOK.md`](ARCHIVE/UPGRADE_RUNBOOK.md) | 已棄用 → 根 [`SPEC.md`](../SPEC.md) §5 |
| [`ARCHIVE/MONOREPO_MIGRATION_PLAN.md`](ARCHIVE/MONOREPO_MIGRATION_PLAN.md) | 四-repo → monorepo 遷移 checklist（已完成） |
| [`ARCHIVE/Architecture.md`](ARCHIVE/Architecture.md) | 已併入根 `SPEC.md` §7 |
| 舊 standalone git+ 安裝 | 僅供歷史；現行用 `scripts/setup-dev.sh` |

## 6. Features（跨模組 ft）

| ID | Slug | Status | 文件 |
| ---- | ---- | ------ | ---- |
| FT-001 | audit-event-replay | Landed | [SPEC](features/audit-event-replay/SPEC.md) · [PLAN](features/audit-event-replay/PLAN.md) · [REVIEW](features/audit-event-replay/REVIEW.md) |
| FT-002 | smc-structure-filter | **MVPClosed** | [SPEC §12](features/smc-structure-filter/SPEC.md) · CAL-8 **放棄** |
| FT-003 | ai-backtest-tuning | MVPClosed | [SPEC](features/ai-backtest-tuning/SPEC.md) · [PLAN](features/ai-backtest-tuning/PLAN.md) · [**ROSTER**](features/ai-backtest-tuning/AGENT_ROSTER.md) · [`election_report.md`](../workspaces/election_report.md) · [`workspaces/`](../workspaces/) |
| FT-004 | momentum-continuation | **MVPClosed** | [SPEC](features/momentum-continuation/SPEC.md) §8 · [PLAN](features/momentum-continuation/PLAN.md) · [`mc-baseline/`](../workspaces/mc-baseline/) |
| FT-005 | timeout-continuation | **MVPClosed** | [SPEC](features/timeout-continuation/SPEC.md) §8 · [PLAN](features/timeout-continuation/PLAN.md) · [`tc-baseline/`](../workspaces/tc-baseline/) |
| FT-006 | vwap-stretch-fade | **MVPClosed** | [SPEC §8](features/vwap-stretch-fade/SPEC.md) · [`gate_report`](../workspaces/vsf-baseline/gate_report.md) |
| FT-007 | momentum-exhaustion-reversal | MVPClosed | [SPEC §8](features/momentum-exhaustion-reversal/SPEC.md) · [`gate_report`](../workspaces/mer-baseline/gate_report.md) |
| FT-008 | short-breakout | MVPClosed | [SPEC §8](features/short-breakout/SPEC.md) · [`gate_report`](../workspaces/sb-baseline/gate_report.md) |
| FT-009 | opening-range-breakout | **MVPClosed** | [SPEC §8](features/opening-range-breakout/SPEC.md) · [`orb-baseline/`](../workspaces/orb-baseline/) |
| FT-010 | vwap-trend-pullback | **MVPClosed** | [SPEC §11](features/vwap-trend-pullback/SPEC.md) · [`vtp-baseline/`](../workspaces/vtp-baseline/) |
| FT-011 | session-confluence-breakout | **MVPClosed** | [SPEC §10](features/session-confluence-breakout/SPEC.md) · [`scb-baseline/`](../workspaces/scb-baseline/) |
| FT-012 | regime-vwap-stretch-fade | **MVPClosed** | [SPEC §8](features/regime-vwap-stretch-fade/SPEC.md) · [`rvsf-baseline/`](../workspaces/rvsf-baseline/) |
| FT-013 | supertrend-flip | **MVPClosed** | [SPEC](features/supertrend-flip/SPEC.md) · [`stf-baseline/`](../workspaces/stf-baseline/) |
| FT-014 | morning-vwap-hold-pullback | **MVPClosed** | [SPEC](features/morning-vwap-hold-pullback/SPEC.md) · [`mvhp_fingerprint_fail`](../workspaces/mvhp-baseline/gate_report.md) |
| FT-015 | fvg-retest-pullback | **MVPClosed** | [SPEC](features/fvg-retest-pullback/SPEC.md) · [`frp_fingerprint_fail`](../workspaces/fvg-baseline/gate_report.md) |
| FT-016 | gap-drive-continuation | **MVPClosed** | [SPEC](features/gap-drive-continuation/SPEC.md) · `gdc_fingerprint_pass_g1_fail` |
| FT-017 | compression-flow-attack | **MVPClosed** | [SPEC](features/compression-flow-attack/SPEC.md) · **`spec_anchor_mismatch`**（mislabel: `cfa_fingerprint_fail`） |
| FT-018 | gap-up-drive-trail | **MVPClosed** | [SPEC](features/gap-up-drive-trail/SPEC.md) · [`gate_report`](../workspaces/gudt-baseline/gate_report.md) · P-011 train champion corpse |
| FT-019 | sweep-fvg-breakout-trail | **Draft** | [SPEC](features/sweep-fvg-breakout-trail/SPEC.md) · [PLAN](features/sweep-fvg-breakout-trail/PLAN.md) · P-012 |
| FT-020 | bear-streak-flip-long | **Draft** | [SPEC](features/bear-streak-flip-long/SPEC.md) · [PLAN](features/bear-streak-flip-long/PLAN.md) · P-013 |

索引與開 ft SOP：[`features/README.md`](features/README.md)。**Draft / InProgress** 期間以 feature SPEC 為設計真相；**Landed** 後併入 app SPEC §Integration contracts。

## 7. AI 角色與 Grok skills

| 路徑 | 職責 |
| ---- | ---- |
| [`.grok/skills/senior-trading-professional/SKILL.md`](../.grok/skills/senior-trading-professional/SKILL.md) | Grok project skill；slash **`/senior-trading-professional`** |
| [`.grok/skills/audit-event-replay/SKILL.md`](../.grok/skills/audit-event-replay/SKILL.md) | Grok project skill；slash **`/audit-event-replay`**（FT-001 實作/審閱） |
| [`prompts/roles/senior-trading-professional.md`](../prompts/roles/senior-trading-professional.md) | 資深交易人員 role 正文（MUST NOT、workflow、Phase 5 checklist） |
| [`prompts/roles/references/txf-gates.md`](../prompts/roles/references/txf-gates.md) | UAT / Pilot / Live gate 速查（交易視角） |

**分層**：`docs/AGENTS.md` §2 安全護欄 > role MUST NOT > `txf-gates.md`。本 role 用於策略可行性、Pilot Go/No-Go、sweep 解讀；**不**取代工程 Agent 改 code。

## 常見混淆

| 問題 | 答案 |
| ---- | ---- |
| 我現在該做什麼？ | **`docs/TODO.md`** + WeeklyStatus 最新一節 |
| 架構與邊界？ | 根 **`SPEC.md`** §7 + 相關 package `SPEC.md` |
| 怎麼裝依賴？ | **`bash scripts/setup-dev.sh`** |
| UAT 跑什麼？ | **`docs/uat/KERNEL.md`** + **`docs/uat/APP.md`** |
| 版本變更寫哪？ | 根 **`CHANGELOG.md`**（對應 package 區塊） |
| 加新策略？ | `packages/strategies/<name>/` + 根 [`SPEC.md`](../SPEC.md) §4 |
| 交易視角 / Pilot gate？ | **`/senior-trading-professional`** → [`prompts/roles/`](../prompts/roles/) |
| 規劃中能力 / 開 ft？ | [`features/README.md`](features/README.md) |
| Audit 事件回放？ | **FT-001** → [`features/audit-event-replay/`](features/audit-event-replay/) |
| SMC 結構濾網？ | **FT-002** → [`features/smc-structure-filter/`](features/smc-structure-filter/) |
| 回測調參 / AI 競賽？ | **FT-003** → [ROSTER](features/ai-backtest-tuning/AGENT_ROSTER.md)（編制表）· [SPEC](features/ai-backtest-tuning/SPEC.md) · 角色 [`senior-trading-professional`](../prompts/roles/senior-trading-professional.md) |
| 補歷史 tick/kbar 快取？ | `python -m backfilldata date …` → [`backfilldata/SPEC.md`](../apps/trading-app/src/backfilldata/SPEC.md) |
| 回測前 tick×kbar 品質？ | `python -m storage.cache_audit --code TMFR1`；修復 `python -m storage.cache_repair --fix` → [`apps/trading-app/SPEC.md`](../apps/trading-app/SPEC.md) §Tick cache audit |