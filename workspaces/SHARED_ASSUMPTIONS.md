# FT-003 共享假設（SHARED_ASSUMPTIONS）

| 欄位 | 值 |
|------|-----|
| **版本** | **v1.1** |
| **更新日期** | 2026-06-26 |

> **SSOT**：所有調參 agent **開工前 MUST 讀**；`grid.json` 邊界與 `analysis.md` 假說須與本檔一致。  
> 違反本檔假設的 grid 視為 **invalid**，不得進入 leaderboard。  
> **版本升級時**：所有進行中 agent 須在 `analysis.md` §1 更新合規聲明至新版本。

## 1. 合約與商品

| 項目 | 假設 |
|------|------|
| 商品 | **TMFR1** 微台指期 |
| Pilot 口數 | **qty=1**（多口管理未完成，見 `docs/AGENTS.md` §8） |
| 時間源 | **交易所時間**（`exchange_time.py`）；日切與 session 以交易所為準 |
| 資料 | `tick_cache/` 2026-01～05（見 [`DATA_SPLIT.md`](DATA_SPLIT.md)） |

## 2. 回測 vs Live（不可混淆）

同一 `tick_cache` 下，UAT live 與 backtest 共用 `TradingEngine` + 同一 strategy plugin — **決策路徑高度一致**。

**績效數字不可直接等同**（詳 [`packages/trading-backtest/SPEC.md`](../packages/trading-backtest/SPEC.md) §8–§9）：

| 可轉移 | 不可直接轉移 |
|--------|----------------|
| 狀態機、audit 語意 | next-tick close 撮合 vs 真實 queue |
| Session / flatten / 日虧停新進場 | 部分成交、callback 延遲 jitter |
| 確定性 regression | 固定 tier 滑價 vs 券商實際 fill |
| | 手續費 / 稅（`friction` net；見 §3.1） |

**MUST**：所有 agent 在 analysis 中區分「相對排序 / 假說驗證」與「live 獲利預測」。**競賽 KPI（`valid_score`、`expectancy_net`）一律以 friction **enabled** 的 net 為準**（v1.1 起）。

## 3. 摩擦、滑價與執行

### 3.1 TMFR1 固定摩擦（MUST — 回測 / sweep / UAT 報表）

微台 **qty=1**、**1 點 = 10 NTD** 前提下，每筆 completed round-trip（一進一出）：

| 項目 | NTD | 點數 |
|------|-----|------|
| 手續費（單邊 15 × 2） | 30 | 3.0 |
| 交易稅（估算） | 20 | 2.0 |
| **合計** | **50** | **5.0** |

**Config SSOT**（`friction.enabled: true`）：

```yaml
friction:
  enabled: true
  mode: ntd
  commission_per_side_ntd: 15.0
  tax_rate: 20.0              # ntd 模式：單趟 round-trip 交易稅（NTD）
  point_value_ntd: 10.0
  round_trip_friction_points: 5.0  # flat 模式備用
```

實作：`reporting.performance_metrics.friction_per_round_trip`；寫入 DAILY_SUMMARY `performance.total_pnl_net` / `expectancy_net`。  
**不**改 MockBroker 撮合價；摩擦僅在績效結算扣除。券商 VIP / 稅率變動時更新本節並 bump SHARED_ASSUMPTIONS 版本。

### 3.2 滑價與執行（研究 grid）

| 項目 | 回測假設 | Live / UAT 現實 |
|------|----------|-----------------|
| 撮合 | MockBroker next-tick + 固定 slippage tier | 券商 queue、部分成交 |
| `ioc_slippage_points` | **研究用** grid 可調（agent-execution） | Live 開盤 IOC 讓價維持 **±3 點** 風控意識；勿為成交率無腦放大 |
| `pending_timeout_sec` | 回測 sync 模式解讀需保守 | UAT 實測 callback 延遲可能更長 |
| 秒停損 | `quick_stop_loss_rate` = exit 中極短持倉停損比例 | Pilot **硬 KPI**；回測可預演但不可替代 UAT |
| Net KPI | `performance` 區塊；**摩擦 5 點/趟已扣**（§3.1） | Pilot 以券商帳戶對帳為準 |

**Phase 1 Pass 後**：建議 `compare_fill_audits` 校準滑價假設（寫入 execution agent 協作備註）。

## 4. ATR、波動與市況

| 項目 | 說明 |
|------|------|
| `min_atr_threshold` | 低 ATR 平淡市況濾網；提高 → 交易次數 ↓、可能錯過趨勢 |
| ATR 來源 | kbars 快取（`tick_cache/{code}_kbars_{date}.csv`）；sweep 前 `cache_audit` PASS |
| 平淡市況 | 微台低 ATR 日可能整天無交易 — **樣本不足** 不得宣稱勝利 |
| Regime filter | Phase 6 旗標預設 **關**；regime agent 不得建議 Pilot 直接開 filter |

## 5. 流動性與微結構（台指期）

- **開盤前 15 分鐘**：價差與 IOC 取消率較高；回測 fill 可能偏樂觀。
- **午盤後段**：流動性通常優於開盤；但劇烈波動日仍可能秒停損。
- **微台 vs 大台**：本 ft 僅 TMFR1；流動性假設不可直接外推 TXF。
- **單口**：不考慮自身下單對 order book 的市場衝擊。

## 6. 資料切分（所有 agent 共用）

見 [`DATA_SPLIT.md`](DATA_SPLIT.md)：

- **Train** 2026-01～03：in-sample 診斷
- **Valid** 2026-04：競賽排名唯一依據
- **Holdout** 2026-05：封印至 Phase 4；`holdout_guard` 程式擋住

禁止把 1～5 月合併當 in-sample 調參。

## 7. 跨 Agent 參數邊界（避免重複 tune / 矛盾）

| Agent | 主軸 keys | 禁止主軸 tune |
|-------|-----------|---------------|
| `agent-conservative` | `min_atr_threshold`, `entry_band_points`, `momentum_vol_1s` | IOC / trail 主軸、Phase 6 旗標 |
| `agent-execution` | `ioc_slippage_points`, `trail_points`, `pending_timeout_sec` | `min_atr_threshold` 主軸 |
| `agent-risk-exit` | `fixed_tp_points`, `trail_points`, `max_consecutive_loss` | 放大 `max_daily_loss_points` 換 PnL |
| `agent-regime` | trend **或** structure 線（互斥） | 同時開兩種 filter |

**合併 config 時**：若 conservative 提高 `min_atr_threshold` 而 execution 放寬 `ioc_slippage_points`，須在 peer_review 註明是否邏輯衝突。

## 8. 引用

- Agent 編制：[`docs/features/ai-backtest-tuning/AGENT_ROSTER.md`](../docs/features/ai-backtest-tuning/AGENT_ROSTER.md)
- Overfitting 協議：[`SPEC.md`](../docs/features/ai-backtest-tuning/SPEC.md) §4
- 交易員身份：[`prompts/roles/senior-trading-professional.md`](../prompts/roles/senior-trading-professional.md)

## 9. 版本紀錄

| 版本 | 日期 | 變更 |
|------|------|------|
| v1.0 | 2026-06-26 | 初版 |
| v1.1 | 2026-06-26 | TMFR1 摩擦 5 點/趟（手續費 30 + 稅 20 NTD）上線；KPI 以 net 為準 |
