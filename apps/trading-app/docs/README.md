# 文件索引（app 層）

> **全 monorepo 索引**：[`docs/DOC_MAP.md`](../../../docs/DOC_MAP.md)  
> **路線圖**：[`TODO.md`](../TODO.md)｜**週報**：[`WeeklyStatus.md`](WeeklyStatus.md)  
> **AI 請先讀**：[`AGENTS.md`](../AGENTS.md) §2 安全護欄

| 文件 | 用途 |
| ---- | ---- |
| [`../AGENTS.md`](../AGENTS.md) | AI 主規範（架構、gate） |
| [`../../../docs/Architecture.md`](../../../docs/Architecture.md) | **架構真相**（monorepo 邊界、資料流） |
| [`../../../SPEC.md`](../../../SPEC.md) | 整合 SPEC 入口 |
| [`UAT_CHECKLIST.md`](UAT_CHECKLIST.md) | **App 層 UAT**（Windows 部署、落盤、報表） |
| [`AuditContract.md`](AuditContract.md) | SIGNAL/FILL/DAILY_SUMMARY log 契約 |
| [`BeforePilot.md`](BeforePilot.md) | UAT → Pilot gate |
| [`WindowsOps.md`](WindowsOps.md) | 排程、告警（`C:\tfx-trading` 路徑） |
| [`SWEEP_SPEC.md`](SWEEP_SPEC.md) | 確定性 + param sweep |
| [`BackTestingSpec.md`](BackTestingSpec.md) | 索引 stub → 各 package 規格 |
| [`ARCHIVE/`](ARCHIVE/) | 歷史週報（非現行真相） |
| [`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md) | 舊四-repo 發布紀錄 |
| [`UPGRADE_RUNBOOK.md`](UPGRADE_RUNBOOK.md) | **已 deprecated** → `monorepo/SPEC.md` |

## Package 規格（monorepo 內相對路徑）

| Package | 關鍵文件 |
| ---- | -------- |
| trading-engine | [`BACKTEST_HOST_CONTRACT`](../../../packages/trading-engine/docs/BACKTEST_HOST_CONTRACT.md)、[`UAT_CHECKLIST`](../../../packages/trading-engine/docs/UAT_CHECKLIST.md)、[`LIVE_SAFETY`](../../../packages/trading-engine/docs/LIVE_SAFETY.md) |
| trading-backtest | [`BACKTEST_IMPLEMENTATION`](../../../packages/trading-backtest/docs/BACKTEST_IMPLEMENTATION.md) |
| vwap-momentum | [`CALIBRATION`](../../../packages/strategies/vwap-momentum/docs/CALIBRATION.md) |

## 現行架構速查

- **Host**：`packages/trading-engine` → `TradingEngine`
- **Backtest**：`packages/trading-backtest`；app `src/backtest/engine.py` 注入 ports
- **Strategy**：`packages/strategies/vwap-momentum`
- **Wiring**：`trading_app_engine_ports()`
- **測試**：app **81** 項；全 repo `bash scripts/run-all-tests.sh`