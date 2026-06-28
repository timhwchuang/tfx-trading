# Thesis Queue — Alpha 提案佇列

> **用法**：Agent **可**填 `draft-proposal`；人類 **Pick 一個**改 `human-approved` 後才准 Phase 0 CF。  
> Playbook：[`ALPHA_RESEARCH_PLAYBOOK.md`](../docs/features/ai-backtest-tuning/ALPHA_RESEARCH_PLAYBOOK.md) · 提案規則 **§5.1**

**狀態**：`draft-proposal` → `human-approved` → `in-cf` → `mvpclosed` | `holdout-pending` | `landed`  
**Rejected** 列保留原因，避免重提案。

---

## 佇列總覽

| ID | 工作標題 | 狀態 | 機制 | collision | 下一步 |
|----|----------|------|------|-----------|--------|
| P-001 | Regime VWAP stretch fade | `mvpclosed` | mean-reversion | — | FT-012 已結 |
| P-002 | Midday liquidity pause fade | `rejected` | mean-reversion | **high** | fade 整族已死 |
| P-003 | Opening gap inventory fade | `draft-hold` | mean-reversion | **high** | 需改觸發或否決 |
| P-004 | Morning VWAP hold pullback long | `draft-proposal` | **continuation** | low | 等人類 Pick |
| P-005 | Gap drive continuation | `draft-proposal` | **continuation** | med | 等人類 Pick |
| P-006 | Midday range expansion long | `draft-proposal` | **continuation** | med | 等人類 Pick |
| P-007 | SuperTrend flip continuation | `draft-proposal` | **continuation** | low | 等人類 Pick |
| P-008 | Bollinger squeeze breakout | `draft-proposal` | **continuation** | **high** | 等人類 Pick（breakout 族） |
| P-009 | FVG retest pullback | `draft-proposal` | **liquidity** | med | 等人類 Pick |

---

## P-002 — Midday liquidity pause fade（**rejected**）

**狀態**：`rejected` · **日期**：2026-06-28 · **原因**：FT-012 驗屍 — fade 整族死；僅改時段（11:00–12:30）≠ 新進場機制。

---

## P-003 — Opening gap inventory fade（**draft-hold**）

**狀態**：`draft-hold` · **提議者**：Agent · **日期**：2026-06-28

**故事**：開盤 gap > k×ATR → 短線 inventory 調整，partial fill 回 prior close。

**碰撞風險**：仍為 **gap fade / mean-reversion**；與 FT-006/012 同族精神。

**粗算錨點**：FT-012 k2_p30 gross **+0.75**、W30 stop-less median **+4** 仍 net 負 → 本案若 gross 目標 6+ 無根據。

**若要復活**：必須改為 **gap 方向 continuation**（見 P-005）或人類書面說明與 fade 整族之本質差異。

---

## P-004 — Morning VWAP hold pullback long

**狀態**：`draft-proposal` · **提議者**：Agent · **日期**：2026-06-28 · **collision**：low

**故事**：09:15–10:30，價格 **持續在 VWAP 上方**（開盤 drive），第一次回踩 VWAP 且 1m 量縮 → **做多**順勢延續（非 fade）。

**不是 FT-006/012 因為**：進場是 **順勢回踩買入**；觸發為「VWAP 支撐 + 量縮」，非 |z| 超標反向。

**粗算錨點**：FT-003 timeout 子集 W180 **+35**（順勢未成交）— 假設可截取類似路徑；預期 n 60–120；gross 目標 **3–6**（保守，仍須過 G1）。

**Falsify**：train W30 stop-less median ≤ 0 → 順勢 thesis 錯；post_entry 附錄 MUST 進 gate_report。

---

## P-005 — Gap drive continuation

**狀態**：`draft-proposal` · **提議者**：Agent · **日期**：2026-06-28 · **collision**：med

**故事**：開盤 gap > k×ATR（k∈{1.0,1.5}），前 30 分鐘 **回撤 < gap×40%** 後再破開盤後高點 → **順 gap 方向**進場（多 gap up / 空 gap down）。

**不是 P-003 因為**：不做 inventory fade；等 **gap 方向確認**後 continuation。

**不是 FT-009 因為**：不用 opening range 邊界；觸發是 **gap 結構 + 回撤深度**。

**粗算錨點**：FT-009 ORB train 全負 — 同為 breakout 族，預期 gross **2–5**（不樂觀）；n 估 40–80。

**Falsify**：Long/Short 單邊 §3.1；W15 stop-less 雙邊皆負 → MVPClosed。

---

## P-006 — Midday range expansion long

**狀態**：`draft-proposal` · **提議者**：Agent · **日期**：2026-06-28 · **collision**：med

**故事**：11:00–12:00 形成 30m **窄幅**（range < 0.5×ATR），12:00 後向上突破 + vol_1s > 早盤 p60 → **做多**（順突破，非 fade 回中軸）。

**不是 P-002 因為**：P-002 做假突破 fade；本案做 **真突破順勢** + 量確認。

**不是 FT-011 因為**：不用 session confluence / OR 堆疊；單一 midday range 觸發。

**粗算錨點**：FT-011 SCB train 負 — breakout 族需保守；gross 目標 **3–6**；n 50–90。

**Falsify**：funnel 顯示突破後 W30 median ≤ 0 → 假突破為主 → MVPClosed。

---

## P-007 — SuperTrend flip continuation

**狀態**：`draft-proposal` · **提議者**：Agent · **日期**：2026-06-28 · **collision**：low · **來源**：TradingView SuperTrend

**故事**：5m kbar 上 SuperTrend（HL/2 ± k×ATR）**翻多**後，09:15–12:00 內 tick 確認收在 trend line 上方 → **做多**；翻空對稱做空（或 Phase 0 先 **long-only** 對照 P-004）。

**不是 FT-004/005 因為**：不用 tick `momentum_armed` + pullback 兩段式；觸發是 **kbar 級 band flip**，非秒級爆量觸發。

**不是 P-004 因為**：不用 VWAP 支撐；進場信號是 **ATR 通道方向翻轉**，非 VWAP 回踩。

**不是 FT-009 因為**：無 opening range；訊號可全日多次 flip（需 **cooldown** 防 whipsaw）。

**粗算錨點**：FT-004/005 continuation No-Go（armed 全進）— 本案有 **flip + cooldown** 過濾；預期 n **80–150**；gross 目標 **3–6**（保守）。

**Pre-register 草圖**：ATR period ∈ {10,14} · mult ∈ {2.5,3.0,3.5} · cooldown_bars ∈ {3,6} · session 09:15–12:00。

**Falsify**：train flip 後 W30 stop-less median ≤ 0 且 n≥30 → whipsaw 為主 → MVPClosed；Long/Short 單邊 §3.1。

---

## P-008 — Bollinger squeeze breakout

**狀態**：`draft-proposal` · **提議者**：Agent · **日期**：2026-06-28 · **collision**：**high** · **來源**：TradingView BB Breakout

**故事**：5m Bollinger（period 20, σ∈{2,2.5}）**bandwidth < p20**（squeeze）後，**close 突破上軌** + vol_1s > 早盤 p50 → **做多**（09:30–11:30）；下破下軌做空（或 long-only）。

**不是 FT-009 因為**：觸發是 **波動壓縮後擴張**（BB width percentile），非固定 OR 高低點 first break。

**不是 P-006 因為**：P-006 用 midday **窄幅 range**；本案用 **BB bandwidth 分位** + 帶外 close，非 30m box。

**不是 FT-011 因為**：不用 session confluence / OR 堆疊；單一 **squeeze → expansion** 條件鏈。

**碰撞警告**：仍屬 **breakout 整族**（Playbook §4：009/011 train 皆負）；僅在「壓縮→爆發」機制與 OR 不同時才值得 CF。

**粗算錨點**：FT-011 SCB train gross **+0.39** net **−4.61**（n=72）；FT-009 v2.1 train **全負** — 預期 gross **2–4**（不樂觀）；n 估 **50–100**。

**Falsify**：squeeze 子集 net 仍 ≤ 0 → 波動擴張亦無 edge → MVPClosed；勿以 valid 單月 rm30 表面正（SCB overfit 前例）作 Go 依據。

---

## P-009 — FVG retest pullback

**狀態**：`draft-proposal` · **提議者**：Agent · **日期**：2026-06-28 · **collision**：med · **來源**：TradingView FVG Pullback / SMC

**故事**：5m 偵測到 **同向 BOS** 後留下未 mitigated FVG；價格 **回測 FVG zone**（tick 進 zone 且 1m 量縮）→ **順 BOS 方向**進場（09:15–12:30）。FVG 定義複用 FT-002 §4.7（完全填補才 mitigated）。

**不是 FT-002 因為**：FT-002 把 FVG 當 **pullback 濾網**（veto）；本案 FVG zone 是 **進場觸發**，非附屬 filter。

**不是 P-004 / FT-010 因為**：回踩錨點是 **結構缺口**（gap between b0/b2），非 VWAP 或 stretch-to-buffer。

**不是 FT-011 因為**：不用 OR / session confluence；單一 **BOS → FVG → retest** 因果鏈。

**粗算錨點**：FT-010 VTP n≪30（pullback 低頻）；FT-002 filter 放棄 — 本案預期 n **40–80**（BOS+FVG 漏斗較窄）；gross 目標 **4–7**（結構回踩理論上 R:R 較好，仍須過 G1）。

**Pre-register 草圖**：5m bucket · BOS swing lookback ∈ {3,5} · retest 需 `vol_1s ≤ p40` · max_fvg_age_bars ∈ {6,12}。

**Falsify**：funnel `bos→active_fvg→zone_touch→entry` 轉化 < 5% 或 train n < 30 → 結構信號太稀 → MVPClosed；W30 stop-less median ≤ 0 → 假 FVG 為主。

---

## 已決議

| ID | 決策 | 日期 | 原因 |
|----|------|------|------|
| P-001 | **mvpclosed** → FT-012 | 2026-06-28 | train 全負；regime 未救 VSF |
| P-002 | **rejected** | 2026-06-28 | midday fade = fade 整族變形 |

---

## 人類操作

1. 自 **P-004～P-009** **Pick 一個** → `human-approved`（或全否決附原因）
2. **優先序建議**（Agent 自評）：P-007（低碰撞）≈ P-009（新機制）> P-004/005/006 > **P-008**（breakout 族高碰撞，除非明確想驗 squeeze）
3. 批准後：「依 Playbook 開 FT-013 `<slug>` Phase 0」
4. P-003 若要復活：先改 thesis 或明確反駁 §4 fade 整族禁令
