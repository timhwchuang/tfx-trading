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

## 4. 研究（Gen-2 · 極簡）

| 主題 | 文件 |
| ---- | ---- |
| **研究 SSOT** | [`workspaces/RESEARCH_CHARTER_v2.md`](../workspaces/RESEARCH_CHARTER_v2.md) · [`RESEARCH_LOG.md`](../workspaces/RESEARCH_LOG.md) |
| 資料切分（防偷看） | [`workspaces/DATA_SPLIT.md`](../workspaces/DATA_SPLIT.md) |
| SessionBarCache / kbar | [`apps/trading-app/src/storage/SPEC.md`](../apps/trading-app/src/storage/SPEC.md) |
| 回測宿主 / MockBroker | package SPECs（engine · backtest） |
| tick 補洞 / cache 稽核 | [`backfilldata/SPEC`](../apps/trading-app/src/backfilldata/SPEC.md) · [`CACHE_AUDIT.md`](../workspaces/CACHE_AUDIT.md) |

新研究：**Brief + SessionBars + 一頁報告**。勿載入 tick-era Playbook / Queue。

## 5. 考古（勿當現行流程）

| 路徑 | 說明 |
| ---- | ---- |
| [`ARCHIVE/research-2026-h1/`](ARCHIVE/research-2026-h1/INDEX.md) | **FT-002～020 研究層冷封存** + 墓誌銘；features 原文在 `features/` 子樹 |
| [`../workspaces/_archive/`](../workspaces/_archive/README.md) | baselines · OSF/June · FT-003 競賽 · CORPSE/Queue |
| [`ARCHIVE/`](ARCHIVE/) | 更早設計稿 / monorepo 遷移 / 舊 checklist |

## 6. Features（現行 only）

| ID | Status | 文件 |
| ---- | ------ | ---- |
| FT-001 audit-event-replay | Landed | [features/](features/audit-event-replay/) |
| FT-021 gudt-route-a | UAT | [SPEC](features/gudt-route-a/SPEC.md) · [baseline](../workspaces/gudt-route-a-baseline/) |
| FT-022 unified-strategy-loading | Landed | [SPEC](features/unified-strategy-loading/SPEC.md) |
| FT-023 gudt-wash-beta | UAT | [SPEC](features/gudt-wash-beta/SPEC.md) · [baseline](../workspaces/gudt-wash-beta-baseline/) |

索引：[`features/README.md`](features/README.md)。Archived ft 見 §5。

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
| 新研究怎麼開？ | [`RESEARCH_CHARTER_v2.md`](../workspaces/RESEARCH_CHARTER_v2.md) · [`features/README.md`](features/README.md) 三行規則 |
| Audit 事件回放？ | **FT-001** → [`features/audit-event-replay/`](features/audit-event-replay/) |
| 現行策略 UAT？ | **GUDT** FT-021/023 · `workspaces/gudt-*-baseline/` |
| 舊 FT / Playbook / 競賽？ | **封存** → [`ARCHIVE/research-2026-h1/`](ARCHIVE/research-2026-h1/INDEX.md) · [`workspaces/_archive/`](../workspaces/_archive/) |
| 補歷史 tick/kbar 快取？ | `python -m backfilldata date …` → [`backfilldata/SPEC.md`](../apps/trading-app/src/backfilldata/SPEC.md) |
| 回測前 tick×kbar 品質？ | `python -m storage.cache_audit --code TMFR1` → [`CACHE_AUDIT.md`](../workspaces/CACHE_AUDIT.md) |
