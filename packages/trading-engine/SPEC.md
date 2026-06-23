# Trading Repo Spec

> **Package**: `trading-engine` · **Import**: `trading_engine`  
> 使用者入口：[README.md](README.md) · 實盤安全：[docs/ops/LIVE_SAFETY.md](../../docs/ops/LIVE_SAFETY.md) · UAT：[docs/uat/KERNEL.md](../../docs/uat/KERNEL.md) · 回測宿主：本 SPEC §12 · 變更：[CHANGELOG.md](../../CHANGELOG.md#trading-engine)

## 1. 定位

Broker-agnostic **期貨執行宿主**：單一狀態機，負責 tick → 策略決策 → pending order → fill → session/risk，與券商 API 解耦。

**一句話**：把「怎麼穩健地下單、管倉、管 session」做好；不管「用什麼策略賺錢」。

## 2. In Scope

| 模組 | 職責 |
|------|------|
| `TradingEngine` | 主狀態機：`on_tick`、pending/timeout、fills、daily summary |
| `OrderExecutorMixin` | IOC limit 下單、order queue、callback 處理 |
| `SessionMixin` | session 開閉、position sync（force flatten 由 kernel 主動觸發，Mixin 提供時間計算） |
| `core/types.py` | `MarketSnapshot`、`OrderSignal`、`PositionSnapshot`（含 `qty`）、`TickSnapshot`、`RiskGate` 等 |
| `core/ports.py` | `BrokerPort`、`QUOTE_TYPE_TICK` — engine 對 `api` 的需求契約 |
| `core/trading_state.py` | `PendingIntent` enum + `validate_pending_consistency` 防禦性 guard |
| `core/strategy.py` | **`Strategy` Protocol**（plugin 公開契約，source of truth） |
| `core/side_effect_ports.py` | `TelemetryPort`、`TrendRefreshPort`、`ArchivePort` 等 |
| `core/order_events.py` | 訂單事件字串常數（live/mock 共用） |
| `core/runtime_config.py` | 引擎 runtime 設定（不含 app yaml 載入） |
| `adapters/` | `ShioajiOrderAdapter`、`MockOrderAdapter`、`position_normalizer`、`ShioajiLiveBootstrap` |
| `calendar/` | TAIFEX 交易日曆、`MarketCalendarPort` |
| `exchange_time.py` | **Deprecated** compat re-export；新程式用 `calendar.taifex` |
| `indicators.py` | 引擎層共用指標 helper（ATR 等，非策略邏輯） |
| `order_errors.py` | 下單錯誤分類 |
| `logging_setup.py` | async logging 設定 |
| `settings.py` | 設定 dataclass（由 app 載入 yaml 後注入） |
| `plugins.py` | **可選** entry-point strategy discovery（非核心；多數 app 直接注入 strategy） |

## 3. Out of Scope

| 不屬於 Trading | 歸屬 |
|----------------|------|
| 策略邏輯（VWAP、momentum、trend veto） | Strategy plugin |
| Tick replay、Mock 撮合、VirtualClock | Backtest |
| Tick/kbar 存檔、資料 loader | App / Backtest |
| Telegram alert、UAT report | App |
| Param sweep、績效報表 | App |
| Live CLI 入口 | App（consuming repo） |

## 4. 公開 API（穩定面）

### 4.1 建構

`api` 為**必填**（`BrokerPort` duck type）；核心路徑（`engine.py` / `session.py` / `order_executor.py`）不含 runtime `import shioaji`。

```python
from trading_engine import TradingEngine, RuntimeConfig, Settings
from trading_engine.adapters.shioaji import ShioajiOrderAdapter
from trading_engine.adapters.shioaji_live import ShioajiLiveBootstrap
from trading_engine.adapters.mock import MockOrderAdapter
from trading_engine.core.types import TickSnapshot

engine = TradingEngine(
    api=broker,                    # 必填；live 時由 app 層建立 sj.Shioaji(...)
    strategy=strategy_instance,    # Strategy Protocol
    runtime_config=cfg,
    order_adapter=ShioajiOrderAdapter(api=broker),  # 必須顯式注入
    telemetry=...,                 # optional TelemetryPort
    trend_refresh=...,             # optional TrendRefreshPort
    clock=...,                     # optional（backtest 注入 VirtualClock）
)

# Live：bootstrap 負責 callback、subscribe、TickFOPv1 → TickSnapshot
ShioajiLiveBootstrap(engine).start_live()

# Backtest / kernel test：直接餵 TickSnapshot 或 duck-typed tick
engine.on_tick(TickSnapshot(ts=..., price=..., volume=..., tick_type=1, exchange_dt=...))
```

### 4.2 Strategy Protocol（給 plugin 實作）

定義於 `trading_engine.core.strategy`（**程式真相**）。注入：`TradingEngine(strategy=MyStrategy(), ...)`。

| 方法 | 必填？ | 用途 |
|------|--------|------|
| `evaluate` | **是** | 每 tick 進出場決策 |
| `reset` | **是**（可 no-op） | fill / resync 後清 episode state |
| `manage_exit` | 選填 | 持倉中 trailing / TP / stop |
| `build_*_audit` | 選填 | SIGNAL 審計 enrichment |
| `session_force_flatten_signal` | 選填 | 客製 kernel force-flatten exit |

`evaluate` 收到預先計算的 `RiskGate` — 勿自行重推 pending / session 旗標。

**MUST（策略作者）**

1. 尊重 `RiskGate` — `is_pending`、`block_new_entry`（entry）、`api_connected` false、session gate 時回 `None`。
2. 回傳合法 `OrderSignal` — `qty > 0`，`intent` ∈ `entry`/`exit`，`action` ∈ `Buy`/`Sell`（kernel 會拒絕非法 signal）。
3. Intent 對應持倉 — entry 僅 `position.qty == 0`；exit 僅 `position.qty > 0`。
4. **勿 mutate `TradingEngine`** — 策略為純決策；用 `get_state_snapshot()` 唯讀觀察。
5. 實作 `reset` — 清除 momentum / episode 計數。

**MUST NOT**

- 在 plugin 內 `import shioaji` 或 app 層模組（Telegram、yaml loader）。
- `risk.is_pending` 時仍回 entry signal（kernel 也擋，但避免 log 噪音）。
- 假設 scale-in / partial exit — kernel exit 使用全量 `position.qty`（見 §4.2.1）。

**0.x → 1.0 演進**：收斂成更小 surface（`evaluate` + `reset` 必填）；breaking 變更 → major bump。

### 4.2.1 Position Model Scope（重要限制）

本 kernel 的持倉模型為 **單一方向、全倉進出**：

| 支援 | 不支援 |
|------|--------|
| 單一 Long 或 Short 部位（`position_qty` 整數口數） | 同商品多筆反向持倉 net 會計 |
| Entry 全量進場；Exit 全量平倉（`qty → 0`） | Scale-in（分批加碼） |
| `sync_positions` 取第一筆匹配的非零部位 | Partial exit（減碼留倉） |
| ~1 口台指日盤策略 | 通用投資組合 / 多商品同時管理 |

外部整合者請勿假設本 repo 提供一般券商部位管理能力。觀察狀態請用 `TradingEngine.get_state_snapshot()`，**切勿**直接 mutate engine 公開屬性。

### 4.2.2 狀態機不變量

| 維度 | 合法值 | 備註 |
|------|--------|------|
| `position_qty` | `int >= 0` | 0 = Flat；主會計欄位 |
| `position_dir` | Flat / Long / Short | `qty == 0` 時必須 Flat |
| `is_pending` | bool | 委託在途 |
| `pending_intent` | entry / exit / None | `is_pending` 時必須有值 |
| `pending_order_id` | str / None | callback 嚴格比對 |
| `filled_qty` | int | IOC partial 累積 |

`has_position` 為衍生屬性（`position_qty > 0`）。

**Kernel 保證**

1. `is_pending` 期間不 arm 第二筆 entry（`_validate_order_signal` 硬擋）。
2. `session_force_flatten_time` 後若 `position_qty > 0`，**kernel** 產生 exit（strategy 僅可 `session_force_flatten_signal` 客製）。
3. `position_qty` 僅由 `sync_positions` 與 matching deal 的 `_apply_deal_fill` 變更。
4. Exit 為全量平倉（`qty → 0`）；partial fill 未達 `pending_qty` 時維持 pending。
5. 錯誤 `order_id` 的 deal/fill 忽略（idempotency）。
6. 日內風控計數依 `trading_day_for_daily_reset` 重置。

實作參考：`order_executor.py`、`session.py`、`engine.py`。歷史設計稿見 [`docs/ARCHIVE/engine/DESIGN.md`](../../docs/ARCHIVE/engine/DESIGN.md)。

### 4.3 BrokerPort

文件化 `self.api` 所需方法；runtime 不強制 isinstance，允許 `MockBroker` / `MagicMock`。

約定：

- `subscribe(contract, quote_type=...)` — live Shioaji 傳 `QuoteType.Tick`；語意常數見 `QUOTE_TYPE_TICK`
- `list_positions(...)` 回傳物件需有 `code`、`quantity`（int）、`direction`、`price`（float）；方向正規化用 `adapters.position_normalizer.is_long_direction`

### 4.4 Optional extras

```toml
pip install trading-engine           # 核心，無券商依賴
pip install trading-engine[shioaji]  # 永豐 Shioaji adapter
```

## 5. 依賴

| 方向 | 規則 |
|------|------|
| → Strategy | **禁止** import 任何 strategy plugin |
| → Backtest | **禁止** |
| → 舊內部 monorepo（theman 等） | **禁止** |
| ← Strategy plugin | 只 import `trading_engine.core.*` |
| ← Backtest | import `TradingEngine`、types、adapters |
| ← App | 組裝 engine + ports + strategy |

**Runtime dependencies**：核心 `dependencies = []`；Shioaji 僅在 `[shioaji]` extra。

## 6. 目錄結構（現況 = 目標）

```
trading-engine/
├── SPEC.md
├── README.md
├── LICENSE
├── pyproject.toml
├── run_tests.py
└── src/trading_engine/
    ├── engine.py          # broker-neutral kernel（無 runtime shioaji）
    ├── session.py
    ├── order_executor.py
    ├── adapters/          # shioaji_live.py 為 live 接線唯一入口
    ├── calendar/
    ├── core/
    ├── py.typed
    └── ...
```

## 7. 歷史遷移（舊內部消費者）

從 theman monorepo 抽離的路徑對照見 [docs/ARCHIVE/MIGRATION_FROM_THEMAN.md](../../docs/ARCHIVE/MIGRATION_FROM_THEMAN.md)（**Historical — 新使用者可忽略**）。

## 8. 測試

| 階段 | 做法 |
|------|------|
| **本 repo** | `python run_tests.py` — **73** kernel tests（含 adversarial：qty、callbacks、reconnect、sync、force-flatten、signal validation、state snapshot、no-shioaji core import） |
| **消費端** | strategy / backtest / app repo 自有整合測 |
| **CI** | [.github/workflows/tests.yml](.github/workflows/tests.yml) — push/PR 至 `main` 跑 matrix Python 3.11–3.13：`ruff check`、`ruff format --check`、`mypy`、`python run_tests.py`（含 `test_no_shioaji_core_import.py`） |

Kernel tests 必須在 **不裝 Shioaji、不裝 strategy plugin** 下跑完。靜態檢查：`engine.py` / `session.py` / `order_executor.py` 不得含 runtime `import shioaji`（見 `tests/test_no_shioaji_core_import.py`）。

## 9. 版本策略

- **0.x**：Protocol / types 可能調整；獨立 semver
- **1.0**：Strategy Protocol 穩定、semver 保證、CI 綠燈

Breaking change 範例：`Strategy.evaluate` 簽名變更、`OrderSignal` 欄位移除 → **major bump**。

## 10. 待辦（Trading repo）

- [x] Position qty 模型（Phase 1）
- [x] Kernel-owned force-flatten + session_force_flatten_signal hook（Phase 2）
- [x] Shioaji 隔離（position_normalizer + TickSnapshot + shioaji_live bootstrap）（Phase 3）
- [x] 狀態維度 / 不變量（本 SPEC §4.2.2）
- [x] Kernel test suite 擴充（37 → 73，含 adversarial + safety guards）
- [x] CI pipeline（本 repo）
- [ ] 發布 PyPI（或 GitHub Packages）
- [x] ~~theman vendored copy~~ → cancelled（historical；見 ARCHIVE/MIGRATION_FROM_THEMAN.md）
- [x] Live safety docs + state snapshot + signal validation guards
- [x] CI lint + typecheck（ruff / mypy）

`core/trading_state.py` 含 `PendingIntent` enum + `validate_pending_consistency` 防禦性 guard。

## 11. 非目標

- 不做策略 marketplace 宿主（屬 App 或獨立 tooling）
- 不做分散式 order routing / MQ 熱路徑
- 不做多券商抽象層（除 Shioaji + Mock 外，新券商用新 adapter PR）

## 12. Backtest host contract

> **Consumers**: `trading-backtest`, kernel tests, any replay driver.  
> **App audit fields**: [`apps/trading-app/SPEC.md`](../../apps/trading-app/SPEC.md) §Integration contracts.

`BacktestEngine` must drive the **same** `TradingEngine` class as live. Replay may only **inject**: `api`, `clock`, `strategy`, ports, `order_adapter`, `runtime_config`.

**Golden rules**

1. Decision logic lives in **Strategy plugins** — never in the replay driver.
2. No `time.time()` / `datetime.now()` / `date.today()` on the replay path.
3. Lock rule: 
   - `self.lock` protects Python engine state only.
   - `self._api_lock` (RLock) must be held for all mutable Shioaji API operations (place_order, update_status, list_positions, kbars, login, logout, usage, subscribe, activate_ca, subscribe_trade, callback registration).
   - Acquisition order when both needed: `_api_lock` first, then `self.lock` (or keep them non-nested).
   - Do not hold `self.lock` across API calls.
   - Backtest uses pre-tick sync refresh outside lock（見 `trading-backtest` SPEC §7.1）.

See implementation in TradingEngine.__init__, OrderExecutorMixin, SessionMixin.

**Constructor**（同 §4.1；backtest 注入 `VirtualClock` + `MockOrderAdapter`）

**Tick input** — `on_tick(tick)` duck-typed tick:

| Field | Type | Notes |
|-------|------|-------|
| `datetime` | `datetime` | Taipei naive |
| `close` | `str` or `float` | Engine normalizes |
| `volume` | `int` | |
| `tick_type` | `int` | |

**Order / fill**

- `place_order(signal)` → `api.place_order(contract, order, timeout=0)` → object with `.order.id` (may be empty at return in simulation; backfill from first callback).
- `handle_order_event(stat, msg)`:
  - `FuturesDeal`: `price`, `quantity`, `action`, `trade_id`
  - `FuturesOrder` (cancel): `operation`, `status`, `trade_id`
- **Live Shioaji pitfall:** callback `stat` is `OrderState.FuturesOrder` / `FuturesDeal`, not a plain string. `isinstance(stat, str)` is `True` on Shioaji `OrderState` — route via `stat.name` (see `core/order_events.normalize_order_stat`). Mock/backtest use string `"FuturesOrder"` / `"FuturesDeal"`; live integration must be tested with real `OrderState` or `live.order_smoke`.
- Pending fields used by replay: `pending_order_id`, `pending_intent`, `is_pending`, `pending_qty`, etc.

**ATR / kbars**

- `refresh_atr()` calls `api.kbars(contract, start, end)` expecting `.High` / `.Low` / `.Close` lists.
- Backtest sets `_maybe_refresh_atr` to no-op; driver refreshes **before** `on_tick` outside lock.

**Session / premarket**

- `exchange_time.is_trading_session(dt, SESSION_START, SESSION_END)` gates **decision** (`on_tick`).
- Premarket ticks may still run matching + pending timeout（見 backtest SPEC）。

**Audit lines**（determinism gate）

Kernel + telemetry emit `SIGNAL_AUDIT`, `FILL_AUDIT`, `DAILY_SUMMARY` — field semantics in app SPEC §Integration contracts.

**Tests**

- Kernel state machine, pending, session, risk gates — `python run_tests.py`（本 repo）
- Integration scenarios — [`docs/uat/KERNEL.md`](../../docs/uat/KERNEL.md) Phase B/C
