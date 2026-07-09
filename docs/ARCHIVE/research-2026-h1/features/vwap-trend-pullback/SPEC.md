---
id: FT-010
slug: vwap-trend-pullback
status: MVPClosed
opened: 2026-06-28
owner: human+agent
target: Pilot-prep
stable_contract: packages/strategies/vwap-trend-pullback/SPEC.md
audit_schema_version: 1
---

# FT-010 — VWAP Trend Pullback（Thesis G）

> **SPEC** = 趨勢確認後的 **session VWAP 強勢回踩**（Phase 0 **long-only**）。**拋開** `momentum_armed` / vol_1s spike / timeout 追價 / 純 fade。  
> **主判**：**01–03 合計** · **04 valid 參考** · **05 holdout 封印**至 plugin baseline 過關。

## 1. Summary

**問題**：FT-003 診斷顯示 v1 hybrid「爆量武裝 + VWAP 回踩」結構性 No-Go——entered 子集在脈衝回吐相位進場（W180 **−15**、MAE > MFE）；瓶頸在「價格是否回到 VWAP band」，非 vol 門檻；停損 **0.23×ATR** 被分鐘噪音掃穿（QSL 28–33%）。FT-006 fade valid 過、holdout 未過，證明「過度延伸」有訊號但**方向與相位**必須分離。

**目標**：在 **已確認上升趨勢** 中，價格先 **stretch 背離 session VWAP**，再在 **recency 窗口內** 縮量回踩 Buffer Zone 時 **long** 進場；出場 **首日即 ATR-scaled**；停損 **tick H/L** 觸發。

**與 live 關係**：與 `strategy-vwap-momentum` **互補**（v1 凍結為研究參考）；UAT **不切換**直至 01–03 過關 + 04 valid 確認 + 05 holdout + 人類 Go。

**使用者**：`workspaces/vtp-baseline` Phase 0 counterfactual → plugin → baseline。

## 2. 現況 vs 目標（FT-003 教訓對照）

| 面向 | FT-003 v1 hybrid | FT-006 fade | **FT-010** |
|------|------------------|-------------|------------|
| Setup | 1s vol spike **armed** | 靜態 z-score 過延伸 | **1m stretch 背離**（無 spike） |
| 相位 | armed 後等回踩（與 timeout 子集混在一起） | 延伸當下 **反向** | stretch **後**回踩 **順勢** long |
| VWAP | 5m rolling + band | 5m rolling | **session 累積**（`IndicatorState` 同語意） |
| 趨勢 | 可選、與 spike 綁定 | 預設關 | **必須** P>VWAP 且 VWAP 斜率正 |
| 停損尺度 | HS6 ≈ **0.23×ATR** | 0.75×ATR | **≥1.0×ATR**（floor 9pt） |
| 頻率 | 高（~150 趟/valid 月） | ~82/月 | **≤3 筆/日** 目標 |
| 時段 | 全時段 | bucket 分組 | **早+尾**；**午盤禁開** |
| Gate 主判 | valid 4 月 | valid 4 月 | **01–03 合計** |
| 方向 | 雙向 + spike | 雙向 fade | **Phase 0 long-only** |

**本 thesis 保留什麼**：「機構以 VWAP 為價值區、過度背離後回踩可能重新進場」——但 **否決** spike-arm、否決固定點數停損、否決全時段、否決 Phase 0 雙向混做。

**本 thesis 必須證偽什麼**（pre-registered）：若 01–03 最佳組 **gross/趟 ≤ 5** 或 **net ≤ 0** → **MVPClosed**（同 FT-004～008，不開 plugin）。

## 3. 方向契約（Long-only · Phase 0）

| Phase | 方向 | 說明 |
|-------|------|------|
| **Phase 0** | **Long only** | 主判僅統計 long leg；避免與 FT-006 fade、FT-003 雙向稀釋 |
| **Phase 1a**（可選） | Mirror short | **僅在** 01–03 long G1–G3 全過後；獨立報告，**combined 不作唯一 gate** |
| **禁止** | Phase 0 雙向 gate | 同 ORB Short 主導教訓：方向 leg 須分開解讀 |

**Phase 1a short 鏡像（封印，不納入 Phase 0）**：`close < session_vwap`、VWAP 連續 3 根遞減、stretch 向下觸及 `vwap − stretch_k×ATR`、回踩 Buffer、TP = `stretch_low`。

## 4. 資料與指標契約（MUST）

1. **資料**：`tick_cache/{code}_{date}.csv` → 1m bar；VWAP / ATR 與 engine **`IndicatorState`** 同語意（tick 累積量加權 session VWAP；ATR = SMA(TR, **14**））。
2. **ATR 單位**：點數；`hard_stop_pts = max(hard_stop_atr_k × ATR, hard_stop_floor_pts)`。
3. **停損觸發**：回放 **tick High/Low**；**禁止**僅用 1m Close 判定停損（FT-003 回測失真教訓）。
4. **摩擦**：每趟 **5 點** round-trip（entry +2.5、exit +2.5）；所有 Gate / leaderboard 以 **net** 為準。
5. **交易所時間**：`exchange_time` / session 邊界；`session_bucket` 語意對齊 FT-006 `session_bucket_for_ts`。

## 5. 進場契約（MUST — Phase 0 CF，pre-registered）

### 5.1 環境濾網（全部通過才允許 stretch 狀態）

| # | 規則 | 可執行定義 |
|---|------|------------|
| E1 | **趨勢** | 當根 1m **close** `> session_vwap` |
| E2 | **VWAP 斜率** | 連續 **3** 根已收盤 1m 的 session VWAP 嚴格遞增：`vwap[t] > vwap[t-1] > vwap[t-2]` |
| E3 | **ATR 地板** | `ATR(14) ≥ min_atr_threshold_points`（預設 **25**） |
| E4 | **時段** | `08:55 ≤ t < 11:00` **或** `13:00 ≤ t < 13:35`；**11:00–13:00 禁新倉** |
| E5 | **日內熔斷** | 策略內累計 net ≤ **−30** 點 → 當日 `block_new_entry`（不覆寫 kernel `max_daily_loss_points`） |

### 5.2 Stretch 事件（背離確認）

在過去 **`stretch_lookback_min`（固定 15）** 分鐘內，1m **high** 曾 ≥ `session_vwap + stretch_k × ATR`。

- `stretch_k` **pre-register**：**1.5**（Phase 0 固定；**禁止**用 04 月 tune 作主判）。

記錄 `stretch_high` = 該窗口內最高價、`stretch_bar_ts` = 首次觸及背離門檻的 bar 結束 ts。

### 5.3 Recency（FT-003「回踩拖太久變反轉」對策）

自 `stretch_high` 形成後，至進場 bar 收盤，經過的 **1m bar 數** ≤ `recency_max_bars`。

- `recency_max_bars` **pre-register grid**：`{6, 8, 10}`（唯一 sweep 軸）。

### 5.4 Buffer Zone + 量能（回踩確認）

**Buffer Zone**（long）：`[session_vwap + upper_buf_k × ATR, session_vwap − lower_buf_k × ATR]`  
預設：`upper_buf_k = 0.12`，`lower_buf_k = 0.05`（固定，不 sweep）。

進場 bar 收盤須 **落在 Buffer 內**（`close ∈ zone`）。

**縮量**（pullback leg）：自 `stretch_bar_ts` 至進場前一根 inclusive，1m volume 的 **median** < stretch 當根 volume × `pullback_vol_ratio_max`（預設 **0.85**）。

**攻擊量**（touch bar）：進場 bar `volume ≥ mean(volume[t-5:t-1]) × attack_vol_mult`（預設 **1.5**）。

### 5.5 進場觸發與頻率

- **觸發**：上述條件於 **同一根 1m bar 收盤** 同時滿足 → entry signal（**禁止**不可審計的「微觀止跌」語意）。
- **頻率**：每交易日最多 **1 筆**（first valid touch only）。
- **去重**：同一 stretch 事件僅允許 1 次進場；平倉後當日不再開倉。

### 5.6 Phase 0 執行模型

Phase 0 counterfactual **僅模擬 market entry @ bar close**（+ entry friction 2.5pt）。  
**Limit IOC**（`limit = session_vwap + limit_offset_pts`，預設 2pt）列為 **Phase 1b** 對照，不在 Phase 0 gate 內 sweep。

**禁止**：

- `momentum_armed` / `vol_1s` spike 任何路徑
- 4 月單獨 tune 作 **01–03 過關**依據
- 05 月任何回測直至 holdout 解封
- Phase 0 以 combined long+short 作唯一 gate

## 6. 出場契約（MUST）

Phase 0 **僅** barrier sim + tick 停損（對齊 FT-004/006/009）：

| 參數 | 語意 | 初值 |
|------|------|------|
| `hard_stop_atr_k` | 硬停距離 | **1.0** |
| `hard_stop_floor_pts` | 停損地板 | **9** |
| `tp_atr_k` | 止盈（相對 entry 的 ATR 倍數） | **1.8** |
| `max_hold_sec` | 時間停 | **1200**（20 分） |
| `exit_grace_sec` | grace 內僅 hard stop | **10** |

**TP 優先序**（釘死）：`min(entry + tp_atr_k × ATR, stretch_high)` 先到者勝（背離高點 cap TP）。

**Phase 1b（非 Phase 0 gate）**：條件式 breakeven——進場後 12 分鐘內曾達 **0.5×R** → SL 移至 entry；再抱 **480s**；否則 12 分鐘成本區橫盤 → 市價平。須單獨子版本，不得事後併入 Phase 0 最佳組。

## 7. 日期切分與 Go / No-Go Gates

引用 [`VOLATILITY_BASELINE.md`](../../../workspaces/VOLATILITY_BASELINE.md) 角色標籤：

| 區間 | 日期 | 角色 | 用途 |
|------|------|------|------|
| **Train** | 2026-01-01～2026-03-31 | 01–03 合計 | **主判** |
| **Valid** | 2026-04-01～2026-04-30 | valid | **參考 + Phase 1 門檻** |
| **Holdout** | 2026-05-01～2026-05-31 | holdout | **封印**至 plugin baseline |

### Phase 0（counterfactual · long only）

| Gate | 條件 | 未過 |
|------|------|------|
| **G1** | 01–03 gross/趟 **> 5** | **MVPClosed** |
| **G2** | 01–03 net/趟 **> 0**（摩擦 5） | **MVPClosed** |
| **G3** | 01–03 **n ≥ 30** | **MVPClosed** |
| **G4** | 01–03 QSL **< 25%** | 僅診斷；可調 `hard_stop_atr_k` 一次重跑 |
| **G5** | 01–03 日均交易 **≤ 3** | 檢討濾網過鬆 |
| **G6** | 01–03 無單月 net/趟 **< −2** | 不穩 / overfit suspect |

**Valid 04（參考，不作 Phase 0 主判）**：

| 指標 | 期望 |
|------|------|
| 最佳 param 的 net/趟 | **> 0**（若 01–03 過但 04 net ≤ 0 → **overfit suspect**，同 FT-006/008） |
| gross/趟 | 記錄對照，不作硬過關 |

**Funnel 診斷（MUST 產出，不當 gate knob）**：沿用 [`ENTRY_FUNNEL_METRICS.md`](../ai-backtest-tuning/ENTRY_FUNNEL_METRICS.md)：

- stretch 事件數 → buffer touch 轉化率
- 若 touch 率 **< 25%** → 標 `structural_band_unreachable`（FT-003 §6.2 同型瓶頸）

### Phase 1（plugin + baseline）

- 01–03 **G1–G3** 仍須成立（plugin 重播）
- **04 valid**：net/趟 **> 0** 且 gross/趟 **> 5**
- **05 holdout 解封**：04 valid 過 + 人類書面 Go

### Phase 1b（執行對照，非 gate）

- Limit IOC vs market：比較 net/趟、成交率、cancel 率；產物 `compare_fill_audits`（UAT 模擬 API）

### Holdout 05

| Gate | 條件 |
|------|------|
| **H1** | gross/趟 **> 5** |
| **H2** | net/趟 **> 0** |
| **H3** | trade_count **< 100**/月 |

未過 → **凍結 Pilot**（同 FT-006）；不回到 04 tune。

## 8. Pre-registered 參數格（Phase 0 ONLY）

| 軸 | 值 | 備註 |
|----|-----|------|
| `recency_max_bars` | 6, 8, 10 | 唯一 sweep 軸 |
| `stretch_k` | 1.5 | 固定 |
| `upper_buf_k` / `lower_buf_k` | 0.12 / 0.05 | 固定 |
| `hard_stop_atr_k` / `tp_atr_k` | 1.0 / 1.8 | 固定 |
| 出場 variant | `atr_barrier_1200s` | 對齊 ORB naming |

**最佳組選取**：01–03 內 **net/趟最高** 且 G1–G3 全過；平手取 **n 較大** 者。

## 9. Audit 與產物

| 產物 | 路徑 |
|------|------|
| CF JSON（01–03） | `workspaces/vtp-baseline/reports/counterfactual_vtp_0103.json` |
| CF JSON（04 valid） | `workspaces/vtp-baseline/reports/counterfactual_vtp_valid.json` |
| Gate report | `workspaces/vtp-baseline/gate_report.md` |
| Funnel | `workspaces/vtp-baseline/reports/entry_funnel_vtp.json` |
| CLI | `apps/trading-app/src/scripts/ft010_vtp_counterfactual.py` |

`SIGNAL_AUDIT reason=vwap_trend_pullback`；欄位 MUST 含：`stretch_high`, `recency_bars`, `session_vwap`, `atr`, `buffer_touch`, `session_bucket`, `direction=long`。

## 10. Definition of Done

### Phase 0

- [ ] 本 SPEC + [`PLAN.md`](PLAN.md)
- [ ] `vwap_trend_pullback_counterfactual.py` + `ft010_vtp_counterfactual.py`
- [ ] 01–03 + 04 CF JSON + funnel + `gate_report.md`
- [ ] `strategy_diagnosis.md` §10 決策段

### Phase 1（01–03 過關後）

- [ ] `packages/strategies/vwap-trend-pullback/` plugin
- [ ] `vtp-baseline` config + baseline replay
- [ ] 04 valid baseline JSON

### Phase 2（04 過關 + 人類 Go）

- [ ] 05 holdout **一次** baseline
- [ ] WeeklyStatus + CHANGELOG

**UAT/Live**：全程 **維持** `strategy-vwap-momentum`，直至 FT-010 holdout 過關。

## 11. §Decision — Phase 0 01–03 未過（2026-06-28）

| 欄位 | 值 |
|------|-----|
| 01–03 主判 | **未過** — 無 param 達 n≥30 |
| 01–03 最佳（參考） | `rcy10`：n=**3** gross **+18.95** net **+13.95** |
| 04 valid | **0 筆**（未過） |
| 05 holdout | **未跑**（封印） |
| 漏斗 01–03 | stretch 日 54/54；buffer touch 15；轉化 **27.8%** |
| Phase 0 方向 | **long-only** |
| 決策 | **MVPClosed at Phase 0**（`thesis_g_vtp_no_go`）— 不開 plugin |
| UAT | **維持** vwap-momentum |

產物 SSOT：[`workspaces/vtp-baseline/gate_report.md`](../../../workspaces/vtp-baseline/gate_report.md)。

## 參考

- PLAN：[`PLAN.md`](PLAN.md)
- FT-003 診斷：[`strategy_diagnosis.md`](../../../workspaces/strategy_diagnosis.md) §6–§7
- 波動基線：[`VOLATILITY_BASELINE.md`](../../../workspaces/VOLATILITY_BASELINE.md)
- 漏斗方法：[`ENTRY_FUNNEL_METRICS.md`](../ai-backtest-tuning/ENTRY_FUNNEL_METRICS.md)
- FT-006 對照：[`vwap-stretch-fade/SPEC.md`](../vwap-stretch-fade/SPEC.md)
- FT-009 通關範本：[`opening-range-breakout/SPEC.md`](../opening-range-breakout/SPEC.md)
- v1 凍結：[`packages/strategies/vwap-momentum/SPEC.md`](../../../packages/strategies/vwap-momentum/SPEC.md)
