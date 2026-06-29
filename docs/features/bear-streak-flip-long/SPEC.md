---
id: FT-020
slug: bear-streak-flip-long
status: Draft
thesis_class: mean_robust
proposal_id: P-013
opened: 2026-06-29
owner: Tim (draft-proposal 2026-06-29)
target: Alpha Phase 0
holdout_contract: v2.2.1
design_review: senior-trader 2026-06-29 — Conditional PASS (P0 sealed)
parent_ft: null
---

# FT-020 — Bear Streak Flip Long（SPEC）

> **Proposal**：[`P-013`](../../../workspaces/THESIS_QUEUE.md) · **Gate**：[`HOLDOUT_CONTRACT_v2.md`](../ai-backtest-tuning/HOLDOUT_CONTRACT_v2.md) v2.2.1 · **`thesis_class: mean_robust`**

## 1. Summary（THESIS_BRIEF §A–B）

**一句話**：09:15–12:00，1m **連續 ≥4 根黑K** 後出現 **反轉陽K收盤**，且收盤後 **tick 買盤 ratio 湧入** → **做多**；初始停損 = **最後一根黑K最低**（含 ATR/min_pts 地板）；停利 = **`tp_r × risk_unit`** barrier；`max_hold_sec=900`。

**錯價因果**

- **誰在錯**：連續賣壓 K 線後，過度追空 / 停損單堆在結構低點下方；反轉初段仍有人逆勢放空
- **何時**：09:15–12:00（交易所時間 · 早盤至午盤前段）
- **機制**：**mean-reversion** — streak exhaustion + tick 買盤接貨（**非** VWAP z-score fade）

**Edge 經濟學（設計審閱 · 封印認知）**

- **同族錨點（FT-007 MER）**：n=**108** · gross **+1.25**/趟 · net **−3.75** · direction_weak — **不得**無根據樂觀
- **Fade 族錨點（FT-012 RVSF）**：W30 stop-less med **+4** · margin thin · holdout 未過 — revert 敘事整體偏弱
- **G1 張力**：預期 gross **2–5**/趟；structure stop 窄時 R-multiple TP **難**壓過 **5 點** friction
- **碰撞**：與 FT-007 近親（連續 K + tick flow）— 本案 **無** impulse body/climax/footprint · **結構 stop + R TP** 非 scalp 固定點

## 2. 與已死 thesis 差異（§C）

| 最接近的舊 FT | 為何不是同一個 |
|---------------|----------------|
| **FT-007 MER** | 要 impulse 量價 + climax + absorption scalp 30–120s；本案 **同色 streak + 單根反轉 + 輕量 buy surge** |
| **FT-006/012 fade** | 錨點 **VWAP z-score / stretch**；本案 **純 K 線 streak + 結構低點 stop** |
| **FT-013 STF** | 5m SuperTrend **flip continuation**；本案 **1m 反轉 revert** |
| **P-002 midday fade** | **fade 回中軸**；本案 **順 tick 買盤做多** |
| **FT-004/005** | tick `momentum_armed` 延續；本案 **kbar streak + flow confirm** |

## 3. 進出規則（§D · 可程式化）

| 項目 | 定義 |
|------|------|
| 方向 | **Long-only** |
| 進場 | §5.1 MUST-1 streak+reversal · MUST-2 tick buy surge |
| 停損 | **結構**：最後 bear bar `low` + floor（§5.1 MUST-3） |
| 停利 | **`tp_r × risk_unit`** · §5.0b `structure_r_barrier_900s` |
| 時間出場 | `max_hold_sec=900` · **12:00** 後禁新倉 |
| 日內 flatten | **是** · max **3** 筆/日 |

### D.1 Exit variant（MUST · Phase 0 封印）

| 欄位 | 值 |
|------|-----|
| `EXIT_VARIANT` | **`structure_r_barrier_900s`** |
| `max_hold_sec` | **900** |
| Stop | `effective_stop = entry − stop_dist`（§5.1 MUST-3） |
| TP | `entry + tp_r × risk_unit` |
| Tie-break | stop vs TP 同 tick → **stop 優先** |

## 4. 頻率與 Gate 粗算（§E）

| 項目 | 估計 |
|------|------|
| train 2025 預期 n | **60–120**（G3 **≥30** · 見 §E.4 鏈式粗算） |
| 預期 gross/趟 | **2–5**（須 mean **> 5** 過 G1） |
| 預期 net/趟（扣 5 點） | 邊緣 — 以 CF 為準 |

### E.1 粗算錨點（MUST · 避免 P-001 式幻想）

| 最接近同族 MVPClosed | v2.2.1 train 實績 |
|----------------------|-------------------|
| **FT-007 MER** | n=108 · gross **+1.25** · net **−3.75** · direction_weak |
| **FT-012 RVSF** | W30 med **+4** · barrier net 負 · holdout 掛 |

**規則**：預期 gross **不得**無根據高於 **5**；若 W900 median ≤ 0 → 整族 revert 弱 → MVPClosed。

#### E.1.1 Baseline 欄位映射

| gate / 參數 | metric 類型 | baseline 欄位或手算來源 | 備註 |
|-------------|-------------|-------------------------|------|
| 1m range | `range_aggregate` | `range_1m.p50`（§A） | streak 尺度參考 |
| ATR stop floor | `atr_multiple` | `ATR20.p50`（§A） | `min_stop_atr_k × ATR` |
| flip vol | `vol_floor` | FT-007 `DEFAULT_MIN_FLIP_VOL=25` | tick confirm |
| buy_ratio | `vol_percentile` | FT-007 flow flip 經驗 | 非 §B vol_1s 門檻 |
| stall price | `atr_multiple` | `ATR20.p50`（§A）· MER `stall_atr_k=0.35` | `|Δprice| ≤ 0.35×ATR` · stall_pts≈8.75 @ ATR25 |

### E.2 進場機制標籤（MUST 勾一）

- [ ] **Continuation**
- [x] **Mean-reversion**（streak exhaustion revert · **非** VWAP fade）
- [ ] **Liquidity / microstructure**
- [ ] **Other**

### E.3 Thesis class（v2.2 · MUST 勾一）

- [x] **`mean_robust`** — Gate §3.1 · G3 n≥30
- [ ] **`skew`**

### E.4 Gate Coverage Preflight（MUST · human-approved 之前）

> SSOT：[`GATE_COVERAGE_PREFLIGHT.md`](../ai-backtest-tuning/GATE_COVERAGE_PREFLIGHT.md)

| gate_id | metric_def | baseline_column | threshold | est_pass_rate_train | est_annual_n | core? | verdict |
|---------|------------|-----------------|-----------|---------------------|--------------|-------|---------|
| streak_bear | 連續 ≥4 bear 1m bar 結束 | 獨立近似 P(bear)≈0.5 | min_streak=4 | ~**3%**/bar | — | Y | **PASS** |
| reversal_bull | streak 後首根 bull 收盤 | 條件 ~50% · doji 中斷 | close>open | ~**1.5%**/bar | — | Y | **PASS** |
| tick_flip | flip_window buy_ratio+vol | FT-007 `vol≥25` | ratio≥0.55, vol≥25 | ~**40%** of reversal arms | — | Y | **PASS** |
| stall_price | reversal→confirm 價格 stall | ATR20.p50 · MER stall | `\|Δprice\| ≤ 0.35×ATR14` | ~**37%** of tick_flip pass | **60–120** | Y | **PASS** |

**鏈式粗算（FT-017 式反省 · train 上會不會有樣本）**

| 階段 | 算式 | 粗算 n/年 |
|------|------|-----------|
| reversal arms | `247 × 165 × 0.015` | ~**612**/年 |
| → tick_flip confirm | × **0.40** | ~**245**/年 |
| → stall_price pass | × **0.37** | ~**91**/年 |
| → entry（保守） | 扣 doji/chop/時段 · **60–120** | **PASS**（mean_robust ≥15） |

> **說明**：舊稿「≈90/年」= **post-stall** 鏈（245×0.37≈91），非 reversal arm 全量。`max_trades_per_day=3` 為執行封頂，**不**用於解釋 preflight 落差。

| Preflight 整案 | |
|----------------|--|
| 結果 | **PASS** |
| 日期 | 2026-06-29 |
| 審核 | 資深 TXF · **Senior 簽數字 PASS**（2026-06-29 · stall 列補齊 · 算式自洽） |

## 5. Pre-register（§F · 開 CF 前封印）

### 5.0 參數 grid（**僅** fingerprint **通過後** tune · 見 §5.2）

| 參數 | 值 / 範圍 | Fingerprint 凍結 |
|------|-----------|-------------------|
| `min_streak` | {3, 4, 5} | **4** |
| `flip_window_sec` | {30, 45, 60} | **45** |
| `flip_buy_ratio_min` | {0.52, 0.55, 0.58} | **0.55** |
| `flip_vol_min` | **25** | 封印 |
| `flip_confirm_timeout_sec` | **120** | 封印 |
| `stall_atr_k` | **0.35** | 封印（core gate） |
| `tp_r` | {1.5, 2.0, 2.5} | **2.0** |
| `min_stop_atr_k` | **0.75** | 封印 |
| `min_stop_pts` | **8** | 封印 |
| `min_atr_pts` | **25.0** | 封印 |
| `atr_period` | **14** | 封印 |
| `cooldown_bars` | **5** | 封印 |
| `max_trades_per_day` | **3** | 封印 |
| session entry | **09:15–12:00** | 封印 |
| `no_new_entry_after` | **12:00** | 封印 |
| `last_entry_before` | **11:45** | 封印 |
| **方向** | **long-only** | 封印 |

**日期封印**：valid `2026-01-01`～`2026-03-31` · holdout `2026-04-01`～`2026-06-30` — **不得**依結果增刪參。

#### 5.0b Exit sim（0c-1 / 0c-2 共用 · 封印）

| 項目 | 值 |
|------|-----|
| 函式 | **`simulate_structure_r_barrier_exit`**（Phase 0a **新實作**） |
| `EXIT_VARIANT` | **`structure_r_barrier_900s`** |
| Stop | tick path 觸 `effective_stop`（§5.1 MUST-3） |
| TP | `entry + tp_r × risk_unit` |
| `max_hold_sec` | **900** |
| Entry 價 | **tick close** @ flip confirm |
| 摩擦 | **5** 點 round-trip |
| Tie-break | stop vs TP 同 tick → **stop 優先** |
| 逾時 | **900s** mark-to-market @ 當 tick close |

**MUST — 每 tick 狀態機（P0 · 0a 封印 · 逐 tick 升序 · long）**

| 步驟 | 動作 |
|------|------|
| 1 | 若 `close ≤ effective_stop` → **stop 出場** @ effective_stop |
| 2 | 若 `close ≥ tp_price`（`entry + tp_r × risk_unit`）→ **TP 出場** @ tp_price |
| 3 | 若 `entry_ts + max_hold_sec` 到達 → **時間出場** @ 當 tick close |

**同 tick tie-break（P0）**：stop vs TP → **stop 優先**。

#### 5.0c Fingerprint window（v1.5 · MUST）

| 欄位 | 值 |
|------|-----|
| `fingerprint_window_sec` | **900** |
| Gate 讀取 | **W900** `close_delta_median`（stop-less gross） |
| **Primary key** | post_entry / 0c-1 gate **MUST** 以 W900 為 primary · **禁止** W1800 作 gate |
| 對齊 | **=** `max_hold_sec` |
| 通過線 | W900 median **> 0** + G3 **n≥30**（mean_robust） |

### 5.1 Phase 0 封印 MUST

#### MUST-1 — Streak + reversal（1m kbar · 無 repaint）

| 項目 | 封印定義 |
|------|----------|
| K 線 | **僅**用 **已收** 1m bar（`08:45–13:45` session） |
| **Bear** | `close < open`（strict） |
| **Bull reversal** | streak 後第一根 `close > open` 且 **已收盤** |
| **Doji** | `close == open` → **中斷** streak · **不**計入 bear/bull |
| **Streak** | 連續 **≥ `min_streak`** 根 bear（指紋 **4**） |
| **Last bear bar** | reversal 前 streak 中時間序 **最後一根 bear** → `stop_ref_low = bar.low` |
| **Reversal arm ts** | bull reversal bar 的 **1m bucket 收盤時戳**（exchange time） |
| **禁止** | intra-bar 猜測反轉 · partial bar 計入 streak |
| **時段** | reversal arm ts 對應 exchange time **∈ [09:15, 12:00)** |
| **11:45 / 12:00** | 確認 tick `≥ 11:45` → 不 arm；`≥ 12:00` → 禁新進場 |

#### MUST-2 — Tick buy surge（flip confirm · 回答「買盤湧入」）

| 項目 | 封印定義 |
|------|----------|
| 起算 | **`reversal_arm_ts`** 之後（**MUST NOT** 用 reversal bar 內 tick） |
| 窗口 | [`RollingFlowWindow`](../../../apps/trading-app/src/reporting/flow_flip_counterfactual.py) · `window_sec = flip_window_sec` |
| Confirm 條件 | 首 tick 滿足：`buy_ratio ≥ flip_buy_ratio_min` **且** `total_vol ≥ flip_vol_min` |
| **Stall（core）** | 自 `reversal_arm_ts` 至 confirm tick：`\|Δprice\| ≤ stall_atr_k × ATR(14)` @ reversal bar |
| Entry | 該 confirm tick 的 `close` |
| Timeout | `reversal_arm_ts + flip_confirm_timeout_sec`（**120s**）內無 confirm → **放棄** setup |
| **禁止** | reversal 前 tick 預判 · 用 future bar 修正 streak |

#### MUST-3 — 結構停損 + 地板

```
risk_raw     = entry_price - stop_ref_low
atr_effective = max(ATR(14) @ entry bar, min_atr_pts)
stop_dist    = max(risk_raw, min_stop_atr_k × atr_effective, min_stop_pts)
effective_stop = entry_price - stop_dist
risk_unit    = stop_dist
tp_price     = entry_price + tp_r × risk_unit
```

| 項目 | 值 |
|------|-----|
| `min_stop_atr_k` | **0.75** |
| `min_stop_pts` | **8** |
| `min_atr_pts` | **25.0** |

#### MUST-4 — 摩擦 · cooldown · 日內上限

| 項目 | 封印定義 |
|------|-----|
| 摩擦 | 每趟 round-trip **5** 點 |
| `cooldown_bars` | 兩次 entry 間隔 ≥ **5** 根已收 1m bar |
| `max_trades_per_day` | **3** |
| Funnel | `session` → `streak_ok` → `reversal_bar` → **`stall_pass`** → `flip_confirm` → `entry` |

#### MUST-5 — post_entry hook（非 gate）

- CF JSON **MUST** 含 `post_entry_diagnosis_by_param`（**W900** primary · W1800 附錄）
- `gate_report` **MUST**：`exit_gap` · `pct_mfe_ge_1atr`（0a 後）

### 5.2 Phase 0 診斷順序（fingerprint 先於 grid）

| 步驟 | 通過線 |
|------|--------|
| **0c-1 Fingerprint** | **W900** stop-less gross **median > 0** · **n ≥ 30**（G3） |
| **0c-1b direction** | W900 ≤ 0 · n≥30 → **`bsfl_fingerprint_fail_direction`** · **不跑 grid** |
| **0c-1b n** | W900 > 0 · n<30 → **`bsfl_fingerprint_fail_n`** · **不跑 grid** |
| **0c-2 Grid** | G1–G3 · §3.1 mean_robust |

| Scenario | Outcome |
|----------|---------|
| W900 ≤ 0 · n≥30 | `bsfl_fingerprint_fail_direction` |
| W900 > 0 · n<30 | `bsfl_fingerprint_fail_n` |
| W900 > 0 · n≥30 · grid fail | `bsfl_fingerprint_pass_g1_fail` |
| train 過 · valid net≤0 | `bsfl_overfit_suspect` |

### 5.3 Post-entry 診斷（非 gate）

- 模組：[`post_entry_diagnosis.py`](../../../apps/trading-app/src/reporting/post_entry_diagnosis.py)
- **`exit_gap`** ≈ `MFE_median − barrier_gross_median`
- **禁止**依 post_entry 回頭 tune train grid 或改 `fingerprint_window_sec`

### 5.4 Outcome codes

| Code | 條件 |
|------|------|
| `bsfl_fingerprint_fail_direction` | 0c-1 W900 median ≤ 0 · n≥30 |
| `bsfl_fingerprint_fail_n` | W900 > 0 · n<30 |
| `bsfl_fingerprint_pass_g1_fail` | fingerprint 過 · grid G1/G2 不過 |
| `bsfl_overfit_suspect` | train 過 · valid net ≤ 0 |
| `bsfl_train_no_go` | 其他 |
| `spec_anchor_mismatch` | 0-design · upstream gate=0（**非** fingerprint） |

## 6. Falsify（§G）

### G.1 0-design

| Outcome | 條件 | 處置 |
|---------|------|------|
| **`spec_anchor_mismatch`** | streak/flip gate 不可達 · upstream=0 | Revise SPEC/PLAN 或 `design-closed` |

### G.2 Train / valid（0c 之後）

- train net ≤ 0 → MVPClosed
- train 過、valid net ≤ 0 → `overfit_suspect`
- W900 median ≤ 0 · n≥30 → **`bsfl_fingerprint_fail_direction`** · revert 整族弱
- fingerprint 過 · G1 fail · **`exit_gap`** 大 → MVPClosed · **禁止** 第三種 exit 變形（未來 exit-led 須 **新 FT** · Playbook §5.2）
- funnel：streak 多 · flip_confirm 極稀 → **`bsfl_fingerprint_fail_n`**

### G.3 禁止

- VWAP z-score fade 濾網「救」revert
- intra-bar reversal 進場
- 在 FT-020 內改 exit 族重跑 grid

## 7. 人類簽核（§H）

| 欄位 | 值 |
|------|-----|
| 簽核人 | |
| 日期 | |
| 決策 | **pending**（`draft-proposal` · 不搶 P-011 · 建議 P-011 0c-1 後 Pick） |

## 8. 設計審閱（Phase 0-design · 非 Pilot Go）

| 欄位 | 值 |
|------|-----|
| 審閱 | 資深 TXF 交易人員 |
| 日期 | 2026-06-29 |
| 審閱檔案 | 本 SPEC · [`PLAN.md`](PLAN.md) |
| 結論 | **Conditional PASS — P0 已封印** — 准 **human-approved → Phase 0a 準備** · **0c train 待** P-013 Pick（建議 P-011 0c-1 後） |
| Phase 0a prompt | [`PLAN.md`](PLAN.md) §「給 Agent 的 Phase 0a 開工 prompt」 |

### 審閱摘要

- **兩段進場**：K streak+reversal arm → tick buy_ratio+vol+stall — 敘事清楚 · 無 lookahead（MUST-1/2 正確）。
- **與 FT-007 差異**：無 impulse/climax/footprint；**structure stop + 2R barrier** — 近親 med 但可並存 queue。
- **Preflight**：四 core gate PASS；§E.4 已補 **stall_price** 列 · 鏈式粗算 612→245→91/年自洽。
- **G1 張力**：gross 2–5 · 窄 stop 時 fingerprint 過、G1 掛 合理（`bsfl_fingerprint_pass_g1_fail`）。
- **W900 = max_hold 900s**：對齊正確。

### P0（0-design · 已併入 SPEC）

1. §E.4 補 **stall_price** core gate + 鏈式粗算表
2. Funnel 含 **`stall_pass`** 階段
3. §8 / YAML `design_review` Conditional PASS

### P1（0a · 非 block）

1. CF test case **13–15**（stall fail · flip timeout · 11:45 arm 邊界）— 見 PLAN
2. `entry_slippage_sensitivity` · `exit_gap` gate_report 附錄（0b 前）

### Pick P-013 建議

- **0-design**：P0 封印後 **Conditional PASS**。
- **human Pick / 0c train**：**等 P-011 0c-1 結案**（建議 · 不與 P-011 並行 Pick）。

## 9. CF code review（§I · Phase 0b · train 前必填）

| 欄位 | 值 |
|------|-----|
| Review 方式 | Bugbot / 人類 |
| Review 日期 | |
| 審查檔案 | `reporting/bear_streak_flip_long_counterfactual.py` · `reporting/simulate_structure_r_barrier_exit.py` · tests |
| 結果 | pending |
| 備註 | MUST-1/2/3 lookahead · streak 無 repaint · W900 primary |

## 參考

- PLAN：[`PLAN.md`](PLAN.md)
- Playbook：[`ALPHA_RESEARCH_PLAYBOOK.md`](../ai-backtest-tuning/ALPHA_RESEARCH_PLAYBOOK.md)
- Preflight：[`GATE_COVERAGE_PREFLIGHT.md`](../ai-backtest-tuning/GATE_COVERAGE_PREFLIGHT.md)
- 近親 FT-007：[`momentum-exhaustion-reversal/SPEC.md`](../momentum-exhaustion-reversal/SPEC.md) · [`gate_report`](../../../workspaces/mer-baseline/gate_report.md)
- Flow 模板：[`flow_flip_counterfactual.py`](../../../apps/trading-app/src/reporting/flow_flip_counterfactual.py)
- Workspace（待建）：`workspaces/bsfl-baseline/`
