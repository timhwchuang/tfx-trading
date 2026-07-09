# storage — Market data cache (SSOT)

> **Parent**: [`apps/trading-app/SPEC.md`](../../SPEC.md) · **Monorepo**: [`SPEC.md`](../../../../SPEC.md) §7.3 Nautilus cache 借鏡

## Layout

| Path | Role |
|------|------|
| `tick_cache/{code}_{date}.csv` | 1m ticks (backfill / UAT archive) |
| `tick_cache/{code}_kbars_{date}.csv` | 1m kbars (backfill / kbar archiver) |
| `trade_days/{year}.json` | Taiwan calendar for trading-day resolution |

Loaders: `tick_loader.py`, `kbar_loader.py`. Audit/repair: `cache_audit.py`, `cache_repair.py`.

---

## SessionBarCache

NautilusTrader **cache 抽象**的落地：Research 與 Live 共用 **同一套多週期 K 線語意**（元大 / TradingView session 錨點）。v1 僅 in-proc library，不接 `kbar_archiver`。

### 落地 vs 記憶體

```
tick_cache/{code}_kbars_{date}.csv   ← 只存 1m（磁碟）
        ↓ SessionBarCache.load()
記憶體：1m / 3m / 5m / 15m / 30m / 1h / 4h + session 日 K + MA5/20/60
```

### Yuanta 錨點與收 K

| Session | 錨點 | 收盤時間戳範例 |
|---------|------|----------------|
| 日盤 | `08:45` | 1h → `09:45`…`13:45`；4h → `12:45`, `13:45` |
| 夜盤 | `15:00` | 4h → `19:00`, `23:00`, `03:00`, `05:00` |

- **收 K 時間戳 = bar 收盤時刻**（非 bucket 開盤）。
- 段尾不足整格仍產生一根（如 4h 日盤尾段 `13:45` 僅 1h）。
- 休市 `05:00–08:45`、`13:45–15:00` **不產 bar**（多週期 resample）。
- **結算尾棒**（磁碟偶見）：日盤 `13:46`、dawn `05:01` — 納入 session 日 K；日 K Close 取含 `13:46` 的最後一根。
- 夜盤開盤常缺 `15:00`，第一根多為 `15:01`。

### 假日 / 連假（元大「圖上無斷層」）

| 層面 | 規則 |
|------|------|
| **序列** | `closed[]` 僅含實際 bar；**index 連續**，不插 `null` / 佔位 |
| **時間戳** | 週五 → 週一可跳空 55h+；MA 用最近 N 根 **已存在** bar |
| **禁止** | 假日 forward-fill、合成 OHLC |

載入以 **`trade_days` 交易日** 為 lookback 單位；`missing_trading_days` 僅列 **交易日** 缺檔。

### 當日 kbar 檔就緒 (`TodayKbarStatus`)

**查詢單位 = 曆日 D**（非 on-disk 檔名）。`assess_calendar_day_readiness()` 為 SSOT；`assess_today_kbar_file()` / `SessionBarCache.today_status` / live `on_new_1m` 皆委派同一邏輯：

1. `kbar_file_dates_for_calendar_day(D)` 列舉可能含 `ts.date()==D` 的 bundle 候選檔
2. 計數前 filter `b.ts.date() == D`（bundle 檔常含多曆日）
3. `file_exists` = 任一候選檔存在 **或** 記憶體已有 D 的 bars

| 情境 | `ready` 條件 |
|------|----------------|
| **週六** | 檔案存在且凌晨 `00:00–05:00` ≥ **299** 根（`EXPECTED_DAWN_BARS=300`，±1） |
| **交易日**（日盤前僅 dawn） | 檔案存在且 dawn ≥ 299 → `reason=dawn_only_ok` |
| **交易日**（日盤中/後） | 檔案存在且日盤 `08:45–13:45` ≥ **299** 根 |
| 缺檔 | `ready=false`, `reason=missing_file` |
| 非交易日（週日/國定假日） | `ready=false`, `reason=not_trading_day` |

### 預設 TF 表

| key | minutes | lookback | session |
|-----|---------|----------|---------|
| 1m | 1 | 300 | day |
| 3m | 3 | 100 | day |
| 5m | 5 | 12 | day |
| 15m | 15 | 24 | both |
| 30m | 30 | 20 | both |
| 1h | 60 | 20 | both |
| 4h | 240 | 40 | both |

### Session 日 K 與 MA

- 一根 = **當日 15:00 → 次日 13:45**（例：7/7 15:00 開盤 → **7/8** 日 K）。
- **label = 13:45 收盤那天的交易日**（非 15:00 開盤日）。
- 週五 15:00 → 週一 13:45 收在同一根（label = 週一）；週六 dawn **不單獨成根**。
- `daily_closed()` lookback **90** 根。
- `daily_mas()` → `ma5`, `ma20`, `ma60`（SMA，不足根數 → `None`）。

### API

**底層** (`SessionBarCache`):

```python
cache = SessionBarCache.load("TMFR1", as_of=exchange_dt)
cache.closed("4h")
cache.current("5m")
cache.daily_mas()  # {"ma5": ..., "ma20": ..., "ma60": ...}
cache.today_status.ready
```

**門面** (`SessionBars` — 建議 live / 研究使用):

```python
bars = SessionBars.load("TMFR1", as_of=exchange_dt)
bars.get("4h")              # list[BarRecord]
bars.get("4h", 20)          # 最近 20 根
bars.get("4h", "last")      # 最後一根已收
bars.get("1m", "ma20")      # SMA(20)
bars.get("daily", "ma20")   # session 日 K MA20
bars.get("today")           # TodayKbarStatus
bars.series("4h", n=40)     # 顯式 list（SMC 研究用）
bars.on_bar(bar)            # live 增量
bars.reload()               # ATR refresh / 落盤後重載
```

### Live（tick → 1m → on_bar）

```
LIVE_BARS=1 python -m live
```

| 元件 | 職責 |
|------|------|
| `MinuteBarAggregator` | tick 增量聚 1m（分鐘 rollover 產 bar） |
| `LiveSessionBars` | 開盤 `SessionBars.load()`；收 K 時 `on_bar()` |
| `TradingAppArchivePort` | `enqueue_tick` 順便餵 live（**lock 外**，與 tick archive 同路徑） |

- `LIVE_KBAR_PERSIST=1`：每根 live 1m append 至 `{code}_kbars_{date}.csv`（僅 `Volume > 0`）
- gap-fill 合成 bar（`Volume=0`）不 persist、不 `on_bar`、不計入 `today_status`
- `refresh_atr` 後可 `live_bars.reload()` 與 API kbars 校正（可選）

SMC 多週期 stack **不在此模組**；另案研究。

**效能邊界**：`on_new_1m` 在鎖內對 1m tail 做 TF resample（O(tail)），屬 live hot path；全量 `_build()` 與 90 天 fixture 屬 load 路徑。慢整合測試（如 `test_daily_ma60`）需 `RUN_SLOW_STORAGE=1` 才執行。

### 與 `structure.py` 差異

`strategy_vwap_momentum.structure.resample_time_buckets` 用 **bucket 開盤** ts、分鐘整除 5m；SessionBarCache **不替換** FT-002 路徑，獨立 `yuanta_resample`。

---

## Implementation

- Module: [`session_bar_cache.py`](session_bar_cache.py)
- Tests: [`tests/storage/test_session_bar_cache.py`](../../tests/storage/test_session_bar_cache.py)