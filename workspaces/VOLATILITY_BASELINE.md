# VOLATILITY_BASELINE — FT-003 Phase 3.6

**商品**：TMFR1  
**資料區間**：2026-01-01 ～ 2026-05-31  
**產生時間**：2026-06-27  
**ATR**：sma_tr (period=20)  
**Config 對照**：hard_stop=6.0, trail=8.0, tp=20.0, min_atr=25.0

> **診斷 only** — 禁止用於本輪 leaderboard 選參。契約：[`SPEC.md`](../docs/features/ai-backtest-tuning/SPEC.md) §4.6。
> **2026-05** 列僅供 holdout 風險敘事，禁止回頭 tune grid。

---

## A. 月度波動（P0 — kbars）

| 月 | 角色 | 交易日 | Close med | 1m range p50 | p90 | max | ATR20 p50 | p90 | 1m Vol p50 | stop_ratio | trail_ratio | tp_ratio | range_ratio |
|----|------|--------|-----------|--------------|-----|-----|-----------|-----|------------|------------|-------------|----------|-------------|
| 2026-01 | train_or_diagnostic | 21 | 31301 | 15.0 | 32 | 111 | 15.7 | 29 | 196 | 0.38 | 0.51 | 1.27 | 0.40 |
| 2026-02 | train_or_diagnostic | 11 | 32648 | 20.0 | 42 | 129 | 21.8 | 37 | 268 | 0.28 | 0.37 | 0.92 | 0.30 |
| 2026-03 | train_or_diagnostic | 22 | 33507 | 32.0 | 67 | 313 | 34.0 | 58 | 404 | 0.18 | 0.24 | 0.59 | 0.19 |
| 2026-04 | valid | 20 | 37250 | 25.0 | 58 | 296 | 25.7 | 51 | 299 | 0.23 | 0.31 | 0.78 | 0.24 |
| 2026-05 | holdout_narrative_only | 20 | 41896 | 32.0 | 69 | 304 | 33.8 | 63 | 378 | 0.18 | 0.24 | 0.59 | 0.19 |

**解讀**（交易員填寫）：

固定點數出場（HS6 / trail8 / TP20）相對 ATR p50 的 `stop_ratio` 自 1 月 **38%** 降至 3–5 月 **18–23%**。`momentum_vol_1s=150` 在隨機 1s bar 上僅 **~0.2%** ≥門檻（§B.1）— 屬事件型爆量門檻。4 月 valid ATR p50≈25.7、5 月 holdout≈33.8（僅風險敘事）。
---

## B. 量能（P1 — tick）

| 月 | 角色 | vol_1s p50 | p90 | p99 | spread p50 | spread p90 |
|----|------|------------|-----|-----|------------|------------|
| 2026-01 | train_or_diagnostic | 3 | 14 | 61 | 2.0 | 3.0 |
| 2026-02 | train_or_diagnostic | 4 | 17 | 61 | 2.0 | 3.0 |
| 2026-03 | train_or_diagnostic | 6 | 23 | 74 | 3.0 | 4.0 |
| 2026-04 | valid | 4 | 20 | 77 | 3.0 | 5.0 |
| 2026-05 | holdout_narrative_only | 5 | 22 | 80 | 3.0 | 5.0 |

### B.1 Config 門檻覆蓋率（vol_1s 樣本）

| 門檻 | 值 | 樣本占比 | 備註 |
|------|-----|----------|------|
| momentum_vol_1s (floor) | 150.0 | ≥門檻 0.2% · ≤門檻 99.8% | n=1383814 |
| exhaustion_vol (ceiling) | 15.0 | ≤門檻 85.6% | 量能枯竭判定 |

---

---

## C. 進場漏斗（P0 — baseline valid log + tick）

**Agent / log / 區間**：`agent-conservative` / `workspaces/agent-conservative/logs/baseline_valid.log` / 2026-04-01～2026-04-30

### C.1 vol_1s 門檻分位

| 指標 | 值 | 備註 |
|------|-----|------|
| P(vol_1s ≥ threshold) | 0.3% | threshold=150.0 |
| P(vol_1s ≤ exhaustion_vol) | 85.7% | exhaustion=15.0 |
| vol_1s_at_arm p50 / p90 | 153.0 / 227.0 | armed cohort |

### C.2 armed 順勢窗口（固定 Δt：30 / 60 / 180 秒）

> armed 後順勢位移 ≠ 策略 net edge（設計為等回踩，不追價）。見 ENTRY_FUNNEL_METRICS §1.3。

| Outcome | N | W30 close_delta med | W60 | W180 | MFE_180 med | MAE_180 med |
|---------|---|---------------------|-----|------|-------------|-------------|
| entered | 150 | -5.00 | -7.00 | -15.00 | 28.00 | 41.50 |
| timeout | 85 | 10.00 | 13.00 | 35.00 | 69.00 | 23.00 |

### C.3 回踩漏斗轉化率

> 回踩漏斗以 `IndicatorState` tick 回放（與 engine VWAP/vol_1s 語意一致）。

| 階段 | count | % of armed |
|------|-------|------------|
| armed | 235 | 100.0% |
| ever_near_vwap | 178 | 75.7% |
| ever_vol_dried | 235 | 100.0% |
| both_same_tick | 152 | 64.7% |
| entered | 150 | 63.8% |
| timeout | 85 | 36.2% |

### C.4 timeout 與 time_to_first_band

| 指標 | 值 |
|------|-----|
| timeout_rate | 36.2% |
| timeout 前從未 near_vwap 占比 | 67.1% |
| time_to_first_band p50（秒） | 72.0 |
| time_to_entry p50（entered 子集） | 78.5 |
| pullback_depth p50 | 25.0 |

### C.5 near_miss（valid 月 **累計**）

> `blocked_*` / `momentum_*` 對 daily_summaries **sum**；`closest_vwap_distance` 取 **min**。 跨 **20** 個交易日。

| 指標 | 值 |
|------|-----|
| momentum_episodes | 235 |
| momentum_timeout | 85 |
| blocked_both | 309164 |
| blocked_vwap_only | 56619 |
| blocked_vol_only | 2130 |
| closest_vwap_distance | 0.0 |

---

## D. 出場診斷（P0 — baseline valid）

**Agent / report**：`agent-conservative` / `workspaces/agent-conservative/reports/baseline_valid.json`

### D.1 Exit reason 占比

| reason | count | % |
|--------|-------|---|
| trailing_stop | 84 | 53.2% |
| stop_loss | 57 | 36.1% |
| take_profit | 17 | 10.8% |

### D.2 Expectancy by reason（毛點）

> §D.2 為 **毛點**（gross）；TMFR1 摩擦 **5 點/趟** 見 [`SHARED_ASSUMPTIONS.md`](SHARED_ASSUMPTIONS.md) §3.1。

| reason | count | total_pnl | avg_pnl |
|--------|-------|-----------|---------|
| stop_loss | 55 | -351.0 | -6.38 |
| trailing_stop | 77 | 1.0 | 0.01 |
| take_profit | 16 | 329.5 | 20.59 |

**Integrity warnings**：
- exit_reasons['trailing_stop']=84 vs expectancy_by_reason.count=77
- exit_reasons['stop_loss']=57 vs expectancy_by_reason.count=55
- exit_reasons['take_profit']=17 vs expectancy_by_reason.count=16

### D.3 秒停損與 hold_ticks

| 指標 | 值 |
|------|-----|
| quick_stop_loss_rate | 33.3% |
| stop_loss in_grace 占比 | 100.0% |
| hold_ticks p50（exit audit） | 21 |

> `in_grace` 期間 **hard stop 仍會觸發**（保護期內不啟用 VWAP 停損）；此占比為 exit audit 中 `reason=stop_loss` 且 `in_grace=true` 的比例。

### D.4 Near-miss 漏斗

（跨 **20** 個交易日加總；非最後一日 snapshot）

| 指標 | 值 |
|------|-----|
| momentum_episodes | 235 |
| momentum_timeout | 85 |
| blocked_both | 309164 |
| blocked_vwap_only | 56619 |
| blocked_vol_only | 2130 |
| closest_vwap_distance | 0.0 |

**Agent / report**：`agent-execution` / `workspaces/agent-execution/reports/baseline_valid.json`

### D.1 Exit reason 占比

| reason | count | % |
|--------|-------|---|
| trailing_stop | 84 | 53.2% |
| stop_loss | 57 | 36.1% |
| take_profit | 17 | 10.8% |

### D.2 Expectancy by reason（毛點）

> §D.2 為 **毛點**（gross）；TMFR1 摩擦 **5 點/趟** 見 [`SHARED_ASSUMPTIONS.md`](SHARED_ASSUMPTIONS.md) §3.1。

| reason | count | total_pnl | avg_pnl |
|--------|-------|-----------|---------|
| stop_loss | 55 | -351.0 | -6.38 |
| trailing_stop | 77 | 1.0 | 0.01 |
| take_profit | 16 | 329.5 | 20.59 |

**Integrity warnings**：
- exit_reasons['trailing_stop']=84 vs expectancy_by_reason.count=77
- exit_reasons['stop_loss']=57 vs expectancy_by_reason.count=55
- exit_reasons['take_profit']=17 vs expectancy_by_reason.count=16

### D.3 秒停損與 hold_ticks

| 指標 | 值 |
|------|-----|
| quick_stop_loss_rate | 33.3% |
| stop_loss in_grace 占比 | 100.0% |
| hold_ticks p50（exit audit） | 21 |

> `in_grace` 期間 **hard stop 仍會觸發**（保護期內不啟用 VWAP 停損）；此占比為 exit audit 中 `reason=stop_loss` 且 `in_grace=true` 的比例。

### D.4 Near-miss 漏斗

（跨 **20** 個交易日加總；非最後一日 snapshot）

| 指標 | 值 |
|------|-----|
| momentum_episodes | 235 |
| momentum_timeout | 85 |
| blocked_both | 309164 |
| blocked_vwap_only | 56619 |
| blocked_vol_only | 2130 |
| closest_vwap_distance | 0.0 |

**Agent / report**：`agent-risk-exit` / `workspaces/agent-risk-exit/reports/baseline_valid.json`

### D.1 Exit reason 占比

| reason | count | % |
|--------|-------|---|
| trailing_stop | 84 | 53.2% |
| stop_loss | 57 | 36.1% |
| take_profit | 17 | 10.8% |

### D.2 Expectancy by reason（毛點）

> §D.2 為 **毛點**（gross）；TMFR1 摩擦 **5 點/趟** 見 [`SHARED_ASSUMPTIONS.md`](SHARED_ASSUMPTIONS.md) §3.1。

| reason | count | total_pnl | avg_pnl |
|--------|-------|-----------|---------|
| stop_loss | 55 | -351.0 | -6.38 |
| trailing_stop | 77 | 1.0 | 0.01 |
| take_profit | 16 | 329.5 | 20.59 |

**Integrity warnings**：
- exit_reasons['trailing_stop']=84 vs expectancy_by_reason.count=77
- exit_reasons['stop_loss']=57 vs expectancy_by_reason.count=55
- exit_reasons['take_profit']=17 vs expectancy_by_reason.count=16

### D.3 秒停損與 hold_ticks

| 指標 | 值 |
|------|-----|
| quick_stop_loss_rate | 33.3% |
| stop_loss in_grace 占比 | 100.0% |
| hold_ticks p50（exit audit） | 21 |

> `in_grace` 期間 **hard stop 仍會觸發**（保護期內不啟用 VWAP 停損）；此占比為 exit audit 中 `reason=stop_loss` 且 `in_grace=true` 的比例。

### D.4 Near-miss 漏斗

（跨 **20** 個交易日加總；非最後一日 snapshot）

| 指標 | 值 |
|------|-----|
| momentum_episodes | 235 |
| momentum_timeout | 85 |
| blocked_both | 309164 |
| blocked_vwap_only | 56619 |
| blocked_vol_only | 2130 |
| closest_vwap_distance | 0.0 |
---

## E. 常見誤讀提醒

tick close price level is NOT minute range in points; volume is contracts not price amplitude

---

## F. 機器可讀

`workspaces/reports/volatility_baseline.json`

schema_version=1 · atr_method=sma_tr
