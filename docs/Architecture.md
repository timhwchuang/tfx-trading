# tfx-trading 架構（Monorepo）

> **整合自**原 `trading-app/docs/Architecture.md`（2026-06-17）並更新為 monorepo 路徑。  
> **SPEC 入口**：[`SPEC.md`](../SPEC.md) · **AI 護欄**：[`apps/trading-app/AGENTS.md`](../apps/trading-app/AGENTS.md)

---

## 目錄與模組歸屬

| 類別 | 角色 | Monorepo 路徑 |
| ---- | ---- | --------------- |
| **TradingEngine** | 狀態機、下單、session、risk | `packages/trading-engine` |
| **Backtest** | tick replay + MockBroker | `packages/trading-backtest` |
| **Strategy** | 可插拔 alpha（目前 VWAP） | `packages/strategies/vwap-momentum` |
| **Integrations** | port wiring | `apps/trading-app/src/integrations/` |
| **Storage** | tick / kbar 落盤 | `apps/trading-app/src/storage/` |
| **Reporting** | UAT log 解析 | `apps/trading-app/src/reporting/` |

未來新策略：`packages/strategies/<name>/`，與 kernel 同 repo、獨立 package。

```text
apps/trading-app
  ├── packages/trading-engine
  ├── packages/trading-backtest ──► trading-engine
  └── packages/strategies/* ──────► trading-engine
```

---

## Broker 解耦：`BrokerPort`

`TradingEngine` 透過 `self.api` 與券商互動：

- **Live**：`TradingEngine(api=shioaji.Shioaji(...))`
- **Backtest**：`TradingEngine(api=MockBroker(...))`（不走 `start()`，直接 `on_tick`）
- **單測**：`TradingEngine(api=MagicMock())`

[`packages/trading-engine/src/trading_engine/core/ports.py`](../packages/trading-engine/src/trading_engine/core/ports.py) 的 `BrokerPort` Protocol 正名 engine 對 api 的需求；runtime 仍以 duck typing 通過。

Engine 模組頂層已移除 `import shioaji`（`TYPE_CHECKING` + lazy import）。

### 已落地

- **TradingEngine**：`from trading_engine.engine import TradingEngine`
- **Strategy plugin**：entry point `vwap_momentum`（`strategy_vwap_momentum`）
- **Backtest**：`trading_backtest`；app `backtest/engine.py` 薄 wrapper + `trading_app_engine_ports`
- **接線**：`integrations/engine_wiring.py` → `trading_app_engine_ports()` + `load_named_strategy()`
- **依賴安裝**：`bash scripts/setup-dev.sh`（editable path，無 git sibling pin）

### 刻意保留

`trading_engine/session.py` 的 `sync_positions` 仍比對 `sj.Action.Buy`（下一輪可與 `order_events` 字串化統一）。

---

## 資料流（Live / Backtest）

```text
Live:  Shioaji tick → on_tick [lock] → IndicatorState → Strategy.evaluate(MarketSnapshot)
                              ↓ lock 外
       ArchivePort.enqueue → TickArchiver → tick_cache/（TICK_ARCHIVE=1）

Backtest: tick_cache/*.csv(.gz) → load_ticks_csv（整日 RAM）→ iter_replay_ticks → 同一 on_tick
```

| 問題 | 答案 |
| ---- | ---- |
| Live 記憶體線性成長？ | 否。指標用時間窗口 deque；策略只保留輕量 state。 |
| 策略讀硬碟？ | **否**。只吃 `MarketSnapshot`。 |
| 日盤 tick 落盤？ | `TICK_ARCHIVE=1` 非同步寫入；queue 滿會 drop。 |
| Backtest 記憶體？ | 按日整份 CSV 進 RAM；非 row streaming。 |

**視窗語意**（`apps/trading-app/config/config.yaml`）：VWAP 5min 滾動；動量 1s；ATR 20×1m K。P6-1 trend 預設關。

---

## 策略載入

| 路徑 | 現況 |
|------|------|
| Production live/backtest | `default_strategy()` → 硬編碼 `VWAPMomentumStrategy` |
| Entry point（已實作） | `load_named_strategy(name)` / `trading_engine.plugins.load_strategy` |
| Config 切換 | **未接線** — 可加 `strategy.name`（見 `monorepo/SPEC.md` Future） |

新增策略：在 `packages/strategies/<name>/` 註冊 entry point，不必新開 GitHub repo。

---

## 事件驅動（規劃中）

- 熱路徑維持 **in-proc**：on_tick → strategy → arm_pending → order queue
- Side effects（storage、reporting）可走向 NDJSON sink（UAT 後）
- 不用關鍵路徑走外部 MQ

### NautilusTrader 借鏡（摘要）

| 借 | 不借 |
| --- | --- |
| Research ↔ Live 同語意 | Rust 重寫熱路徑 |
| Event catalog / audit | 熱路徑 MQ |
| Cache 抽象 | 多 venue 複雜度 |

**決策（2026-06-17）**：`trend_filter_enabled` 維持 false。見 [`apps/trading-app/docs/WeeklyStatus.md`](../apps/trading-app/docs/WeeklyStatus.md)。

---

## 時序與相容性

- 新縫以可選參數 + 安全預設加入
- `bash scripts/run-all-tests.sh` 每次全綠（engine ~80、strategy ~33、app ~81）
- **tick_cache**：app 用 `storage.cache_paths.DEFAULT_TICK_CACHE_DIR`（repo 根 `tick_cache/`）
- live 入口：`cd apps/trading-app/src && python -m live`（行為不變）