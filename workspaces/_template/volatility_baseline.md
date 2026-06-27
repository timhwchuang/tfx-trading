# VOLATILITY_BASELINE — FT-003 Phase 3.6

**商品**：TMFR1  
**資料區間**：YYYY-MM-DD ～ YYYY-MM-DD（`tick_cache` kbars）  
**產生時間**：YYYY-MM-DD（`ft003_volatility_baseline.py`）  
**Config 對照**：`hard_stop_points` / `trail_points` / `fixed_tp_points` / `min_atr_threshold` / `entry_band_points` / `momentum_vol_1s` / `exhaustion_vol` / `momentum_timeout_sec`（來源路徑）

> **診斷 only** — 禁止用於本輪 leaderboard 選參。契約：[`SPEC.md`](../docs/features/ai-backtest-tuning/SPEC.md) §4.6。  
> **四平面**：§A/B 尺度 · **§C 進場漏斗** · §D 出場 · §E/F 附錄。Methods：[`ENTRY_FUNNEL_METRICS.md`](../docs/features/ai-backtest-tuning/ENTRY_FUNNEL_METRICS.md)。

---

## A. 月度波動（P0 — kbars）

| 月 | 交易日 | Close med | 1m range p50 | p90 | max | ATR20 p50 | p90 | stop_ratio | trail_ratio | tp_ratio | range_ratio |
|----|--------|-----------|--------------|-----|-----|-----------|-----|------------|-------------|----------|-------------|
| | | | | | | | | | | | |

**解讀**（交易員填寫）：

---

## B. 量能與價差（P1 — tick，可選 `--ticks`）

| 月 | vol_1s p50 | p90 | p99 | spread p50 | p90 | momentum_vol_1s 百分位 | exhaustion_vol 百分位 |
|----|------------|-----|-----|------------|-----|------------------------|----------------------|
| | | | | | | | |

Config 對照：`momentum_vol_1s`=___，`exhaustion_vol`=___

---

## C. 進場漏斗（P0 — baseline valid log + tick）

**Agent / log / 區間**：（例 `agent-conservative` / `logs/baseline_valid.log` / 2026-04 valid）

### C.1 vol_1s 門檻分位

| 指標 | 值 | 備註 |
|------|-----|------|
| P(vol_1s ≥ threshold) | | 全樣本或 valid 月 |
| P(vol_1s ≤ exhaustion_vol) | | |
| vol_1s_at_arm p50 / p90 | | armed cohort |

### C.2 armed 順勢窗口（固定 Δt：30 / 60 / 180 秒）

| Outcome | N | W30 close_delta med | W60 | W180 | MFE_180 med | MAE_180 med |
|---------|---|---------------------|-----|------|-------------|-------------|
| entered | | | | | | |
| timeout | | | | | | |
| trend_veto | | | | | | |
| （其他） | | | | | | |

> 順勢 ≠ net edge；解讀見 ENTRY_FUNNEL_METRICS §1.3、§4.6。

### C.3 回踩漏斗轉化率

| 階段 | count | % of armed |
|------|-------|------------|
| armed | | 100% |
| ever_near_vwap | | |
| ever_vol_dried | | |
| both_same_tick | | |
| entered | | |
| timeout | | |

### C.4 timeout 與 time_to_first_band

| 指標 | 值 |
|------|-----|
| timeout_rate | |
| timeout 前從未 near_vwap 占比 | |
| time_to_first_band p50（秒） | |
| time_to_entry p50（entered 子集） | |
| pullback_depth_over_atr p50 | |

### C.5 near_miss（valid 月 **累計**）

| 指標 | 值 |
|------|-----|
| momentum_episodes | |
| momentum_timeout | |
| blocked_both | |
| blocked_vwap_only | |
| blocked_vol_only | |
| closest_vwap_distance (min) | |

> **方法論**：`blocked_*`、`momentum_*` 對 `daily_summaries` **sum**；`closest_vwap_distance` 取 **min**。不可僅取最後一日（見 ENTRY_FUNNEL_METRICS §5.3）。

---

## D. 出場診斷（P0 — baseline valid）

**Agent / report**：（例 `agent-conservative` / `reports/baseline_valid.json`）

### D.1 Exit reason 占比

| reason | count | % |
|--------|-------|---|
| | | |

### D.2 Expectancy by reason（毛點）

| reason | count | total_pnl | avg_pnl |
|--------|-------|-----------|---------|
| | | | |

> 毛點未扣 5 點/趟摩擦；net 見 SHARED_ASSUMPTIONS §3.1。

### D.3 秒停損與 hold_ticks（log）

| 指標 | 值 |
|------|-----|
| quick_stop_loss_rate | |
| stop_loss in_grace 占比 | |
| hold_ticks p50（exit） | |

### D.4 Near-miss 漏斗（單 report 頂層；月累計見 §C.5）

| 指標 | 值 |
|------|-----|
| blocked_both | |
| blocked_vwap_only | |
| blocked_vol_only | |
| closest_vwap_distance | |

---

## E. 常見誤讀提醒

- tick `close` 價位 ≠ 分鐘振幅點數
- `volume` / `vol_1s` 口數 ≠ 價格點數變動
- armed 後順勢 ≠ 策略 net 獲利（設計為等回踩，不追價）

---

## F. 機器可讀

- `workspaces/reports/volatility_baseline.json`
- `workspaces/reports/entry_funnel.json`（§C，`ft003_episode_diagnosis.py` pending）
