# Strategy Plugin Spec — strategy-vwap-momentum

> **Package**: `strategy-vwap-momentum` · **Import**: `strategy_vwap_momentum`  
> **第一個公開 reference `strategy-<name>`**（依據 `strategy/SPEC.md` 與 `docs/three-repo/README.md`）  
> 使用者入口：[README.md](README.md) · 契約 source of truth：`trading_engine.core.strategy`（trading-engine） · 完整參數與邏輯：本文

**一句話**：這是 trading-engine 社群第一個參考實作的 VWAP momentum pullback + 高時間框架 trend 濾網 + ATR 動態出場策略 plugin。**僅供學術研究與個人學習**。

## 1. 定位

本 package 實作一個**可插拔的決策模組**，被 `TradingEngine`（live）與 `BacktestEngine`（replay）以同一 `Strategy` Protocol 注入。

**不碰**：券商連線、下單狀態機、tick replay、存檔、alert、報表、參數 sweep 編排。  
**只回答**：這個 tick 要不要進場 / 出場？用什麼 audit 資訊？

## 2. 與 trading-engine / trading-backtest 的關係（鐵律）

- 依賴方向：`strategy-vwap-momentum` → `trading-engine`（僅公開 core）
- **禁止** import `trading_backtest`、`shioaji`、任何 app 層（`trading-app` 等）
- 同一 `TradingEngine` 狀態機同時服務 live 與 backtest
- Protocol 演進由 trading-engine 帶動（breaking 會 major bump）

## 3. Strategy Protocol 實作現況（trading-engine 0.2.2+）

必須實作（來自 `trading_engine.core.strategy`）：
- `evaluate(market, position, risk, vol_threshold, *, session_force_flatten_time, max_daily_loss_points, on_daily_loss_block) -> (OrderSignal | None, StrategySideEffects)`
- `reset() -> None`

本 plugin 額外提供（非 Protocol 要求，屬 plugin 內部 + 相容）：
- `manage_exit(...)`
- `build_entry_audit(...)` / `build_exit_audit(...)`
- `session_force_flatten_signal(...)`
- `MomentumState` + 相關方法（**完全留在 plugin 內部**，不污染 Protocol）

詳見 trading-engine `docs/STRATEGY.md` 與 `core/strategy.py`。

## 4. 公開參數面（StrategyParams）

所有參數透過 `RuntimeConfig` overlay 即時讀取（支援 sweep / patch 做研究校準）。

| 參數屬性                    | 對應 config key (大概)       | 語意與影響 |
|-----------------------------|------------------------------|----------|
| `entry_band_points`         | ENTRY_BAND_POINTS           | 進場時「夠靠近 VWAP」的寬度（點數） |
| `vwap_stop_points`          | VWAP_STOP_POINTS            | 基礎 VWAP 停損距離（可被 ATR 動態放大） |
| `exhaustion_vol`            | EXHAUSTION_VOL              | pullback 進場所需「量能枯竭」門檻 |
| `exit_grace_ticks` / `exit_grace_sec` | EXIT_GRACE_*          | 進場後 grace 期間只認 hard stop，忽略 VWAP stop |
| `fixed_tp_points`           | FIXED_TP_POINTS             | 固定止盈距離 |
| `trail_points`              | TRAIL_POINTS                | 基礎移動停損距離（可 ATR 動態） |
| `hard_stop_points`          | HARD_STOP_POINTS            | 硬停損（進場價 +/-） |
| `momentum_buy_ratio` / `momentum_sell_ratio` | MOMENTUM_*_RATIO | 啟動 momentum 所需的 1s 買/賣量比門檻 |
| `min_atr_threshold`         | MIN_ATR_THRESHOLD           | 進場前 ATR 過低直接擋（避免無趨勢區間） |
| `max_consecutive_loss`      | MAX_CONSECUTIVE_LOSS        | 連續虧損次數上限（kernel 層也會擋） |
| `atr_trailing_enabled` / `atr_vwap_stop_enabled` | ATR_*_ENABLED | 是否啟用 ATR 動態 trail / vwap stop |
| `trail_points_floor` / `trail_atr_k` 等 | *_FLOOR / *_ATR_K | ATR 動態計算的下限與倍數 |
| `trend_filter_enabled`      | TREND_FILTER_ENABLED        | 是否開啟 P6-1 高時間框架趨勢濾網 |
| `flatten_slippage_points`   | FLATTEN_SLIPPAGE_POINTS     | 收盤強制平倉的滑價（僅供 audit） |

詳細預設值與校準流程見 [docs/CALIBRATION.md](docs/CALIBRATION.md) 與 consuming app `config/config.yaml`。**本 package 不硬塞預設值**，全部來自 RuntimeConfig。

## 5. 核心決策流程（高層）

1. **Momentum 啟動**（`_try_activate_momentum`）
   - 無持倉 + 非 pending + 交易時段 + ATR 足夠 + 連續虧損未達上限
   - `vol_1s >= threshold` 且 `buy_ratio >= momentum_buy_ratio` → 啟動 Long momentum（記錄 trigger 價、時間）
   - 同理 Short。

2. **Pullback 進場**（`_try_pullback_entry`）
   - momentum 已 active 且未超時（`momentum_timeout_sec`，預設 180s，可透過 RuntimeConfig overlay 調整）
   - `|price - vwap| <= entry_band_points` **且** `vol_1s <= exhaustion_vol`
   - **Trend filter**（若開啟）：`trend_allows_entry(...)` 必須通過，否則發 `reason="trend_veto"` 的 SIGNAL_AUDIT 後直接 return None（重要：讓 UAT / 績效分析能看到被濾掉的候選，誠實評估濾網價值）。

3. **出場管理**（`manage_exit` + `_stop_loss_hit`）
   - grace 期間：只認 hard stop
   - 超出 grace：hard stop / vwap stop（ATR 動態） / fixed TP / trailing（ATR 動態）
   - 全部產生對應 reason 的 exit audit + OrderSignal。

4. **Session 邊界**
   - `after_flatten_time` 禁止新進場
   - `force_flatten` 時 kernel 主動呼叫 `session_force_flatten_signal`，plugin 可自訂 slippage 與 audit reason，否則 kernel 合成。

5. **其他 guard**（由 RiskGate 傳入，plugin 必須尊重）
   - `is_pending`、`exit_pending`、`cooldown_active`、`block_new_entry`、`!in_trading_session`、`!api_connected` 等 → 直接 return None。

**Daily loss breach 行為注意**：
- 當 `risk.daily_pnl <= -max_daily_loss_points` 時，當前 tick 會設定 `effects.block_new_entry = True`。
- 由於 block_new_entry 檢查在 daily loss 檢查之後（flat 情況），**breach 發生的那一個 tick 仍有可能 arm entry**（effects 只影響後續 tick 與 kernel 狀態）。這是設計上的 "arming window"，UAT 時需確認 harness 正確捕捉這個邊界。

**Hard stop 與 VWAP stop 的基準差異**（重要）：
- Hard stop：以 `position.entry_price` 為基準（「我進錯了」）。
- VWAP stop / ATR dynamic stop：以當前 `market.vwap` 為基準（mean-reversion 觀點）。
- 這兩個 stop 的參考價格故意不同，grace period 也只保護 hard stop。文件與 UAT 應明確區分這兩種意義。

## 6. Trend Filter（P6-1）重要語意警告（務必閱讀）

`compute_trend(..., min_strength=..., atr=...)` 實作 **Level-2 gating**：

- 只有當偵測到的 HTF 位移強度（raw 或 /ATR）**>= min_strength** 才發出 "Long"/"Short"，否則強制 "Flat"。
- `min_strength=0.0` 是**最嚴格**（最多 veto）的設定，不是最寬鬆。
- ATR normalization 讓不同波動度與不同 mode (ema vs slope) 的門檻可以比較。
- `resample_closes` 刻意從尾端對齊，保證最新價格永遠參與最後一個 bar 的計算。
- EMA 使用 SMA-seed warmup，減少第一根 bar 的 overweight bias。
- 真實使用時建議搭配 engine 端的 `select_recent_trading_days_closes`（避免跨日 gap 汙染舊 regime）—— 見 test_trend.py 中的定量 guard。

這些設計讓 trend_veto 真正有統計意義，而不是對微弱雜訊的過度反應。

## 7. Audit 與可觀測性

plugin 盡可能在關鍵決策點產生 `SignalAudit` 並經由 kernel 記錄為 `SIGNAL_AUDIT` log。

常見 reason：
- entry: "pullback"
- exit: "stop_loss", "stop_loss_vwap", "take_profit", "trailing_stop", "session_force_flatten"
- 特殊： "trend_veto"（帶完整 trend_dir / strength / 量比 / ATR / VWAP）

這些 audit 是後續 UAT report、delta expectancy 分析、min_strength 校準的**唯一可靠來源**。缺少 trend_veto audit 就無法誠實評估濾網是否改善了期望值。

## 8. In Scope / Out of Scope

**In Scope（本 plugin 負責）**
- 所有 momentum / pullback / exit 決策規則
- 策略專屬狀態（MomentumState：active / direction / trigger_time；peak 為歷史死碼已移除）
- 策略專屬參數封裝 + sweep 支援
- 策略專屬 audit 欄位與 reason
- 單元測試（直接 mock snapshot 或透過 testing host）

**Out of Scope（絕對不屬於本 plugin）**
- TradingEngine 狀態機、pending、force-flatten 擁有權、sync_positions
- Tick 回放、MockBroker、VirtualClock（trading-backtest）
- 真實 kbar / tick 抓取（TrendRefreshPort 由 app 實作，策略只 consume `market.trend_dir` 等）
- Telegram、報表、儲存、參數 sweep 執行器（`trading-app`）
- 多商品、scale-in、部分出場（kernel position model 限制）

## 9. 依賴與版本策略

```toml
dependencies = ["trading-engine>=0.2.2,<1.0"]
```

- trading-engine major bump → 本 plugin 需跟進發新版
- Plugin 內部改動（參數預設、校準值、細微規則調整）→ 只 bump plugin patch/minor
- 建議 consuming app 鎖 tag：`strategy-vwap-momentum @ git+...@v0.1.0`

## 10. 測試

- `python run_tests.py`（本 repo 內）
- 強項：trend 數學 + Level-2 + 邊界（gap、resample 最新 bar、min_strength 門檻、ATR norm、SMA seed）
- 行為測試：grace period、cooldown 使用 exchange ts、session force flatten、trend veto 產生正確 audit
- 風格：部分用 `make_vwap_host`（trading_engine.testing）做整合式驗證；純 Protocol 測試建議未來補強
- CI 會在無 shioaji、無 trading-backtest 的環境下至少跑核心邏輯（dev 依賴只裝 ruff/mypy）

## 11. 非目標 / 限制

- 本策略**不是**「拿去實盤就發財」的黑箱產品。它是研究參考實作。
- 不支援 scale-in、減碼、反向同時持倉、多商品。
- 1 口台指日盤為設計目標（與 trading-engine position model 一致）。
- 任何實盤使用前，請完整閱讀 trading-engine 的 `LIVE_SAFETY.md` + `UAT_CHECKLIST.md` 並在 simulation/paper 充分驗證。

---

**維護原則**：Protocol 變更追隨 trading-engine；本 plugin 專注把「這個特定 alpha」的決策、參數、audit、測試文件寫到可被社群閱讀與複製的程度。

See also: [README.md](README.md)、[docs/CALIBRATION.md](docs/CALIBRATION.md)、trading-engine `docs/STRATEGY.md`。
