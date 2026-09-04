# SMC 策略回測 → Live 對接 Roadmap

> 來源:2026-09 review 討論(FVG 模組落地後的下一步);2026-09-02 依實務 review 補強。
> 用法:**一個 Phase 開一個 AI plan/chat**,把該 Phase 整段貼給 AI 當需求,完成後勾掉。
> 規格衝突時以本文為基準;要改規則,先改本文再改 code。
> 上游決策文件:[BAR_MULTI_TF_DECISIONS.md](BAR_MULTI_TF_DECISIONS.md)。

## 進度總覽

- [x] Phase 0:歷史資料回補與品質報告
- [x] Phase 1:交易資料模型 + 成本模型
- [x] Phase 2:回測引擎(Broker 模擬器 + Ledger)
- [x] Phase 3:策略層 Setup A(sweep-reversal,純函數)
- [ ] Phase 4:第一輪回測 + 參數掃描 + walk-forward
- [ ] Phase 5:Live 對接(paper → 最小口數)

## 現況盤點(已完成、不重做)

- 1m SSOT + 嚴格 resample(缺分鐘整根丟):`bar_store.py`
- 資料讀取:`bar_reader.py`(每日 CSV `TMFR1_kbars_YYYY-MM-DD.csv`)
- 指標(`compute()` 可增量、frozen dataclass、無 lookahead;等價不變量見全域 #6):
  - `indicators/sma.py`:MA5/20/60
  - `indicators/smc.py`:swings、PDH/PDL、prev night H/L、session H/L、
    interact 三態(untouched/swept/taken)、dealing range(premium/discount)、BOS/CHoCH
  - `indicators/fvg.py`:FVG 形成 + mitigation 三態(untouched/mitigated/filled)
- Shioaji 接口與回補:`shioaji_api.py`、`backfilldata.py`(skip existing、`--overwrite`、fetch 後才 sleep)
- 交易日曆 / 品質報告:`calendar.py`、`data_quality.py`(tape hole vs 日曆 mismatch 分開)
- **TMFR1 結算日 13:31 換月、無 back-adjust**(見 `config/tmfr1_rollover.csv`;含順延日 2026-02-23)
- 交易物件 / 成本:`trading/models.py`、`trading/costs.py`
  (Intent/Order/Fill/Position/TradeRecord;`close_trade` 只在 costs;
  `load_config` 忽略 yaml `trading:`)
- 回測引擎:`backtest/{engine,broker,ledger}.py`
  (5m prefix `decide`;`fill_mode`;Broker 呼叫 `close_trade`;Ledger 只記帳。
  6 個月 < 5 分鐘用 `run()` + 空 `FixedTimeStrategy` + `BarReader` 手動驗,不進預設 pytest)
- 策略 Setup A:`strategy/setup_a.py`(純 `decide`;日盤 sweep-reversal;engine 傳 `closed_trades`/`entry_ts`)

## 全域不變量(每個 Phase 都要遵守)

1. **Strategy 是純函數**:`decide(市場狀態, 部位狀態) -> list[Intent]`。
   回測與 live 跑同一份策略碼,只換執行層(模擬 Broker vs Shioaji adapter)。
2. **5m 收盤決策、1m 模擬成交**:決策只用截至該 5m close 的已收 K;
   成交模擬只能用決策時刻**之後**的 1m。任何 lookahead 都是 bug。
3. **保守成交假設**(細則見 Phase 2):
   - 同一根 1m 同時觸及停損與停利 → 停損先成交。
   - 進場限價與停損同一根 1m 皆觸及 → 視為進場後**立刻停損**
     (FVG 被一根長針掃穿時常發生,必須明定)。
   - 限價成交採雙模式(樂觀 touch / 保守 trade-through)。
     **edge 只存在於樂觀模式 = 沒有 edge**,不得進 Phase 5。
4. **記帳以 NT$ 為準**:equity curve、MDD、日虧上限的最終單位是 NT$(含成本),
   點數與 R 倍數為輔助指標。資金與保證金是一級公民,不是事後換算。
5. **touch ≠ fill**:限價單「碰到價位」不保證成交,且有系統性偏差——
   最賺的單(碰到就反彈)最容易沒排到,最虧的單(直接穿過)100% 成交。
   所有成交假設都要往保守方向偏。
6. 指標**可以增量**,但必須保留 `compute_from_scratch` oracle 與逐 prefix 等價測試。
   `compute()` 輸出與全量重算位元一致是不變量;lookahead 仍是 bug。
7. 風格比照現有 code:frozen dataclass、pytest、ruff、mypy。

---

## Phase 0:歷史資料回補與品質報告

**目標**:5m SMC 策略一天只有 0–2 個 setup,至少要 6–12 個月 1m 資料才有統計意義。
同時要知道 resample「默默丟整根」到底丟掉了什麼,以及連續合約(R1)接月怎麼接的。

**產出**

- 用 `backfilldata.py` 回補至少 6 個月(目標 12 個月)TMFR1 1m 日檔
- 新增 `tfx_trading/data_quality.py` + `tests/test_data_quality.py`:
  對日期區間輸出報告——每個交易日的 1m 應有/實有根數、缺哪些分鐘、
  該日被 resample_5m 丟棄的 5m 根數;應有檔卻沒有的日期(對照 trade_day 規則)
- **夜盤品質一併納入報告**:Setup A 依賴 `prev_night_low` 與 PDH/PDL,
  夜盤缺資料會讓日盤訊號**靜默失真**,不是只檢查日盤 1m 就好
- 報告每日加註記欄位:
  - 是否為**結算日**(台指期每月第三個週三;結算日行為異常,下游 Phase 會用到)
  - 是否接近**漲跌停**(如日內極值距前結算價 > 9%;鎖死日回測不可信)
- **確認 TMFR1 接月方式**:向 Shioaji 文件/實測確認 R1 歷史資料的換月接點日期、
  有無 back-adjust。產出換月日清單(csv 或寫死在 config),後續 Phase 3/5 都要用

**驗收**

- 回補完成後跑品質報告,人工確認缺漏率可接受(缺 5m 比例 < 1% 為佳)
- 報告可輸出成 CSV 或 stdout 表格,回測前可重跑
- 換月日清單人工抽查 2–3 個月份,確認接點前後價差與量能轉移合理

**非目標**:自動補洞、tick 資料。

---

## Phase 1:交易資料模型 + 成本模型

**目標**:定義回測與 live 共用的交易物件、成本假設與資金概念。

**產出**

- 新增 `tfx_trading/trading/models.py` + 測試:
  - `Intent`:策略輸出。種類至少含 `place_limit` / `place_stop` / `cancel` / `flatten`,
    欄位含方向、價格、口數、有效期(GTC / 至某 ts 失效)、
    **唯一 `intent_id`**(live 下單冪等用,回測也帶著,見 Phase 5)
  - `Order`(含狀態:pending/filled/cancelled/expired/**rejected**)——
    rejected 是實盤必有:期交所**動態價格穩定措施**與漲跌停都會退單,
    停損單被退單 = 部位裸露,狀態機必須能表達
  - `Fill`(ts、價、口數)、`Position`(方向、口數、均價)、
    `TradeRecord`(進出場 ts/價、損益 NT$ 與 R 倍數、觸發原因)
- 新增 `tfx_trading/trading/costs.py` + 測試:
  - TMF(微型臺指)規格:1 點 = NT$10,tick = 1 點
  - 期交稅:單邊 契約價值 × 0.00002;手續費:單邊固定額,**預設值寫在 config,不寫死**
  - 滑價模型 v1:市價/停損單固定 N tick(config,預設 1),限價單無滑價
  - **保證金**:原始/維持保證金金額寫在 config(期交所會調整,不寫死);
    提供「給定口數 → 所需保證金」函數,Phase 2 Ledger 與 Phase 5 資金檢查共用

**驗收**:單元測試涵蓋往返成本計算(給定進出場價與口數 → 淨損益 NT$ 正確)、
保證金計算、rejected 狀態轉移。

**非目標**:多商品、加減碼(v1 固定 1 口進出)。

---

## Phase 2:回測引擎(Broker 模擬器 + Ledger)

**目標**:事件驅動迴圈,吃 1m bars 與 Intent,產出 fills 與績效報表。
**這一層的成交假設決定整個專案的成敗**,寧可保守到少賺,不可樂觀到假賺。

**產出**

- `tfx_trading/backtest/engine.py`:主迴圈
  - 逐根走 1m;每到合法 5m close(`is_session_5m_close`)→ 組出截至該刻的 5m bars
    → 呼叫 Strategy 的 `decide` → 把 Intent 交給 Broker
  - 效能:指標可增量(見全域不變量 6);引擎層仍可快取 5m prefix list。
    Phase 4 `CachedSetupA` 用增量 tracker,不再假設批次永遠重算。
- `tfx_trading/backtest/broker.py`:模擬成交
  - **限價單雙模式 `fill_mode`(config,兩種都要實作)**:
    - `optimistic`:之後的 1m `low <= 限價` 即成交(賣方對稱)
    - `conservative`:要求 trade-through——買方 `low <= 限價 - 1 tick` 才成交(賣方對稱)
  - 停損單:觸價即以停損價 ± 滑價成交
  - 同根 1m 停損停利皆觸及 → **停損優先**;
    同根 1m 進場限價與停損皆觸及 → **進場後立刻停損**(全域不變量 3)
  - 掛單過期、13:40 強制平倉(收到 `flatten` intent 時以下一根 1m 開盤價成交;
    強平屬市價性質,**滑價另計且偏大**,config 獨立一個 `flatten_slippage_ticks`)
- `tfx_trading/backtest/ledger.py`:記帳與報表
  - trade log(CSV)、equity curve(**NT$,含成本**)、總損益、MDD(NT$)、勝率、
    profit factor、期望值(R)、平均持倉時間、分日盤/夜盤 breakdown
  - **保證金占用**:報表輸出最大保證金占用 + MDD → 推得「最低所需帳戶資金」
  - **可重現性**:每次 run 在 trade log 檔頭記 git commit hash、完整參數、
    資料檔案清單與日期範圍。三個月後要能回答「這條 equity curve 是哪個版本跑的」
- 測試:用手工構造的 1m 序列驗證每種成交路徑
  (限價成交/不成交、兩種 fill_mode 差異、停損優先、進場即停損、過期、強平)

**驗收**

- 一個「假策略」(如固定時間進出)在手工資料上跑出可人工核對的 trade log
- 同一策略同資料下,`conservative` 的成交筆數 ≤ `optimistic`,且差異可解釋
- 引擎對 6 個月 1m 資料全跑一輪 < 5 分鐘

**非目標**:多策略並行、部分成交、滑價進階模型、依 tick 資料估排隊位置。

---

## Phase 3:策略層 Setup A(sweep-reversal,純函數)

**目標**:把 SMC 組合拳寫成 `decide()`,只依賴 `smc.compute` / `fvg.compute` 的輸出。

**規則(多方;空方鏡像)**

1. **Bias 過濾**:`dealing_range.position == "discount"` 才找多
2. **前提**:`pdl` 或 `prev_night_low` 的 `interact == "swept"`(swept = 反轉候選;
   `taken` = 趨勢延續,v1 不做)
3. **確認**:sweep 的 `interact_ts` **當根或之後** (`event.ts >= interact_ts`;
   同根 wick sweep + close CHoCH 算確認。CHoCH 優先僅 demo 列印;
   `scope == "external"` 當參數,v1 先只要求「有 bullish event」)
4. **進場**:確認後,選最新的 bullish FVG,條件:
   `state in ("untouched", "mitigated")`、`size >= min_points`、
   `formed_at >= interact_ts`。限價掛 `top` 或 `ce`(參數,見 Phase 4 掃描)
5. **停損**:sweep 低點 − buffer(參數),或 FVG `bottom` − buffer,取較近者為 v1 預設
6. **停利**:固定 R 倍數(預設 2R);對側流動性(session_high/pdh)當參數選項
7. **風控**:
   - 一次一單;13:40 強制平倉;v1 只做日盤
   - 日虧停手:**次數上限(預設 2 次)與金額上限(NT$,config)雙軌**,先到先停
   - **結算日整天不交易**(用 Phase 0 的結算日標記/換月日清單;
     結算日流動性轉移、跨日參考價是不同合約,sweep 邏輯會被污染)
   - **開盤禁做窗 `no_trade_before`(預設 09:15)**:08:50 第一根 5m 收盤時
     當日樣本極少、波動最大,v1 不碰
   - **Time stop `max_hold_bars`**:持倉超過 N 根 5m 未觸 SL/TP → flatten
     (v1 預設可設很大等同關閉,但參數要留,Phase 4 要掃)

**產出**

- `tfx_trading/strategy/setup_a.py`:純函數 + `SetupAParams` frozen dataclass(所有參數)
- 內含 `_select_active_fvg`(同向、最新、age 過濾)——FVG plan 明確留給策略層的函數
- `tests/test_setup_a.py`:手工 bar 序列驗證每條規則的觸發與不觸發
  (bias 不對不進、taken 不進、FVG 太小不進、日虧停手(次數與金額)、
  結算日不進、開盤窗內不進、time stop、強平)

**驗收**:接上 Phase 2 引擎,在實際資料某一天上手動追蹤一筆完整交易,逐步核對訊號鏈
(swept → event → FVG → fill → exit)與指標 demo 輸出一致。

**非目標**:Setup B(BOS 延續)、夜盤、多口數、移動停損。

---

## Phase 4:第一輪回測 + 參數掃描 + walk-forward

**目標**:回答「sweep → CHoCH → 回踩 FVG 在台指 5m 上有沒有 edge」——
且答案要在**保守成交假設與滑價壓力下仍然成立**才算數。

**產出**

- `tfx_trading/backtest/sweep.py`(或 notebook):參數掃描
  - 掃描維度:進場價(top vs ce)、`min_points`、停損 buffer、TP(2R vs 對側流動性)、
    是否要求 external scope、`max_hold_bars`
  - **每組參數都要在 `fill_mode = optimistic` 與 `conservative` 各跑一輪**
  - **滑價敏感度**:停損滑價 0/1/2/3 tick 各跑一輪,看期望值衰減曲線
- Walk-forward:**rolling** 優於單次切分——例如每 3 個月用前段資料重選參數、
  往後推進驗證;至少要做前 70% 選參 / 後 30% out-of-sample 的基本版
- 報告:每組參數的期望值(R 與 NT$)、trade 數、MDD(NT$);
  in-sample vs out-of-sample 對照表
- **MDD 分布**:對最終候選參數的 trade 序列做 Monte Carlo 重排(≥1000 次),
  輸出 MDD 分位數(P50/P90/P99)——這個數字是 Phase 5 決定資金與日虧上限的依據,
  不是單一路徑的 MDD

**驗收與決策準則**

- 每組參數樣本內至少 ~30 筆 trade 才納入比較;**out-of-sample 也要有最低 trade 數**
- **參數選 plateau 不選單點最佳**:掃描維度多,總有幾組「看起來能賺」
  (多重比較偏誤);候選參數的鄰近組合也必須獲利,孤峰一律視為過擬合
- 進 Phase 5 的門檻(全部要過):
  - `conservative` fill_mode 下 out-of-sample 期望值 > 0
  - 相對 in-sample 衰退 < 50%
  - 滑價 2 tick 下期望值仍 > 0
- 全部組合都不行 → 回頭調 Setup A 規則(改本文後再改 code),不硬上 live

**非目標**:ML 調參、組合多策略。

---

## Phase 5:Live 對接(paper → 最小口數)

**目標**:同一份 `decide()` 接上 Shioaji,先模擬環境驗證,再最小口數上線。
「同一份策略碼」不是宣稱,是要用 parity 機制**證明**的。

**產出**

- `tfx_trading/live/runner.py`:
  Shioaji 訂閱 → 組 1m → `BarStore.push` → 每個 5m 邊界跑 `decide` → intents 交給下單 adapter
- `tfx_trading/live/broker_shioaji.py`:Intent → Shioaji 下單/改單/刪單;訂單回報 → Order 狀態
  - **合約 mapping**:訊號來自 R1 概念,下單下**實際月份合約**;
    換月規則寫死在 config(如結算日前一日收盤後切次月),與 Phase 0 換月清單一致
  - **rejected 處理**:動態價格穩定措施/漲跌停退單 → 記 log 告警;
    停損單被退 = 部位裸露,立即改市價平倉或重掛,規則先寫死不臨場發揮
  - **下單冪等**:每個 Intent 帶唯一 id;下單前查在途單,重連後不重複下單
- **Parity harness(「回測 = live」的證明,不可省)**:
  - 決策快照:live 每次 `decide` 落地完整輸入(bars 範圍與 hash、指標輸出、intents)
  - Replay 比對:事後用回測引擎跑同一天資料,intents 必須**逐筆一致**;
    不一致 = lookahead 或狀態污染,停下來修
  - Bar parity:比對「live 自組 1m bars vs Shioaji 歷史 kbars」同一天的差異;
    差異大代表回測資料和 live 看到的世界不同,回測結論不可移植
- Live 特有處理(回測沒有、必須做):
  - 啟動時用 `backfilldata` 回補當日 bars 再開始
  - 斷線重連後部位對帳:**以券商回報為準**,不信本地狀態
  - **盤中重啟的完整狀態重建**:不只部位,還有當日已虧次數/金額、在途掛單、
    今日已觸發過的 setup——否則重啟後日虧停手歸零、重複進場
  - 行情缺 1m → 該 5m 不會收出來(resample 規則)→ 該次決策跳過,記 log 告警
  - kill switch:一鍵全平 + 停止下單
  - **Heartbeat / dead man's switch**:程式掛掉且有部位時,必須有**獨立於程式本身**的
    通知管道到手機(外部 watchdog 監控 heartbeat 檔案/端點;程式自己發不算,它已經掛了)
  - **時間戳紀律**:一律用交易所/回報時間戳,不信本機時鐘;主機開 NTP
- forming bar 與已收 K 分開處理(比照 BAR_MULTI_TF_DECISIONS.md:勿同一條 if)

**驗收(依序,不可跳)**

1. Parity harness 就位:任選 3 個交易日,live 決策快照 replay 比對 intents 逐筆一致;
   bar parity 差異在可接受範圍(缺根數與 OHLC 差異有量化報告)
2. Shioaji 模擬環境 paper 跑 ≥ 2–4 週
3. 比對 paper 成交 vs 回測假設:限價單成交率、滑價分布;
   實際成交率落在 optimistic/conservative 之間才合理;偏差大 → 回 Phase 2 修 Broker 假設
4. 資金檢查:帳戶資金 ≥ 保證金 + Phase 4 的 MDD P90(NT$),否則不上
5. 最小口數(1 口 TMF)上線,日虧上限(次數與金額)先設得比回測更緊

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
| `max_daily_loss_nt` | (config) | 日虧停手金額(NT$),與次數雙軌先到先停 |
| `flatten_time` | 13:40 | 日盤強平時間 |
| `no_trade_before` | 09:15 | 開盤禁做窗,此前的 5m close 不進場 |
| `max_hold_bars` | (大值) | Time stop:持倉超過 N 根 5m 未觸 SL/TP → flatten |
| `fill_mode` | `conservative` | 限價成交模式:`optimistic`(touch)/ `conservative`(trade-through) |
| `slippage_ticks` | 1 | 市價/停損單滑價(tick);敏感度掃 0–3 |
| `flatten_slippage_ticks` | 2 | 強平(市價性質)滑價,獨立於一般滑價 |
| `skip_settlement_day` | True | 結算日整天不交易 |

## 附錄:UAT / 上線前 go/no-go 檢查清單

全部打勾才進最小口數;任何一項 fail → 停在該 Phase 修完再來。

**回測可信度(Phase 2/4)**

- [ ] `conservative` fill_mode 下 OOS 期望值 > 0,且相對 in-sample 衰退 < 50%
- [ ] 滑價 2 tick 壓力下期望值仍 > 0
- [ ] 候選參數是 plateau 不是孤峰(鄰近參數組合皆獲利)
- [ ] MDD 用 Monte Carlo 分位數(P90)評估,非單一路徑
- [ ] trade log 可重現(git hash + 參數 + 資料範圍齊全)

**Parity(Phase 5 前置)**

- [ ] 3 個交易日的 live 決策快照 replay,intents 逐筆一致
- [ ] bar parity 報告(自組 vs API kbars)差異可接受
- [ ] paper 限價成交率落在 optimistic/conservative 兩模式之間

**資金與風控**

- [ ] 帳戶資金 ≥ 保證金 + MDD P90(NT$)
- [ ] 日虧上限(次數 + 金額)設定完成,且比回測假設更緊
- [ ] 結算日不交易已生效;換月 mapping 已人工核對下一個換月日

**運維**

- [ ] kill switch 演練過(一鍵全平 + 停單)
- [ ] dead man's switch 演練過:kill 掉程式,手機在 N 分鐘內收到通知
- [ ] 盤中重啟演練過:重啟後部位對帳、當日虧損計數、在途單全部正確重建
- [ ] rejected 訂單處理路徑演練過(至少在模擬環境觸發一次)
