# Thesis Queue — Alpha 提案佇列

> **用法**：Agent **可**填 `draft-proposal`；人類 **Pick 一個**改 `human-approved` 後才准 Phase 0 CF。  
> Playbook：[`ALPHA_RESEARCH_PLAYBOOK.md`](../docs/features/ai-backtest-tuning/ALPHA_RESEARCH_PLAYBOOK.md) · 提案規則 **§5.1**  
> **Gate SSOT**：[`HOLDOUT_CONTRACT_v2.md`](../docs/features/ai-backtest-tuning/HOLDOUT_CONTRACT_v2.md) **v2.2.1** — `mean_robust`（預設）| **`skew`**（低頻厚尾）

**狀態**：`draft-proposal` → `human-approved` → `in-cf` → `mvpclosed` | `holdout-pending` | `landed`  
**Rejected** 列保留原因，避免重提案。

---

## 佇列總覽

| ID | 工作標題 | 狀態 | 機制 | class | collision | 下一步 |
|----|----------|------|------|-------|-----------|--------|
| P-001 | Regime VWAP stretch fade | `mvpclosed` | mean-reversion | — | — | FT-012 已結 |
| P-002 | Midday liquidity pause fade | `rejected` | mean-reversion | — | **high** | fade 整族已死 |
| P-003 | Opening gap inventory fade | `draft-hold` | mean-reversion | — | **high** | 需改觸發或否決 |
| P-004 | Morning VWAP hold pullback long | **`mvpclosed`** → FT-014 | **continuation** | mean_robust | low | train n=7 · W30 med +38 · vol_shrink 過稀 |
| P-005 | Gap drive continuation | **`mvpclosed`** → FT-016 | **continuation** | **skew** | med | W30 med +13 · grid G1 fail · valid net−9 |
| P-006 | Midday range expansion long | `draft-proposal` | **continuation** | mean_robust | med | 等人類 Pick |
| P-007 | SuperTrend flip continuation | **`mvpclosed`** | **continuation** | mean_robust | low | FT-013 · `stf_fingerprint_fail` |
| P-008 | Bollinger squeeze breakout | `rejected` | **continuation** | — | **high** | breakout 族 · gross 天花板 |
| P-009 | FVG retest pullback | **`mvpclosed`** → FT-015 | **liquidity** | **skew** | med | W30 med −0 · n=211 |
| P-010 | Compression flow attack | **`mvpclosed`** → FT-017 | **liquidity** | **skew** | med | `cfa_fingerprint_fail` · n=0 |
| P-011 | Gap up drive trail | `draft-proposal` → FT-018 | **continuation** | **skew** | med | **0-design PASS** · 待 Pick → [`PLAN` Phase 0a prompt](../../docs/features/gap-up-drive-trail/PLAN.md) |
| P-012 | Sweep FVG breakout trail | `draft-proposal` → FT-019 | **liquidity** | **skew** | med | **0-design PASS** · 待 Pick → [`PLAN`](../../docs/features/sweep-fvg-breakout-trail/PLAN.md) |

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

## P-004 — Morning VWAP hold pullback long → **FT-014**（**MVPClosed**）

**狀態**：**`mvpclosed`** · **outcome**：`mvhp_fingerprint_fail` · **日期**：2026-06-28 · **class**：**mean_robust** · **FT**：[`morning-vwap-hold-pullback`](../../docs/features/morning-vwap-hold-pullback/SPEC.md) · [`gate_report`](mvhp-baseline/gate_report.md)

**0c-1（2026-06-28）**：train n=**7**（G3 不過）· W30 stop-less med **+38** · barrier gross/趟 24 · funnel hold→entry 4.3% · vol_shrink 瓶頸（77 touch → 7 entry）。post_entry `direction_ok_margin_thin` — **方向弱正但樣本過稀，禁 grid**。

**Pick A（2026-06-28）**：post FT-013 · 延續 mean_robust continuation 族。

---

## P-008 — Bollinger squeeze breakout（**rejected**）

**狀態**：`rejected` · **日期**：2026-06-28 · **原因**：資深交易員 + v2.2 前評估 — breakout 高碰撞；gross 目標 2–4 **< friction 5**（G1 前已死）。**不因 v2.2 skew 復活**（機制未變）。

---

## P-005 — Gap drive continuation → **FT-016**（**MVPClosed**）

**狀態**：**`mvpclosed`** · **outcome**：`gdc_fingerprint_pass_g1_fail` · **class**：**skew** · [`gate_report`](gdc-baseline/gate_report.md)

**0c-1（2026-06-28）**：n=**79** · W30 stop-less med **+13** · barrier gross/趟 3.29 · post_entry `exit_kills_edge`（barrier med −1 · W30 順向）。

**0c-2**：36 combos 全敗 G1（best gross 4.3 < 5 或 net≤0）· valid Q1 n=15 net **−9.28** · holdout 硬擋。

**Pick（2026-06-28）**：Tim Pick P-005 → FT-016 · 0-design PASS → 0a–0c 完。

---

## P-006 — Midday range expansion long

**狀態**：`draft-proposal` · **提議者**：Agent · **日期**：2026-06-28 · **collision**：med

**故事**：11:00–12:00 形成 30m **窄幅**（range < 0.5×ATR），12:00 後向上突破 + vol_1s > 早盤 p60 → **做多**（順突破，非 fade 回中軸）。

**不是 P-002 因為**：P-002 做假突破 fade；本案做 **真突破順勢** + 量確認。

**不是 FT-011 因為**：不用 session confluence / OR 堆疊；單一 midday range 觸發。

**粗算錨點**：FT-011 SCB train 負 — breakout 族需保守；gross 目標 **3–6**；n 50–90。

**Falsify**：funnel 顯示突破後 W30 median ≤ 0 → 假突破為主 → MVPClosed。

---

## P-007 — SuperTrend flip continuation → **FT-013**

**狀態**：**`mvpclosed`** · **簽核**：Tim · **日期**：2026-06-28 · **class**：**mean_robust** · **FT**：[`supertrend-flip`](../../docs/features/supertrend-flip/SPEC.md)

**結案（2026-06-28）**：Phase 0c-1 fingerprint 未過 — train 2025 W30 stop-less gross median **−10.0**（n=67）→ **`stf_fingerprint_fail`** · grid 跳過 · [`gate_report`](../../workspaces/stf-baseline/gate_report.md)

**Phase 0 約束**（封印 · [`SPEC §5.1`](../../docs/features/supertrend-flip/SPEC.md)）：**long-only** · MUST-1 無 repaint · MUST-2 滑價/摩擦 · MUST-3 cooldown+12:00 · **0c-1 fingerprint 先於 grid**（W30 median 順勢指紋）。

**故事**：5m kbar 上 SuperTrend（HL/2 ± k×ATR）**翻多**後，09:15–12:00 內 tick 確認收在 trend line 上方 → **做多**。

**不是 FT-004/005 因為**：不用 tick `momentum_armed` + pullback 兩段式；觸發是 **kbar 級 band flip**，非秒級爆量觸發。

**不是 P-004 因為**：不用 VWAP 支撐；進場信號是 **ATR 通道方向翻轉**，非 VWAP 回踩。

**不是 FT-009 因為**：無 opening range；訊號可全日多次 flip（需 **cooldown** 防 whipsaw）。

**粗算錨點**：FT-004/005 continuation No-Go（armed 全進）— 本案有 **flip + cooldown** 過濾；預期 n **80–150**；gross 目標 **3–6**（保守）。

**Pre-register 草圖**：見 SPEC §5.0（grid 僅 fingerprint 過後 tune）。

**Falsify**：0c-1 W30 stop-less median ≤ 0 → **即 MVPClosed**（不扫 mult）；§3.1 long 欄。

---

## P-009 — FVG retest pullback → **FT-015**（**MVPClosed**）

**狀態**：**`mvpclosed`** · **outcome**：`frp_fingerprint_fail` · **class**：**skew** · [`gate_report`](fvg-baseline/gate_report.md)

**0c-1（2026-06-28）**：n=**211** · W30 stop-less med **−0.0** · barrier gross/趟 0.33 · Long W30 +2 / Short −2 · post_entry `direction_weak` · **grid 跳過**。

---

## P-010 — Compression flow attack → **FT-017**（**MVPClosed**）

**狀態**：**`mvpclosed`** · **outcome**：`cfa_fingerprint_fail` · **class**：**skew** · [`gate_report`](cfa-baseline/gate_report.md)

**0c-1（2026-06-28）**：train n=**0** · W30 med **—** · funnel session=241 → compress=**0** → regime=233 → quiet=240 → attack=236 → entry=**0** · **瓶頸**：attack 觸發時 `signal_1m` 從未 compress_pass（封印 A 同時評估）· **grid 跳過**。

**Pick（2026-06-28）**：資深 TXF 0-design PASS → 0a–0b → 0c-1 fail。

---

## P-011 — Gap up drive trail → **FT-018**（**draft-proposal**）

**狀態**：`draft-proposal` · **提議者**：Agent · **日期**：2026-06-28 · **class**：**skew** · **FT**：[`gap-up-drive-trail`](../../docs/features/gap-up-drive-trail/SPEC.md) · **0-design Conditional PASS**（2026-06-29 · P0 封印）

**故事**：**Exit-led** — **reuse** FT-016 gap-up drive 進場 P0 · **新** `atr_trail_skew_900s` 出場（BE@1× → trail@2×@0.5 → TP@4×）· **long-only** · fingerprint **W900**。

**不是 FT-016 復活**：新 FT 編號 · 新 `EXIT_VARIANT` · Playbook §5.2 · **禁止** 016 內改 exit 重跑 grid。

**不是 P-003**：順 gap **做多** · 非 fade。

**粗算錨點**：FT-016 fp W30 **+13** · barrier med **−1** · MFE **~25** · valid net **−9.28** · post_entry **`exit_kills_edge`** · `exit_gap` **~26**。

**碰撞風險**：med — 進場同族 · 但 exit-led + long-only 降維。

**Falsify**：W900 median ≤ 0 → `gudt_fingerprint_fail_direction`；grid G1 fail 且 exit_gap 仍大 → MVPClosed · 禁第三 exit 變形。

**下一步**：P-011 **`human-approved`** → Phase 0a CF · **0c train 不得**跳步。

---

## P-012 — Sweep FVG breakout trail → **FT-019**（**draft-proposal**）

**狀態**：`draft-proposal` · **提議者**：Agent · **日期**：2026-06-29 · **class**：**skew** · **FT**：[`sweep-fvg-breakout-trail`](../../docs/features/sweep-fvg-breakout-trail/SPEC.md) · **0-design Conditional PASS**（2026-06-29 · P0 封印）

**故事**：**Long-only** — 1m swing low **浅扫**（`sweep_k×ATR`）→ **120s reclaim** → **5m bullish FVG** → tick **breakout > fvg_high**；初始 stop **`fvg_mid`**；动态 **`fvg_mid_trail_skew_900s`**（BE/trail 锚 `risk_unit`）；`fingerprint W900`。

**不是 FT-015 復活**：**breakout** 非 zone retest · **fvg_mid trail** 非 `atr_barrier` · sweep 前置链 · **非** 固定 1:2 主 TP。

**不是 FT-018 GUDT**：无 gap drive · stop 非 ATR 主锚 · 有 sweep+FVG。

**粗算錨點**：FT-015 n=**211** · barrier gross **0.33** · MFE **~17** · **W900 +1.0** · Long W900 **+3.0**（**非**纯方向死 · legacy W1800 gate −0.0）→ **`exit_kills_edge`** 叙事。

**预期 n**：**25–50**（sweep+breakout+long-only · 有 **fail_n** 风险）。

**碰撞風險**：**med** — structure/liquidity 族 · 与 FRP 同 detector 但 **进场触发不同**。

**Falsify**：W900 ≤ 0 → `sfbt_fingerprint_fail_direction`；n<15 → `sfbt_fingerprint_fail_n`；G1 fail + 大 exit_gap → MVPClosed。

**下一步**：資深 TXF **0-design Conditional PASS**（2026-06-29）→ 人類 **`human-approved`**（建议 **P-011 0c-1 后** Pick）→ Phase 0a。

---

## 已決議

| ID | 決策 | 日期 | 原因 |
|----|------|------|------|
| P-001 | **mvpclosed** → FT-012 | 2026-06-28 | train 全負；regime 未救 VSF |
| P-002 | **rejected** | 2026-06-28 | midday fade = fade 整族變形 |
| P-008 | **rejected** | 2026-06-28 | breakout 族 + gross 天花板 < friction 5 |
| P-007 | **mvpclosed** → FT-013 | 2026-06-28 | train W30 med −10 · 0c-1 fingerprint fail |
| P-004 | **mvpclosed** → FT-014 | 2026-06-28 | train n=7 · `mvhp_fingerprint_fail` · grid 跳過 |
| P-009 | **mvpclosed** → FT-015 | 2026-06-28 | W30 med −0 · n=211 · `frp_fingerprint_fail` |
| P-005 | **mvpclosed** → FT-016 | 2026-06-28 | fingerprint W30 +13 · grid G1 fail · valid net−9 |
| P-010 | **mvpclosed** → FT-017 | 2026-06-28 | n=0 · compress@trigger 瓶頸 · `cfa_fingerprint_fail` |

---

## 人類操作

1. **P-011 / FT-018** · **P-012 / FT-019** — 0-design 審閱 / Pick（建议 **串行** · 一次 Pick 一個）→ [`gap-up-drive-trail/PLAN`](../docs/features/gap-up-drive-trail/PLAN.md) · [`sweep-fvg-breakout-trail/PLAN`](../docs/features/sweep-fvg-breakout-trail/PLAN.md) Phase 0a prompt
2. **P-006** — 仍 `draft-proposal` · 等人類 Pick
3. **v2.2.1 不復活 FT 屍體** — 見 Holdout §11
