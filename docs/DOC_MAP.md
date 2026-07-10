# 文件職責地圖

> Active 文件一個真相來源。考古見 [`legacy/`](../legacy/README.md)。

## 入口

| 文件 | 職責 |
|------|------|
| [`../README.md`](../README.md) | Clone / setup |
| [`AGENTS.md`](AGENTS.md) | AI 安全 + 架構 |
| [`../CHANGELOG.md`](../CHANGELOG.md) | 版本歷史 |
| [`../legacy/README.md`](../legacy/README.md) | 歷史研究索引 |

## 架構

| 文件 | 職責 |
|------|------|
| [`../SPEC.md`](../SPEC.md) | Monorepo 整合 |
| [`../apps/trading-app/SPEC.md`](../apps/trading-app/SPEC.md) | 產品邊界 / Host 架構 SSOT（Foundation A–D） |
| [`../apps/trading-app/src/storage/SPEC.md`](../apps/trading-app/src/storage/SPEC.md) | tick_cache SSOT |

## 運維

| 文件 | 職責 |
|------|------|
| [`ops/LIVE_SAFETY.md`](ops/LIVE_SAFETY.md) | 實盤失敗情境 |
| [`ops/HYBRID_DEPLOY.md`](ops/HYBRID_DEPLOY.md) | GCE Live |
| [`ops/LinuxOps.md`](ops/LinuxOps.md) | systemd |
| [`ops/WindowsOps.md`](ops/WindowsOps.md) | Windows 排程 |

## 考古

| 路徑 | 說明 |
|------|------|
| [`../legacy/docs/`](../legacy/docs/) | 舊 features / UAT / TODO / WeeklyStatus |
| [`ARCHIVE/`](ARCHIVE/) | 更早設計稿 |
| [`../packages/README.md`](../packages/README.md) | engine 已併入 app |
