---
id: FT-018
slug: gap-up-drive-trail
status: Draft
thesis_class: skew
proposal_id: P-011
opened: 2026-06-28
owner: Tim (draft-proposal 2026-06-28)
target: Alpha Phase 0
holdout_contract: v2.2.1
design_review: senior-trader 2026-06-29 — Conditional PASS (P0 sealed)
parent_ft: FT-016
exit_led: true
---

# FT-018 — Gap Up Drive Trail（SPEC）

> **Proposal**：[`P-011`](../../../workspaces/THESIS_QUEUE.md) · **Gate**：[`HOLDOUT_CONTRACT_v2.md`](../ai-backtest-tuning/HOLDOUT_CONTRACT_v2.md) v2.2.1 · **`thesis_class: skew`**  
> **Exit-led**：進場 **reuse** FT-016 P0 MUST · 出場 **新** `atr_trail_skew_900s` · **非** FT-016 復活

## 1. Summary（THESIS_BRIEF §A–B）

**一句話**：**Gap-up only** — 開盤 gap > k×ATR 後，09:15–09:45 drive 段回撤 < gap×40%，09:45 後 **破 drive_high** → **做多**；出場用 **ATR trail skew**（BE@1×ATR → trail@2×ATR@0.5 → hard TP 4×ATR）；`max_hold_sec=900`。

**錯價因果**

- **誰在錯**：gap-up drive 確認後，過早止盈 / 固定 barrier 停利 **截斷** 延續腿
- **何時**：09:15–10:30（break 進場窗 · 同 FT-016）
- **機制**：**continuation**（gap-up drive + shallow retrace + breakout）· **exit-led** 驗證 trail 能否收斂 `exit_kills_edge`

**Edge 經濟學（設計審閱 · 封印認知）**

- **母 FT 錨點（FT-016 · 非樂觀假設）**：train fp n=**79** · W30 stop-less med **+13** · barrier gross/趟 **3.29** · barrier med **−1** · MFE med **~25** · valid net **−9.28** → `gdc_fingerprint_pass_g1_fail` · post_entry **`exit_kills_edge`**
- **`exit_gap` 粗算**：MFE med − barrier med ≈ **26pt** — thesis 假設 **trail 可部分捕獲**，**非**保證 G1 gross>5
- **Long-only**：FT-016 雙向中 long 方向 W30 正；本案 **封印 gap-down skip**（非新進場機制 · 降 collision）
- **禁止**：在同一 FT-016 改 exit 重跑 grid；**禁止** EMA/trend filter overlay（CAL-8 已放棄）

## 2. 與已死 thesis 差異（§C）

| 最接近的舊 FT | 為何不是同一個 |
|---------------|----------------|
| **FT-016 GDC** | **同進場 P0** · **不同 FT 編號** · **不同** `EXIT_VARIANT`（barrier → **trail skew**）· **long-only** |
| P-003 gap fade | **順 gap 做多** · 非 inventory fade |
| FT-009 ORB | 錨點 gap+drive+retrace · 非 OR 邊界 |
| FT-017 CFA | 盤中 compression flow · **非** 開盤 gap 結構 |

## 3. 進出規則（§D · 可程式化）

| 項目 | 定義 |
|------|------|
| 方向 | **Long-only**（`gap_pts > 0` 且 qualify；gap-down **整日 skip**） |
| 進場 | **Reuse** FT-016 §5.1 MUST-1 / MUST-1a（[`gap_drive_continuation_counterfactual.py`](../../../apps/trading-app/src/reporting/gap_drive_continuation_counterfactual.py) P0 封印） |
| 停損 | 初始 `k_sl × ATR(14)` · 觸發 BE 後抬至 entry |
| 停利 / trail | §5.0b **`atr_trail_skew_900s`** |
| 時間出場 | `max_hold_sec=900` · **10:30** 後禁新倉 |
| 日內 flatten | **是** · max **1** 筆/日 |

## 4. 頻率與 Gate 粗算（§E）

| 項目 | 估計 |
|------|------|
| train 2025 預期 n | **25–45**（G3S **≥15** · long-only ≈ FT-016 一半） |
| 預期 gross/趟 | **3–7**（trail 厚尾敘事 · **仍須** G1 gross>5） |
| 預期 net/趟 | 邊緣 — 以 CF 為準 |

### E.1 粗算錨點（FT-016 · exit-led）

| 指標 | FT-016 fp 實績 | FT-018 設計含意 |
|------|----------------|-----------------|
| W30 stop-less med | **+13** | 進場方向 **未 falsify** · fingerprint 改 **W900**（對齊 hold） |
| barrier gross/趟 | 3.29 | G1 **不過** — trail 須 ** materially** 提升 gross |
| barrier med | **−1** | 契約 PnL 負 · 路徑仍順 |
| MFE med | **~25** | BE@1× trail@2× **有** 觸發空間 |
| **`exit_gap`** | **~26** | gate_report 附錄 MUST 重算 |
| valid net | **−9.28** | skew **禁 holdout** 若 valid≤0 |

**規則**：預期 gross **不得**無根據高於 FT-016 barrier best（4.3）；若 W900 median ≤ 0 → **`gudt_fingerprint_fail_direction`**。

### E.2 機制標籤

- [x] **Continuation**
- [ ] Mean-reversion
- [ ] Liquidity / microstructure

### E.3 Thesis class（skew · MUST）

| 欄位 | pre-register |
|------|--------------|
| `payoff_ratio_min` | **2.5** |
| `tail_gross_min_pts` | **15** |
| `max_consecutive_losses` | **10** |
| `max_consecutive_loss_pts` | **150** |
| `worst_month_net_pts` | **−120** |
| `top3_win_gross_share_max` | **0.65** |
| 預期 win_rate | **30–45%**（trail 截斷 losers · 厚尾 winners） |
| `k_sl × ATR` | **≥ 1.0**（fingerprint 凍結 **1.0**） |

## 5. Pre-register（§F · 開 CF 前封印）

### 5.0 參數 grid（**僅** fingerprint **通過後** tune · 見 §5.2）

| 參數 | 值 / 範圍 | Fingerprint 凍結 |
|------|-----------|-------------------|
| `gap_k_atr` | {1.0, 1.5} | **1.0** |
| `retrace_max_frac` | {0.30, 0.40} | **0.40** |
| `drive_window_min` | **30** | 封印 |
| `k_sl` | {0.75, 1.0, 1.25} | **1.0** |
| `be_trigger_atr_k` | {0.75, 1.0} | **1.0** |
| `trail_arm_atr_k` | {1.5, 2.0} | **2.0** |
| `trail_dist_atr_k` | {0.4, 0.5, 0.6} | **0.5** |
| `hard_tp_atr_k` | {3.0, 4.0, none} | **4.0** |
| `gap_ref` / `prior_close` / `open_0845` | 同 FT-016 §5.1a | 封印 |
| `break_entry_start` | **09:45** | 封印 |
| `no_new_entry_after` | **10:30** | 封印 |
| `max_trades_per_day` | **1** | 封印 |
| `min_atr_pts` | **25.0** | 封印 |
| `atr_period` | **14** | 封印 |
| **方向** | **long-only** | 封印 |

**日期封印**：valid `2026-01-01`～`2026-03-31` · holdout `2026-04-01`～`2026-06-30` — **不得**依結果增刪參。

#### 5.0b Exit sim（0c-1 / 0c-2 共用 · 封印）

| 項目 | 值 |
|------|-----|
| 函式 | **`simulate_atr_trail_skew_exit`**（Phase 0a **新實作** · 0-design 後） |
| `EXIT_VARIANT` | **`atr_trail_skew_900s`** |
| 初始 stop | `hard_stop_atr_k` = §5.0 `k_sl` 凍結 **1.0** |
| BE | 浮盈 ≥ **`be_trigger_atr_k`×ATR** → stop 抬至 **entry**（breakeven gross） |
| Trail arm | 浮盈 ≥ **`trail_arm_atr_k`×ATR** → trailing stop = peak − **`trail_dist_atr_k`×ATR** |
| Hard TP | 若 `hard_tp_atr_k` 非 none：peak ≥ **`hard_tp_atr_k`×ATR** → 市價出場 @ TP 價 |
| Tie-break | 同 tick **stop 與 TP 同觸** → **stop 優先**（保守） |
| `max_hold_sec` | **900** |
| Entry 價 | **tick close** @ break 確認 |
| 摩擦 | **5** 點 round-trip |
| Pilot 前瞻 | tick path · BE/trail intrabar 順序 — **0c 用 tick 序列**；gate_report 附註 bar-close 落差 |

**MUST — 每 tick 狀態機（P0 · 0a 封印 · 逐 tick 升序）**

| 步驟 | 動作 |
|------|------|
| 1 | 讀 tick `close` · 更新 **peak** = max(peak, close)（long） |
| 2 | 若 peak − entry ≥ `be_trigger_atr_k×ATR` → **BE armed** · effective_stop = max(effective_stop, entry) |
| 3 | 若 peak − entry ≥ `trail_arm_atr_k×ATR` → **trail armed** · effective_stop = max(effective_stop, peak − `trail_dist_atr_k×ATR`) |
| 4 | 若 trail armed：每 tick effective_stop = max(BE stop if armed, peak − `trail_dist_atr_k×ATR`) |
| 5 | 若 peak − entry ≥ `hard_tp_atr_k×ATR`（且 hard_tp 非 none）→ **TP 觸發** @ entry + hard_tp×ATR |
| 6 | 若 close ≤ effective_stop → **stop 出場** @ effective_stop |
| 7 | 若 `entry_ts + max_hold_sec` 到達 → **時間出場** @ 當 tick close |

**同 tick 多事件 tie-break（P0）**

| 衝突 | 優先 |
|------|------|
| stop vs TP 同 tick | **stop 優先** |
| initial stop vs BE stop 同 tick | **較寬 stop（較高價）優先** — 對 long = max(initial, entry) |
| BE arm 與 trail arm 同 tick | 先 BE（步驟 2）再 trail（步驟 3）· 同 tick 可同時 armed |
| peak 更新 vs stop 檢查 | **先**更新 peak（步驟 1）**再**檢查 stop/TP（步驟 5–6） |

#### 5.0c Fingerprint window（v1.5 · MUST）

| 欄位 | 值 |
|------|-----|
| `fingerprint_window_sec` | **900** |
| Gate 讀取 | **W900** `close_delta_median`（stop-less gross · 同 [`post_entry_diagnosis.py`](../../../apps/trading-app/src/reporting/post_entry_diagnosis.py)） |
| **Primary key** | post_entry / 0c-1 gate **MUST** 以 `fingerprint_window_sec=900` 為 **primary** · **禁止**混用 W30 / W1800 作 gate |
| Legacy W1800 | **僅** post_entry 附錄 · **非** 0c-1 gate |
| 對齊 | **=** `max_hold_sec` |
| FT-016 錨點 | W30 med **+13** 為 **歷史參考** · **非** FT-018 gate KPI |

### 5.1 Phase 0 封印 MUST

#### MUST-1 — Gap · drive · retrace · break（long-only · normative · 源自 FT-016 P0）

| 項目 | 封印定義 |
|------|----------|
| **Gap 方向** | `gap_pts = open_0845 − prior_close`（§5.1a） |
| **Long-only 後置** | **先**跑 GDC entry builder（雙向 P0）· **再** filter：`gap_pts ≤ 0` 或 flat gap → **整日 skip** · **MUST NOT** 改 GDC 模組內 P0 |
| **Flat gap** | `\|gap_pts\| < 0.5` → skip |
| **Gap 門檻** | `gap_pts ≥ gap_k_atr × ATR(14)` @ **09:14 bar close**（long-only 僅 gap-up） |
| **Drive 窗** | 09:15–09:45 已收 1m bar（**含** 09:15 · **不含** 09:46 起） |
| **Drive 極值** | gap up：`drive_high = max(High)` in drive 窗 |
| **Retrace（一次性）** | **僅** 09:45 bar 收盤後判定一次 · 09:45 後再拉回 **不**恢復 |
| **Retrace 公式** | `min_low_drive ≥ open_0845 − gap_pts × retrace_max_frac` |
| **Break 進場** | retrace OK · **≥ 09:45:00** · 首 tick `close > drive_high` |
| **進場窗** | break tick **< 10:30** |
| **1 筆/日** | 首個合格 break → entry |

#### MUST-1a — `prior_close` · `open_0845`（P0 · normative · FT-016 2026-06-28 封印）

| 項目 | 封印定義 |
|------|----------|
| **Session 日** | 當日可交易 1m kbars `08:45`–`13:45` |
| **`prior_session_date`** | 當日 D 在 `tick_cache` 中 **前一個有 kbar 檔** 的交易日 |
| **`prior_close`** | `prior_session_date` session 內 **時間序最後一根已收** 1m bar 的 **Close** |
| **缺 prior kbar** | `resolve_kbar_path(prior_session_date)` 為 None → **整日 skip**（**無** fallback） |
| **`open_0845`** | 當日 **第一根** `ts.time == 08:45` 且 **已收盤** 的 1m bar 之 **Open** |
| **缺 08:45 bar** | 整日 skip |
| **ATR 錨** | ATR(14) @ **09:14 bar close** · `min_atr_pts=25` |

#### MUST-1b — Entry reuse 邊界（P0 · 0-design 2026-06-29 封印）

| 項目 | 封印定義 |
|------|----------|
| **Builder** | Phase 0a **MUST** 呼叫 [`gap_drive_continuation_counterfactual.py`](../../../apps/trading-app/src/reporting/gap_drive_continuation_counterfactual.py) 同款 entry 邏輯 |
| **P0 不可變** | **MUST NOT** 修改 GDC 模組內 gap/drive/retrace/break 定義 |
| **Long-only** | **後置 filter** on GDC candidate entries · 非 GDC 內建方向分支 |
| **Bit-identical 驗收** | fp 參 `gk1_rt0p4` · GDC long entries 集合 **=** GUDT entries 集合（同一 cache · 同一日期範圍）· PLAN case 10 → 0a 必測 |
| **Exit** | 僅 GUDT CF 替換 `simulate_atr_trail_skew_exit` · entry ts/price **不變** |

#### MUST-2 — 摩擦 · ATR · 執行診斷

- 主判摩擦 **5** 點 round-trip · `atr_effective = max(atr, min_atr_pts)`
- Entry = **tick close** @ break
- **P1 診斷（非 gate）**：`entry_slippage_sensitivity_pts ∈ {0,1,2}` · `pct_mfe_ge_1atr` · **`exit_gap`**

#### MUST-3 — Funnel 五階（同 FT-016 · long-only funnel）

`days_with_session` → `gap_qualify_up` → `retrace_ok` → `break_signal` → `entry`

#### MUST-4 — post_entry · skew 附錄 hook

- CF JSON **MUST** 含 `post_entry_diagnosis_by_param`（**W900** primary · W1800 附錄）· `skew_gate_by_param`
- `gate_report` **MUST**：`exit_gap` · `pct_mfe_ge_1atr` · friction@7 · G-SK5

### 5.2 Phase 0 診斷順序（fingerprint 先於 grid）

| 步驟 | 通過線 |
|------|--------|
| **0c-1 Fingerprint** | **W900** stop-less gross **median > 0** · **n ≥ 15**（G3S） |
| **0c-1b direction** | W900 ≤ 0 · n≥15 → **`gudt_fingerprint_fail_direction`** · **不跑 grid** |
| **0c-1b n** | W900 > 0 · n<15 → **`gudt_fingerprint_fail_n`** · **不跑 grid** |
| **0c-2 Grid** | G1–G2 · G3S · §3.2 skew gate |

| Scenario | Outcome |
|----------|---------|
| W900 ≤ 0 · n≥15 | `gudt_fingerprint_fail_direction` |
| W900 > 0 · n<15 | `gudt_fingerprint_fail_n` |
| W900 > 0 · n≥15 · grid fail | `gudt_fingerprint_pass_g1_fail` / `gudt_no_skew_champion` |
| train 過 · valid net≤0 | `gudt_overfit_suspect` · **禁 holdout** |

### 5.3 Post-entry 診斷（非 gate）

- 模組：[`post_entry_diagnosis.py`](../../../apps/trading-app/src/reporting/post_entry_diagnosis.py)
- **禁止**依 post_entry 回頭 tune train grid 或改 `fingerprint_window_sec`

### 5.4 Outcome codes

| Code | 條件 |
|------|------|
| `gudt_fingerprint_fail_direction` | 0c-1 W900 median ≤ 0 · n≥15 |
| `gudt_fingerprint_fail_n` | W900 > 0 · n<15 |
| `gudt_fingerprint_pass_g1_fail` | fingerprint 過 · grid G1/G2 不過 |
| `gudt_no_skew_champion` | grid 過 · §3.2 disqualify |
| `gudt_overfit_suspect` | train 過 · valid net ≤ 0 |
| `gudt_train_no_go` | 其他 |

## 6. Falsify（§G）

- W900 median ≤ 0 且 n≥15 → **`gudt_fingerprint_fail_direction`**（進場 thesis 錯 · **非** 再調 exit）
- W900 > 0 · grid G1 fail · **`exit_gap`** 仍大 → MVPClosed · **禁止** 第三種 exit 變形
- **禁止** gap-down short · fade · EMA overlay

## 7. 人類簽核（§H）

| 欄位 | 值 |
|------|-----|
| 簽核人 | |
| 日期 | |
| 決策 | **pending**（`draft-proposal` · 待 FT-017 0c 後 Pick） |

## 8. 設計審閱（Phase 0-design · 非 Pilot Go）

| 欄位 | 值 |
|------|-----|
| 審閱 | 資深 TXF 交易人員 |
| 日期 | 2026-06-29 |
| 審閱檔案 | 本 SPEC · [`PLAN.md`](PLAN.md) |
| 結論 | **Conditional PASS — Revise（P0 已併入 SPEC）** — 准 **Phase 0a 準備** · **0c train 待** P-011 `human-approved` + FT-017 0c-1 後 Pick |
| Phase 0a prompt | [`PLAN.md`](PLAN.md) §「給 Agent 的 Phase 0a 開工 prompt」 |

### 審閱摘要

- **Exit-led 框架**：PASS — 新 FT-018、reuse entry、新 `atr_trail_skew_900s`；非 FT-016 復活。
- **Trail 參數（BE1 / trail2@0.5 / TP4 / k_sl1.0 / hold900）**：交易上可接受；gap-up 上午 trail dist 0.5 偏緊，依 tick path 驗證。
- **Long-only**：有助 thesis 純度與降 collision；n≈25–45 緊貼 G3S 15，skew 附錄解讀需保守。
- **W900 fingerprint**：與 max_hold_sec=900 對齊正確；W30 +13 僅為 FT-016 歷史錨點，不作 FT-018 gate。
- **Skew + G1 gross>5**：張力已揭露；fingerprint 先於 grid 順序正確。
- **Collision**：與 FT-017 機制/時段低重疊；與 P-003 fade 反向隔離。

### P0（0a 前 — 已写入 SPEC §5.0b / §5.0c / §5.1）

1. `prior_close` / `gap_ref` / `open_0845` — §5.1a inline
2. Trail intrabar 狀態機 + tie-break — §5.0b
3. Entry reuse 邊界 + bit-identical — §5.1b
4. W900 primary gate — §5.0c

### P1（0b 前）

1. `entry_slippage_sensitivity_pts ∈ {0,1,2}` 診斷
2. `exit_gap` · `pct_mfe_ge_1atr` gate_report 附錄
3. friction@7 對照

### Pick P-011 建議

- **0-design**：P0 封印後可視為 **PASS（條件式）**。
- **human Pick / 0c train**：**等 FT-017 0c-1 fingerprint 結案**（建議）。

## 9. CF code review（§I · Phase 0b · train 前必填）

| 欄位 | 值 |
|------|-----|
| Review 日期 | |
| 結果 | pending |
