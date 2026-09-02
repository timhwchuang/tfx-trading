# SMC 策略回測 → Live 對接 Roadmap

> 來源:2026-09 review 討論(FVG 模組落地後的下一步)。
> 用法:**一個 Phase 開一個 AI plan/chat**,把該 Phase 整段貼給 AI 當需求,完成後勾掉。
> 規格衝突時以本文為基準;要改規則,先改本文再改 code。
> 上游決策文件:[BAR_MULTI_TF_DECISIONS.md](BAR_MULTI_TF_DECISIONS.md)。

## 進度總覽

- [ ] Phase 0:歷史資料回補與品質報告
- [ ] Phase 1:交易資料模型 + 成本模型
- [ ] Phase 2:回測引擎(Broker 模擬器 + Ledger)
- [ ] Phase 3:策略層 Setup A(sweep-reversal,純函數)
- [ ] Phase 4:第一輪回測 + 參數掃描 + walk-forward
- [ ] Phase 5:Live 對接(paper → 最小口數)

## 現況盤點(已完成、不重做)

- 1m SSOT + 嚴格 resample(缺分鐘整根丟):`bar_store.py`
- 資料讀取:`bar_reader.py`(每日 CSV `TMFR1_kbars_YYYY-MM-DD.csv`)
- 指標(皆為批次 `compute()`、frozen dataclass、無 lookahead):
  - `indicators/sma.py`:MA5/20/60
  - `indicators/smc.py`:swings、PDH/PDL、prev night H/L、session H/L、
    interact 三態(untouched/swept/taken)、dealing range(premium/discount)、BOS/CHoCH
  - `indicators/fvg.py`:FVG 形成 + mitigation 三態(untouched/mitigated/filled)
- Shioaji 接口與回補:`shioaji_api.py`、`backfilldata.py`

## 全域不變量(每個 Phase 都要遵守)

1. **Strategy 是純函數**:`decide(市場狀態, 部位狀態) -> list[Intent]`。
   回測與 live 跑同一份策略碼,只換執行層(模擬 Broker vs Shioaji adapter)。
2. **5m 收盤決策、1m 模擬成交**:決策只用截至該 5m close 的已收 K;
   成交模擬只能用決策時刻**之後**的 1m。任何 lookahead 都是 bug。
3. **保守成交假設**:同一根 1m 同時觸及停損與停利 → 停損先成交。
4. 指標維持批次全量重算(5m 頻率跑得動);增量化是之後的優化,不在本 roadmap。
5. 風格比照現有 code:frozen dataclass、pytest、ruff、mypy。

---

## Phase 0:歷史資料回補與品質報告

**目標**:5m SMC 策略一天只有 0–2 個 setup,至少要 6–12 個月 1m 資料才有統計意義。
同時要知道 resample「默默丟整根」到底丟掉了什麼。

**產出**

- 用 `backfilldata.py` 回補至少 6 個月(目標 12 個月)TMFR1 1m 日檔
- 新增 `tfx_trading/data_quality.py` + `tests/test_data_quality.py`:
  對日期區間輸出報告——每個交易日的 1m 應有/實有根數、缺哪些分鐘、
  該日被 resample_5m 丟棄的 5m 根數;應有檔卻沒有的日期(對照 trade_day 規則)

**驗收**

- 回補完成後跑品質報告,人工確認缺漏率可接受(缺 5m 比例 < 1% 為佳)
- 報告可輸出成 CSV 或 stdout 表格,回測前可重跑

**非目標**:自動補洞、tick 資料。

---

## Phase 1:交易資料模型 + 成本模型

**目標**:定義回測與 live 共用的交易物件與成本假設。

**產出**

- 新增 `tfx_trading/trading/models.py` + 測試:
  - `Intent`:策略輸出。種類至少含 `place_limit` / `place_stop` / `cancel` / `flatten`,
    欄位含方向、價格、口數、有效期(GTC / 至某 ts 失效)
  - `Order`(含狀態:pending/filled/cancelled/expired)、`Fill`(ts、價、口數)、
    `Position`(方向、口數、均價)、`TradeRecord`(進出場 ts/價、損益、R 倍數、觸發原因)
- 新增 `tfx_trading/trading/costs.py` + 測試:
  - TMF(微型臺指)規格:1 點 = NT$10,tick = 1 點
  - 期交稅:單邊 契約價值 × 0.00002;手續費:單邊固定額,**預設值寫在 config,不寫死**
  - 滑價模型 v1:市價/停損單固定 1 tick,限價單無滑價

**驗收**:單元測試涵蓋往返成本計算(給定進出場價與口數 → 淨損益正確)。

**非目標**:多商品、加減碼(v1 固定 1 口進出)。

---

## Phase 2:回測引擎(Broker 模擬器 + Ledger)

**目標**:事件驅動迴圈,吃 1m bars 與 Intent,產出 fills 與績效報表。

**產出**

- `tfx_trading/backtest/engine.py`:主迴圈
  - 逐根走 1m;每到合法 5m close(`is_session_5m_close`)→ 組出截至該刻的 5m bars
    → 呼叫 Strategy 的 `decide` → 把 Intent 交給 Broker
  - 效能:全量重算可接受;若太慢,允許在引擎層快取 5m bars 的 list(不改指標)
- `tfx_trading/backtest/broker.py`:模擬成交
  - 限價單:之後的 1m `low <= 限價 <= high` 即成交(買方 `low <= 限價` 即可,賣方對稱)
  - 停損單:觸價即以停損價 ± 滑價成交
  - 同根 1m 停損停利皆觸及 → **停損優先**(全域不變量 3)
  - 掛單過期、13:40 強制平倉(收到 `flatten` intent 時以下一根 1m 開盤價成交)
- `tfx_trading/backtest/ledger.py`:記帳與報表
  - trade log(CSV)、equity curve、總損益、MDD、勝率、profit factor、期望值(R)、
    平均持倉時間、分日盤/夜盤 breakdown
- 測試:用手工構造的 1m 序列驗證每種成交路徑(限價成交/不成交、停損優先、過期、強平)

**驗收**

- 一個「假策略」(如固定時間進出)在手工資料上跑出可人工核對的 trade log
- 引擎對 6 個月 1m 資料全跑一輪 < 5 分鐘

**非目標**:多策略並行、部分成交、滑價進階模型。

---

## Phase 3:策略層 Setup A(sweep-reversal,純函數)

**目標**:把 SMC 組合拳寫成 `decide()`,只依賴 `smc.compute` / `fvg.compute` 的輸出。

**規則(多方;空方鏡像)**

1. **Bias 過濾**:`dealing_range.position == "discount"` 才找多
2. **前提**:`pdl` 或 `prev_night_low` 的 `interact == "swept"`(swept = 反轉候選;
   `taken` = 趨勢延續,v1 不做)
3. **確認**:sweep 的 `interact_ts` 之後出現 bullish `StructureEvent`
   (CHoCH 優先;`scope == "external"` 權重更高——v1 先只要求「有 bullish event」即可,
   scope 當參數)
4. **進場**:確認後,選最新的 bullish FVG,條件:
   `state in ("untouched", "mitigated")`、`size >= min_points`、`formed_at` 在 sweep 之後。
   限價掛 `top` 或 `ce`(參數,見 Phase 4 掃描)
5. **停損**:sweep 低點 − buffer(參數),或 FVG `bottom` − buffer,取較近者為 v1 預設
6. **停利**:固定 R 倍數(預設 2R);對側流動性(session_high/pdh)當參數選項
7. **風控**:一次一單;日虧 2 次當日停手;13:40 強制平倉;v1 只做日盤

**產出**

- `tfx_trading/strategy/setup_a.py`:純函數 + `SetupAParams` frozen dataclass(所有參數)
- 內含 `_select_active_fvg`(同向、最新、age 過濾)——FVG plan 明確留給策略層的函數
- `tests/test_setup_a.py`:手工 bar 序列驗證每條規則的觸發與不觸發
  (bias 不對不進、taken 不進、FVG 太小不進、日虧停手、強平)

**驗收**:接上 Phase 2 引擎,在實際資料某一天上手動追蹤一筆完整交易,逐步核對訊號鏈
(swept → event → FVG → fill → exit)與指標 demo 輸出一致。

**非目標**:Setup B(BOS 延續)、夜盤、多口數、移動停損。

---

## Phase 4:第一輪回測 + 參數掃描 + walk-forward

**目標**:回答「sweep → CHoCH → 回踩 FVG 在台指 5m 上有沒有 edge」。

**產出**

- `tfx_trading/backtest/sweep.py`(或 notebook):參數掃描
  - 掃描維度:進場價(top vs ce)、`min_points`、停損 buffer、TP(2R vs 對側流動性)、
    是否要求 external scope
- Walk-forward:前 70% 資料選參數,後 30% out-of-sample 驗證
- 報告:每組參數的期望值(R)、trade 數、MDD;in-sample vs out-of-sample 對照表

**驗收與決策準則**

- 每組參數樣本內至少 ~30 筆 trade 才納入比較
- out-of-sample 期望值 > 0 且相對 in-sample 衰退 < 50% → 進 Phase 5
- 全部組合都不行 → 回頭調 Setup A 規則(改本文後再改 code),不硬上 live

**非目標**:ML 調參、組合多策略。

---

## Phase 5:Live 對接(paper → 最小口數)

**目標**:同一份 `decide()` 接上 Shioaji,先模擬環境驗證,再最小口數上線。

**產出**

- `tfx_trading/live/runner.py`:
  Shioaji 訂閱 → 組 1m → `BarStore.push` → 每個 5m 邊界跑 `decide` → intents 交給下單 adapter
- `tfx_trading/live/broker_shioaji.py`:Intent → Shioaji 下單/改單/刪單;訂單回報 → Order 狀態
- Live 特有處理(回測沒有、必須做):
  - 啟動時用 `backfilldata` 回補當日 bars 再開始
  - 斷線重連後部位對帳:**以券商回報為準**,不信本地狀態
  - 行情缺 1m → 該 5m 不會收出來(resample 規則)→ 該次決策跳過,記 log 告警
  - kill switch:一鍵全平 + 停止下單
- forming bar 與已收 K 分開處理(比照 BAR_MULTI_TF_DECISIONS.md:勿同一條 if)

**驗收(依序,不可跳)**

1. Shioaji 模擬環境 paper 跑 ≥ 2–4 週
2. 比對 paper 成交 vs 回測假設:限價單成交率、滑價分布;偏差大 → 回 Phase 2 修 Broker 假設
3. 最小口數(1 口 TMF)上線,日虧上限先設得比回測更緊

**非目標**:自動重啟營運、多帳戶、加碼邏輯。

---

## 附錄:開放參數一覽(Phase 4 掃描對象)

| 參數 | 預設 | 說明 |
|---|---|---|
| `entry_price` | `top` | FVG 進場價:`top` 或 `ce` |
| `min_points` | 20.0 | FVG 最小 size(比照 SMC MIN_POINTS 起手) |
| `stop_buffer` | 5.0 | 停損 buffer(點) |
| `take_profit` | `2R` | `2R` 或 `opposite_liquidity` |
| `require_external` | False | 確認 event 是否要求 `scope == "external"` |
| `max_daily_losses` | 2 | 日虧停手次數 |
| `flatten_time` | 13:40 | 日盤強平時間 |
