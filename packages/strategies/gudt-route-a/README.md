# GUDT Route A（`gudt_route_a`）

台指期 **洗盤日（GUDT）** 的 UAT 候選策略：把研究層已驗過的「Route A 多單 + 可選空單對沖」做成可在 **同一套 TradingEngine** 上回測與模擬下單的 plugin。

**不是** 已封板的 B′ 生產策略；上線前須過 parity 與人類 Go。

---

## 一句話

開盤跳空洗盤後，若當日符合 GUDT 條件，系統依 **離線算好的當日行程表** 在固定時間點送限價 IOC 進出場；live 與回測走同一顆 kernel。

---

## 什麼日子會交易？

必須同時滿足（由 wash probe / 開盤結構掃描決定，**不是** 策略在盤中即時判斷）：

| 條件 | 白話 |
|------|------|
| 有足夠 tick / K 線 | 當日資料完整，能算開盤結構 |
| 跳空夠大 | 開盤相對昨收跳空 ≥ 約 25 點，且相對當日 ATR 夠明顯 |
| 洗盤型態成立 | 早盤 drive 有回檔但不破結構（probe 內建規則） |
| 路由器有標的 | B′ 規則在當日 pick 出 **p0** 或 **flow_turn / reclaim_br** 等路徑，而非 skip |

不符合 → 當日 `skipped`，**零筆交易**。

---

## 進場怎麼選？（B′ + br5）

每日從 counterfactual 網格選一條 **主路徑**：

| 路徑 | 意思 |
|------|------|
| **p0 + sealed** | 早盤 sealed 突破多單（最常見） |
| **flow_turn + …** | 早盤 flow 轉折後多單 |
| **reclaim_br + …** | 洗回區間後的多單 |
| **skip** | 當日不做 |

**br5 濾網（僅 p0）**：若早盤買賣比 `pre_break_br` **低於 0.35**，視為假突破，**改走 flow_turn 備援**；備援也沒有 → 當日 skip。

可選 **chase 濾網**（預設關）：開盤追太高時不追 p0（`gudt_p0_ext_open_max`）。

---

## 持倉期間發生什麼？（Route A 多單）

依路徑不同，離線模擬器會算 **進場價、出場價、出場原因**：

**p0 路徑（預設 sealed）**

- 先走 15 分鐘 sealed 出場邏輯（含保本、止盈等）。
- **延伸條件**：若開盤延伸夠強（`ext_open > 5`）且 15 分鐘段仍賺錢，可 **延長持有到 60 分鐘**，出場改看 **5 分 K 的 EMA9 跌破 EMA21**（預設 `gudt_extension_exit: ema5` 對應研究裡的 EMA 延伸設定）。

**flow_turn / reclaim 路徑**

- 用對應的結構出場模擬（如 `drive_low_struct`），**沒有** p0 延伸。

---

## 什麼時候會翻空？（distribution flip）

僅在 **p0 多單** 且當日有開倉時，才可能：

1. 開盤延伸夠大（`ext_open > 5`）。
2. **信號**（約 P0+10 分）：價格跌破進場價且買賣比偏弱。
3. **確認**（約 P0+12 分）：跌幅夠深（`dump_atr ≤ −0.65`）且 2 分鐘斜率在 `−0.35 .. 0` 之間。

確認通過 → 平多後 **再開空單**（止損在 drive 高點上方），持有約 60 分鐘。  
確認不通過 → **只平多、不翻空**（研究裡常見的 confirm veto 日）。

---

## 回測 / live 實際怎麼跑？

本 package **不在盤中掃信號**，而是 **回放行程表**：

```
開盤前：bootstrap 讀 probe CSV → 為每一天生成 DayReplayPlan（一串 Buy/Sell 時間與價格）
盤中：  GudtRouteAStrategy 到了 ts 就下 IOC 限價單 → MockBroker / 券商撮合
```

與 **CF（counterfactual）** 的差異：CF 假設在 probe 價成交；kernel 用 **限價 IOC + 滑價 band**（`ioc_slippage_points`，baseline 目前 **6**），快行情可能 miss。

---

## 主要參數（`config.yaml` → `strategy_gudt_route_a`）

| 參數 | 預設 | 作用 |
|------|------|------|
| `gudt_pre_break_br_min` | 0.35 | p0 的 br5 門檻 |
| `gudt_flip_min_ext_open` | 5.0 | 允許延伸 / 翻空的開盤延伸下限 |
| `gudt_extension_exit` | `ema5` | p0 延伸段出場方式 |
| `gudt_confirm_min_dump_atr` | 0.65 | 翻空確認：跌幅（ATR 倍數） |
| `gudt_confirm_slope2_min/max` | −0.35 / 0 | 翻空確認：2 分鐘斜率區間 |
| `gudt_friction_points` | 5.0 | 研究層每趟摩擦（點） |
| `ioc_slippage_points` | 6 | 進出場限價相對信號價的讓價 band |

完整列表見 [`src/strategy_gudt_route_a/params.py`](src/strategy_gudt_route_a/params.py)。

---

## 怎麼跑？

**Workspace（UAT 預設）**：[`workspaces/gudt-route-a-baseline/README.md`](../../../workspaces/gudt-route-a-baseline/README.md)

```bash
cd apps/trading-app/src
CONFIG_PATH=../../../workspaces/gudt-route-a-baseline/config/config.yaml \
  python scripts/ft021_run_baseline.py --slice UAT_2m

# 執行層 parity（n 一致 + net 對照）
python scripts/ft021_execution_parity.py --slice UAT_2m --append-spot-log
```

**模擬 live（2026-07-02 起 UAT）**

```bash
CONFIG_PATH=../../../workspaces/gudt-route-a-baseline/config/config.yaml \
  python -m live
```

---

## 驗收看什麼？

| 層級 | 工具 | 硬條件 |
|------|------|--------|
| 決策 | `ft021_parity_check.py` | 每日 skip/路徑/flip 與 CF 一致 |
| 執行 | `ft021_execution_parity.py` | **成交趟數 n 一致**（CF plan = kernel fills） |
| 績效 | 同上 + baseline JSON | net 差異 **警告**（出場 IOC / flatten 造成，不擋 n） |

研究數字 SSOT：[`workspaces/gudt-baseline/ROUTE_A_UAT_STACK.md`](../../../workspaces/gudt-baseline/ROUTE_A_UAT_STACK.md)

---

## 程式入口

| 模組 | 用途 |
|------|------|
| [`strategy.py`](src/strategy_gudt_route_a/strategy.py) | `GudtRouteAStrategy` — 回放行程表 |
| [`stack.py`](src/strategy_gudt_route_a/stack.py) | CF 側：選路徑、算 net、flip |
| [`replay.py`](src/strategy_gudt_route_a/replay.py) | pick → `DayReplayPlan` |
| [`params.py`](src/strategy_gudt_route_a/params.py) | 參數綁定 |

行程表由 trading-app 的 `integrations/gudt_replay_planner.py` 在 backtest/live 開盤前建立。

---

## 文件

- **本 package 契約**：[`SPEC.md`](SPEC.md)（簡短、自包含）
- **研究規格與歷史回測表**：[`ROUTE_A_UAT_STACK.md`](../../../workspaces/gudt-baseline/ROUTE_A_UAT_STACK.md)
- **功能票據（FT-021）**：[`docs/features/gudt-route-a/SPEC.md`](../../../docs/features/gudt-route-a/SPEC.md)
