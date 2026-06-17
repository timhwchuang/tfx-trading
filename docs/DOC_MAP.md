# 文件職責地圖（tfx-trading monorepo）

> **原則**：每份文件一個真相來源。本檔為**全 repo 索引**；各 package 細規格見各自 `SPEC.md`。

## 頂層（先看這裡）

| 文件 | 讀者 | 職責 |
| ---- | ---- | ---- |
| [`SPEC.md`](../SPEC.md) | 整合者 | **Monorepo 整合 SPEC** — 路徑、依賴、安裝、模組入口 |
| [`docs/Architecture.md`](Architecture.md) | 開發者 | **架構** — 模組邊界、資料流、策略載入 |
| [`README.md`](../README.md) | 所有人 | Clone、setup、快速連結 |
| [`monorepo/SPEC.md`](../monorepo/SPEC.md) | 維護者 | 目錄慣例、新策略 scaffold、發布 SOP |
| [`apps/trading-app/AGENTS.md`](../apps/trading-app/AGENTS.md) | AI / 開發者 | 安全護欄、gate、開發紀律 |

## 路線圖與週報（app 層）

| 文件 | 職責 |
| ---- | ---- |
| [`apps/trading-app/TODO.md`](../apps/trading-app/TODO.md) | 未完成工作項、gate 摘要 |
| [`apps/trading-app/docs/WeeklyStatus.md`](../apps/trading-app/docs/WeeklyStatus.md) | 人類週報、Follow-up |

## UAT / 安全 / 運維

| 文件 | 路徑 |
| ---- | ---- |
| App UAT | [`apps/trading-app/docs/UAT_CHECKLIST.md`](../apps/trading-app/docs/UAT_CHECKLIST.md) |
| Kernel UAT | [`packages/trading-engine/docs/UAT_CHECKLIST.md`](../packages/trading-engine/docs/UAT_CHECKLIST.md) |
| LIVE_SAFETY | [`packages/trading-engine/docs/LIVE_SAFETY.md`](../packages/trading-engine/docs/LIVE_SAFETY.md) |
| BeforePilot | [`apps/trading-app/docs/BeforePilot.md`](../apps/trading-app/docs/BeforePilot.md) |
| WindowsOps | [`apps/trading-app/docs/WindowsOps.md`](../apps/trading-app/docs/WindowsOps.md) |

## Package SPEC（模組真相）

| Package | SPEC |
| ------- | ---- |
| trading-engine | [`packages/trading-engine/SPEC.md`](../packages/trading-engine/SPEC.md) |
| trading-backtest | [`packages/trading-backtest/SPEC.md`](../packages/trading-backtest/SPEC.md) |
| vwap-momentum | [`packages/strategies/vwap-momentum/SPEC.md`](../packages/strategies/vwap-momentum/SPEC.md) |
| trading-app | [`apps/trading-app/SPEC.md`](../apps/trading-app/SPEC.md) |

## 研究 / 回測

| 文件 | 路徑 |
| ---- | ---- |
| BACKTEST_HOST_CONTRACT | `packages/trading-engine/docs/BACKTEST_HOST_CONTRACT.md` |
| BACKTEST_IMPLEMENTATION | `packages/trading-backtest/docs/BACKTEST_IMPLEMENTATION.md` |
| CALIBRATION (P6-1) | `packages/strategies/vwap-momentum/docs/CALIBRATION.md` |
| SWEEP_SPEC | `apps/trading-app/docs/SWEEP_SPEC.md` |
| AuditContract | `apps/trading-app/docs/AuditContract.md` |

## 已廢止 / 僅供歷史

| 文件 | 說明 |
| ---- | ---- |
| `apps/trading-app/docs/ARCHIVE/UPGRADE_RUNBOOK.md` | 四 repo pin SOP（已棄用）→ 由 monorepo/SPEC 取代 |
| `*/docs/ARCHIVE/` (incl. releases/, MIGRATION_FROM_THEMAN, old BackTesting) | 歷史週報、pre-monorepo 發布記錄、舊 spec、遷移對照。閱讀時注意路徑已過時 |
| 舊 `docs/releases/*.md` | 已移至各 `ARCHIVE/releases/`；舊 standalone git+ 安裝指令僅供歷史 |

## 常見混淆

| 問題 | 答案 |
| ---- | ---- |
| 架構與邊界？ | **`docs/Architecture.md`** |
| 怎麼裝依賴？ | **`bash scripts/setup-dev.sh`** |
| UAT 跑什麼？ | Kernel checklist + App checklist（上表） |
| 加新策略？ | `packages/strategies/<name>/` + `monorepo/SPEC.md` §6 |