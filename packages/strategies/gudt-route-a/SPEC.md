# strategy-gudt-route-a — Package SPEC

**Config 名稱**：`gudt_route_a`  
**類別**：`GudtRouteAStrategy`  
**狀態**：UAT 候選（2026-07-02 起模擬盤驗證）

人話版說明、參數表、怎麼跑 → **[`README.md`](README.md)**（請先看這份）。

---

## 1. 責任邊界

| 做 | 不做 |
|----|------|
| 依 `DayReplayPlan` 在指定 `ts` 送 Buy/Sell | 盤中即時掃 GUDT / 洗盤型態 |
| 與 TradingEngine 共用 pending / IOC / flatten | 改寫 B′ sealed 或 br5 研究參數 |
| 回測與 live 同一套 evaluate 路徑 | 保證成交價等於 CF probe 價 |

**行程表來源**：trading-app `bootstrap_gudt_route_a` → `gudt_replay_planner`（讀 wash probe CSV + 當日 tick 上下文）。

---

## 2. 策略行為（v1 = Route A UAT stack）

### 2.1 當日是否交易

由 **離線** wash probe + `rule_pick_for_day` 決定；策略只讀 `DayReplayPlan.skipped`。

### 2.2 多單（Leg 1）

- **Router**：B′ + br5（p0 且 `pre_break_br < 0.35` → fallback flow_turn，否則 skip）。
- **p0**：sealed 15m 出場；符合延伸條件時延至 60m + 5m EMA 破線出場。
- **非 p0**：`flow_turn` / `reclaim_br` + 結構出場（如 `drive_low_struct`）。

### 2.3 翻空（Leg 2，可選）

僅 p0 多單且 `ext_open > 5`：信號 + 結構確認通過 → 平多後開空；否則只平多。

數值門檻見 `GudtRouteAParams` / workspace `config.yaml`。

### 2.4 `reset()`

Engine 在進場成交後會呼叫 `reset()`；本策略為 **no-op**，避免當日行程表游標被 rewind（UAT 必修項）。

---

## 3. Parity（驗收）

| Gate | 腳本 | Pass 條件 |
|------|------|-----------|
| 決策 | `ft021_parity_check.py` | 路徑 / skip / flip 與 CF 一致 |
| 執行 | `ft021_execution_parity.py` | `cf_round_count == kernel_round_count` |
| 績效 | 同上 `net_delta` | **warn-only**（不擋 Pass） |

預設 UAT slice：`UAT_2m`（2026-05-01 .. 2026-06-30）。  
產物：`workspaces/gudt-route-a-baseline/reports/execution_parity_{label}.json`

研究對照數字（CF net、flip 次數等）：[`workspaces/gudt-baseline/ROUTE_A_UAT_STACK.md`](../../../workspaces/gudt-baseline/ROUTE_A_UAT_STACK.md)

---

## 4. 設定

Workspace SSOT：[`workspaces/gudt-route-a-baseline/config/config.yaml`](../../../workspaces/gudt-route-a-baseline/config/config.yaml)

| 區塊 | 說明 |
|------|------|
| `strategy.name: gudt_route_a` | 載入本 plugin |
| `strategy.gudt_*` | 堆參數（見 README 表） |
| `ioc_slippage_points` | 執行層讓價（目前 6） |
| `session.*` | 08:45–13:45，13:40 flatten |

---

## 5. 測試

```bash
cd packages/strategies/gudt-route-a
PYTHONPATH="src:../../trading-engine/src" python -m unittest discover -s tests -p "test_*.py"
```

含 `test_strategy_replay.py`（`reset()` no-op、flatten 後不重進場）。

---

## 6. 相關文件（各一份，不重複引用）

| 文件 | 內容 |
|------|------|
| [`README.md`](README.md) | 策略說明（開發/UAT 必讀） |
| [`workspaces/gudt-route-a-baseline/README.md`](../../../workspaces/gudt-route-a-baseline/README.md) | 回測 / parity 指令 |
| [`docs/features/gudt-route-a/SPEC.md`](../../../docs/features/gudt-route-a/SPEC.md) | FT-021 功能票據與範圍 |
| [`ROUTE_A_UAT_STACK.md`](../../../workspaces/gudt-baseline/ROUTE_A_UAT_STACK.md) | 研究結果與區間損益表 |
