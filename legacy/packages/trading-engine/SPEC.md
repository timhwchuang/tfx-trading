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
| `_settling` | bool | timeout 後 = 委託結果未知（UNKNOWN），主動對帳確認中 |
| `_position_unconfirmed` | bool | 部位未經券商確認（HALT）；凍結 entry+exit |

`has_position` 為衍生屬性（`position_qty > 0`）。`settling` / `position_unconfirmed` 透過 `get_state_snapshot()` 與 `RiskGate` 對外暴露（唯讀）。

**Kernel 保證**

1. `is_pending` 期間不 arm 第二筆 entry（`_validate_order_signal` 硬擋）。
2. `session_force_flatten_time` 後若 `position_qty > 0`，**kernel** 產生 exit（strategy 僅可 `session_force_flatten_signal` 客製）。
3. `position_qty` 僅由 `sync_positions` 與 matching deal 的 `_apply_deal_fill` 變更。
4. Exit 依實際成交量遞減 `position_qty`，歸零才轉 Flat（**P1-1**）；單筆委託內 partial fill 未達 `pending_qty` 時維持 pending。Exit 由 kernel 以實際 `position_qty` 為平倉量；平倉自認 flat 後觸發 re-sync 以券商確認。
5. **無法歸屬的成交（pending 已清或 `order_id` 不符）不得靜默丟棄（P0-2）**：觸發 `sync_positions` + `block_new_entry` + CRITICAL，以券商為準。
6. 日內風控計數依 `trading_day_for_daily_reset` 重置。
7. **`_api_connected`** 僅在「報價 subscribe 成功」**且「委託/成交回報通道重掛（`_resubscribe_trade`）成功」**且 `refresh_atr()` 成功（或 ATR 失敗非 session 錯誤）後由 `_on_reconnected` 設為 `True`；任一失敗 → 保持 disconnected，交由 session watchdog relogin（**P0-1**，見 [`LIVE_SAFETY.md`](../../docs/ops/LIVE_SAFETY.md)）。重連只重訂報價而不重掛回報通道，是 24 口 phantom short 的主因。
8. **週期對帳熔斷（P0-3）**：交易時段每 `position_reconcile_sec`（預設 60）以 `list_positions` 比對；qty/dir 與券商不一致 → 以券商為準更新 + `block_new_entry` + CRITICAL。**嚴重漂移（severe drift）** 須經 `reconcile_confirm_reads` debounce 後才 HALT + 收斂市價平倉（避免 exit fill 後 broker 回報延遲誤觸）：`kernel=Flat` 且 `broker_qty>0`、方向反轉、或 `broker_qty > max 且 > kernel_qty`。`_position_unconfirmed`（HALT）時改 `reconcile_fast_sec`（預設 1）快節奏；**exit 全平後**另設 `post_exit_reconcile_sec`（預設 15）快節奏窗口，縮短 over-flatten 盲窗。「未確認持倉與券商一致前，禁止任何新進場」；對帳是 kernel 的權威來源，callback 僅為快路徑。
9. **硬部位上限（P0-4）**：`_validate_order_signal` 對 entry 於 `position_qty + signal.qty > max_position_qty`（預設 1）時拒單；對帳/結算發現 `broker_qty > max 且 > kernel_qty` → HALT + 收斂平倉（硬背板）。
10. **部位真相驅動（P0-5）＋實盤淨部位硬上限永不超過 `max_position_qty`（=1）**：券商 `list_positions` 為唯一真相。
    - **Timeout = UNKNOWN，非 FAILED**：`pending_timeout_sec`（預設 1）後**不**清 pending 讓策略重下，而是進入 `_settling`（保留 `pending_order_id` 使遲到成交仍可歸屬），快節奏（`reconcile_fast_sec`，預設 1）poll 券商（`_settle_via_reconcile`），讀數經 `reconcile_confirm_reads`（預設 3）次 debounce 後採信。**未知視窗下限＝券商自身回報延遲**（`list_positions`/deal 皆會延遲），縮短本值無法壓到券商延遲以下；exit/停損時效改由緊急市價脫鉤（見下）。
    - **entry 永不以「瞬間 flat 快照」判定未成交**：`_apply_pending_broker_truth` entry 分支**只有正向成交**才解析 pending；瞬間 flat 讀數不是未成交證據。時間門控的 **MISSED** 決策在 `_settle_via_reconcile`（`entry_miss_confirm_sec` 預設 5 + debounce）：穩定 readable-flat 逾窗 → 清 pending、記 WARNING、**恢復正常進場**（不 sticky HALT）。
    - **exit 永不以 L3 unchanged 推論未成交（2026-06-29 RCA）**：`_apply_pending_broker_truth` exit 分支**任何時候**（含非 HALT）皆不得以「部位未變且與 kernel 一致」清 pending — 在途 IOC 可能已成交但 `list_positions` 尚未反映。時間門控 **exit MISSED** 在 `_settle_via_reconcile`（`exit_miss_confirm_sec` 預設 5 + debounce）：先 `order_deal_records`，仍無終態則 `_resolve_exit_missed` — `stop_loss`/`stop_loss_vwap` → 市價 flatten 請求 + clear（禁止策略 limit 重試）；`take_profit`/`trailing_stop`/其他 → clear + WARNING（允許策略下一 tick 重試 limit）。
    - **已清 pending 的遲到成交歸屬**：僅在 **未經正常 fill 路徑** 清 pending 時（`_clear_pending(watch_late_fill=True)`：miss resolve、L1/L2 Cancelled 無 fill、HALT clear）將 `order_id` 寫入 `_recent_cleared_orders`（TTL `cleared_order_registry_sec` 預設 120）。正常 `_apply_deal_fill` 後清 pending **不**登記。遲到 deal callback 或 `order_deal_records` 命中 registry → HALT + CRITICAL。
    - **雙層狀態機**：**SETTLING**（暫態、自動恢復）vs **HALT**（異常、sticky）。偶發 callback 靜默 / 單次 entry miss → SETTLING → NORMAL。HALT 僅用於：上限 breach、孤兒/非當前成交、券商不可讀、debounce 無法穩定、連續 miss 熔斷（`max_consecutive_missed_entries` 預設 3）。
    - **單一在途（single-flight）涵蓋所有 kernel 委託**：`_halt_position_unconfirmed(clear_pending=...)` 只有在呼叫端確知在途委託已終結才 `clear_pending=True`；exit/平倉在途一律保留 `order_id`。
    - **不確定即凍結**：`_settling` 凍結新 entry；`_position_unconfirmed`（HALT）凍結 entry+exit。
    - **exit 逾時轉 HALT**：`settle_timeout_sec`（預設 45）內 exit 仍無法確認 → HALT（single-flight 保留在途單）。entry 不在此路徑 sticky-HALT（改 MISSED 恢復）。
    - **收斂式復原（以新鮮 debounce 真相定量）**：HALT 且券商非 flat → kernel `_maybe_converge_flatten` **重新讀取並 debounce 券商真相**，以該確認 qty 送**唯一一張**平倉（`is_pending`/`_settling` 守門 + 節流），送後回 `_settling` 等確認；確認 flat 後解除 HALT（`block_new_entry` 維持至日切/人工）。HALT 期間**不得**以「未變動且一致」讀數清在途 exit/平倉（分鐘級延遲下該讀數只是尚未反映的舊部位），否則收斂會重複送 — HALT 中 exit 只認真實減倉或明確 Cancelled。
    - **緊急市價單（`emergency_market_orders`，預設 True）**：停損 IOC（`stop_loss`/`stop_loss_vwap`）未成交（Cancelled 無 fill）→ kernel 送**唯一一張市價平倉**（`_maybe_emergency_market_flatten`，single-flight、`_kernel_converging` 繞過凍結）；`_stop_market_flatten_request` 待送出期間 `_validate_order_signal` **拒絕策略 exit/entry**（防 miss-clear 與 market flatten 間隙雙送）。收斂平倉亦改市價。保證成交、以滑價換時效，使 exit/停損「最慢多久平倉」自未知視窗脫鉤。entry 與獲利/移動停利出場維持限價 IOC 不變。
    - 孤兒/非當前委託成交 → `_position_unconfirmed`（全面凍結，非僅 `block_new_entry`）。
    - **IOC live vs sim**：live IOC 為交易所內建單別（ms 級終結）；模擬環境回報延遲可達分鐘級（批次撮合、測試主機限制），**不得**用模擬延遲校準 live 行為。`entry_miss_confirm_sec=5` 對 live 保守；sim 可能觸發 orphan→收斂背板（預期、安全）。
    - **回報延遲量測**：`CALLBACK_LATENCY` log（`exchange_ts` vs 本地接收時間）供 UAT 校準。
    - **雙層真相模型（callback-first，Shioaji 官方路徑）**：
      - **Layer 1（快路徑）**：`set_order_callback` → `handle_order_event` / `_handle_futures_order` / `_handle_futures_deal` — Cancelled/Failed 內聯清 pending、停損市價 escalation 等。
      - **Layer 2（背景對帳）**：timeout/settle 走 `order_deal_records` + `list_positions` debounce（`_reconcile_pending_trade` / `_settle_via_reconcile`）。**零** runtime `update_status(trade)`。
      - **HALT 期間 exit pending 何時可清（訊號分類）**：**推論（L3 unchanged read）永不 clear exit pending**；**L1 callback Cancelled** clear 並允許 convergence / 市價重試；**時間門控 exit MISSED**（`exit_miss_confirm_sec`）為第三路徑。
      - Callback 沉默時終態辨識延遲至 `entry_miss_confirm_sec` / `exit_miss_confirm_sec`（預設 5s）。UAT gate：零 `update_status`、callback 不 deadlock。見 [`LIVE_SAFETY.md`](../../docs/ops/LIVE_SAFETY.md)。

實作參考：`order_executor.py`（`handle_order_event`、`_settle_via_reconcile`、`_reconcile_pending_trade`）、`session.py`、`engine.py`。

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
| **本 repo** | `python run_tests.py` — **112** kernel tests（含 adversarial：qty、callbacks、reconnect、no-tick escalation、sync、force-flatten、signal validation、state snapshot、no-shioaji core import） |
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

### Shioaji Time Contract

**Internal convention:** all naive `datetime` values in this repo mean **exchange wall clock** (Asia/Taipei semantics, no `tzinfo`).

**Vendor reference:** [Shioaji Historical Market Data](https://sinotrade.github.io/tutor/market_data/historical/) documents `ts` as an integer Unix timestamp. Official examples decode with `pl.col("ts").cast(pl.Datetime("ns"))`, producing naive session times (e.g. stock `09:00:08`, TXFR1 kbar `08:46:00`). The docs do **not** name UTC, Asia/Taipei, or simulation vs production differences.

**Historical `api.ticks` / `api.kbars` raw `ts` (nanoseconds int):**

| Rule | Detail |
|------|--------|
| Decode | `trading_engine.calendar.shioaji_ts.shioaji_historical_ts_from_ns` — equivalent to official polars cast |
| Sim vs prod | Same encoding (verified 2026-06-25 TXFR1 sim + production) |
| Tick vs kbar ns | Raw ns may differ by 28800s; wall-clock decode aligns prices; 1m kbar `ts` is **bar-end** (+1 min vs tick minute) |

**Live streaming `TickFOPv1.datetime`:**

- SDK provides naive exchange wall clock; `adapters/shioaji_live.tick_to_snapshot` uses it directly — **do not** pass through `shioaji_historical_ts_from_ns`.

**Anti-patterns (do not use on historical raw ns):**

- `datetime.fromtimestamp(ns, TAIWAN_TZ)` (+8) — shifts 08:45 → 16:45
- Split rules (sim tick wall / kbar +8) — empirically wrong
- Different decode in `select_recent_trading_days_closes` vs backfill loaders

**Legacy cache migration (our bug, not Shioaji):** read paths perform **no** time correction — CSV cache on disk is the single source of truth and is read verbatim. Any pre-fix file written before 2026-06-26 with the +8 decode must be deleted and re-fetched (`--overwrite`, or `rm tick_cache/*.csv*` then `python -m backfilldata ...`); the corrected `shioaji_historical_ts_from_ns` decoder lands clean wall-clock times. Old kbar CSV with wrong times must likewise be re-fetched with `--overwrite`.

**Session / premarket**

- `exchange_time.is_trading_session(dt, SESSION_START, SESSION_END)` gates **decision** (`on_tick`).
- Premarket ticks may still run matching + pending timeout（見 backtest SPEC）。

**Audit lines**（determinism gate）

Kernel + telemetry emit `SIGNAL_AUDIT`, `FILL_AUDIT`, `DAILY_SUMMARY` — field semantics in app SPEC §Integration contracts.

**Tests**

- Kernel state machine, pending, session, risk gates — `python run_tests.py`（本 repo）
- Integration scenarios — [`docs/uat/KERNEL.md`](../../docs/uat/KERNEL.md) Phase B/C
