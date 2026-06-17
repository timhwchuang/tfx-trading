# tfx-trading — Monorepo Spec (整合入口)

> **Repo**: [`timhwchuang/tfx-trading`](https://github.com/timhwchuang/tfx-trading)  
> **文件地圖**: [`docs/DOC_MAP.md`](docs/DOC_MAP.md) · **進度**: [`docs/TODO.md`](docs/TODO.md)  
> **遷移紀錄（考古）**: [`docs/ARCHIVE/MONOREPO_MIGRATION_PLAN.md`](docs/ARCHIVE/MONOREPO_MIGRATION_PLAN.md)

**文件分層**（與程式依賴同向）：

| 層級 | 文件 | 讀者 | 連結規則 |
|------|------|------|----------|
| **高階** | 本檔、`docs/DOC_MAP.md`、`docs/TODO.md` | clone repo、加策略、發版 | 可指向各 package `SPEC.md` |
| **低階** | `packages/*/SPEC.md`、`apps/trading-app/SPEC.md` | 改該模組的人 | **只連依賴**（下游 kernel / 同層 app）；**不連回本檔** |

在 `packages/` 內工作時，以該目錄 `SPEC.md` 為入口，不必回頭讀根 `SPEC.md`。

---

## 1. 定位

台指期（TXF）個人研究用 **monorepo**：kernel、回測、可插拔策略、Windows UAT 整合，單一 `git clone` 即可開發。

| 路徑 | pip 名稱 | import | 職責 |
|------|----------|--------|------|
| [`packages/trading-engine`](packages/trading-engine/SPEC.md) | `trading-engine` | `trading_engine` | 狀態機、risk、broker adapters、Strategy Protocol |
| [`packages/trading-backtest`](packages/trading-backtest/SPEC.md) | `trading-backtest` | `trading_backtest` | Tick replay、MockBroker |
| [`packages/strategies/vwap-momentum`](packages/strategies/vwap-momentum/SPEC.md) | `strategy-vwap-momentum` | `strategy_vwap_momentum` | VWAP momentum plugin（entry point `vwap_momentum`） |
| [`apps/trading-app`](apps/trading-app/SPEC.md) | — | `src/` on path | Config、落盤、reporting、sweep、Windows 執行 |

**App 子模組**（`apps/trading-app/src/`）：

| 路徑 | 職責 |
|------|------|
| `integrations/` | port wiring、`trading_app_engine_ports()` |
| `storage/` | tick / kbar 落盤 |
| `reporting/` | UAT log 解析、sweep 評分 |

**依賴方向**（不可逆向）：

```text
apps/trading-app → trading-engine, trading-backtest, strategy-*
trading-backtest → trading-engine
packages/strategies/* → trading-engine
```

---

## 2. 安裝與測試

```bash
git clone git@github.com:timhwchuang/tfx-trading.git
cd tfx-trading
python3 -m venv .venv && source .venv/bin/activate
bash scripts/setup-dev.sh
bash scripts/run-all-tests.sh
```

Windows 執行與 UAT：[`apps/trading-app/README.md`](apps/trading-app/README.md)

**測試基線**（`bash scripts/run-all-tests.sh`）：engine ~80、strategy ~33、app ~81、backtest 全綠。

**Live 入口**：`cd apps/trading-app/src && python -m live`（行為不變）。

---

## 3. 模組 SPEC（各 package 為真相來源）

| 主題 | 文件 |
|------|------|
| Engine 狀態機 / Protocol / 回測宿主 | [`packages/trading-engine/SPEC.md`](packages/trading-engine/SPEC.md)（§4、§12） |
| MockBroker / 回放 | [`packages/trading-backtest/SPEC.md`](packages/trading-backtest/SPEC.md) §5–10 |
| VWAP 策略參數與 audit | [`packages/strategies/vwap-momentum/SPEC.md`](packages/strategies/vwap-momentum/SPEC.md) |
| App 整合、audit、sweep | [`apps/trading-app/SPEC.md`](apps/trading-app/SPEC.md) §Integration contracts |

---

## 4. 新策略（研究驗證）

策略放在 `packages/strategies/<name>/`（與 kernel / backtest 分離）。

**命名慣例**

| 層級 | 慣例 | 範例 |
|------|------|------|
| 目錄 | `packages/strategies/<short-kebab>/` | `vwap-momentum` |
| pip / `pyproject.toml` `name` | `strategy-<short-kebab>` | `strategy-vwap-momentum` |
| Python import | `strategy_<snake>` | `strategy_vwap_momentum` |
| Entry point key | `<snake>` | `vwap_momentum` |

**步驟**

1. 複製 `packages/strategies/vwap-momentum/` → `packages/strategies/<name>/`
2. 設定 `pyproject.toml`：`name = "strategy-<name>"`、`dependencies = ["trading-engine>=0.2.2,<1.0"]`、`[project.entry-points."trading_engine.strategies"]` → `<name> = "strategy_<module>:StrategyClass"`
3. 加入 [`scripts/setup-dev.sh`](scripts/setup-dev.sh) 與 [`scripts/run-all-tests.sh`](scripts/run-all-tests.sh)
4. App 載入：[`load_named_strategy()`](apps/trading-app/src/integrations/engine_wiring.py)（可選 `config.yaml` `strategy.name`）

失敗實驗：刪除或移至 `experiments/`，無需另開 GitHub repo。

**策略載入現況**

| 路徑 | 現況 |
|------|------|
| Production live/backtest | `default_strategy()` → 硬編碼 `VWAPMomentumStrategy` |
| Entry point（已實作） | `load_named_strategy(name)` / `trading_engine.plugins.load_strategy` |
| Config 切換 | **未接線** — 可加 `strategy.name`（見本檔 §4 步驟 4） |

---

## 5. 版本與發布

各 package 保留獨立 `pyproject.toml` `version`；**變更紀錄統一寫入根 [`CHANGELOG.md`](CHANGELOG.md)**（按 package 分區）。Monorepo 發布 SOP：

1. 改動 → bump 該 package `version` → `bash scripts/run-all-tests.sh` 全綠  
2. 更新根 `CHANGELOG.md` 對應 package 區塊  
3. commit；可選 monorepo tag  

**注意**：不再建立新的 `docs/releases/vX.Y.Z.md`。歷史釋出記錄見 [`docs/ARCHIVE/releases/`](docs/ARCHIVE/releases/)。舊 standalone git+ 安裝範例僅供考古。

舊四 repo 已封存；歷史 tag 仍指向舊 GitHub，**現行開發僅此 repo**。授權：[LICENSE](LICENSE)（MIT）；各 package 目錄保留同名 `LICENSE` 供單獨發布 wheel 使用。

---

## 6. 安全與 UAT

- AI / 開發紀律：[`docs/AGENTS.md`](docs/AGENTS.md)
- Kernel UAT：[`docs/uat/KERNEL.md`](docs/uat/KERNEL.md)
- App UAT（含 Pilot Gate）：[`docs/uat/APP.md`](docs/uat/APP.md)
- 實盤安全：[`docs/ops/LIVE_SAFETY.md`](docs/ops/LIVE_SAFETY.md)

---

## 7. 架構與資料流

### 7.1 Broker 解耦：`BrokerPort`

`TradingEngine` 透過 `self.api` 與券商互動：

- **Live**：`TradingEngine(api=shioaji.Shioaji(...))`
- **Backtest**：`TradingEngine(api=MockBroker(...))`（不走 `start()`，直接 `on_tick`）
- **單測**：`TradingEngine(api=MagicMock())`

[`packages/trading-engine/src/trading_engine/core/ports.py`](packages/trading-engine/src/trading_engine/core/ports.py) 的 `BrokerPort` Protocol 正名 engine 對 api 的需求；runtime 仍以 duck typing 通過。Engine 模組頂層已移除 `import shioaji`（`TYPE_CHECKING` + lazy import）。

**已落地**

- **TradingEngine**：`from trading_engine.engine import TradingEngine`
- **Strategy plugin**：entry point `vwap_momentum`（`strategy_vwap_momentum`）
- **Backtest**：`trading_backtest`；app `backtest/engine.py` 薄 wrapper + `trading_app_engine_ports`
- **接線**：`integrations/engine_wiring.py` → `trading_app_engine_ports()` + `load_named_strategy()`

**刻意保留**

`trading_engine/session.py` 的 `sync_positions` 仍比對 `sj.Action.Buy`（下一輪可與 `order_events` 字串化統一）。

### 7.2 資料流（Live / Backtest）

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

**tick_cache**：app 用 `storage.cache_paths.DEFAULT_TICK_CACHE_DIR`（repo 根 `tick_cache/`）。

### 7.3 事件驅動（規劃中）

- 熱路徑維持 **in-proc**：on_tick → strategy → arm_pending → order queue
- Side effects（storage、reporting）可走向 NDJSON sink（UAT 後）
- 不用關鍵路徑走外部 MQ

**NautilusTrader 借鏡（摘要）**

| 借 | 不借 |
| --- | --- |
| Research ↔ Live 同語意 | Rust 重寫熱路徑 |
| Event catalog / audit | 熱路徑 MQ |
| Cache 抽象 | 多 venue 複雜度 |

**決策（2026-06-17）**：`trend_filter_enabled` 維持 false。見 [`docs/WeeklyStatus.md`](docs/WeeklyStatus.md)。

### 7.4 時序與相容性

- 新縫以可選參數 + 安全預設加入
- 相容性以 `bash scripts/run-all-tests.sh` 全綠為 gate
