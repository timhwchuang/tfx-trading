---
id: FT-014
slug: morning-vwap-hold-pullback
status: MVPClosed
closed: 2026-06-28
outcome: mvhp_fingerprint_fail
thesis_class: mean_robust
proposal_id: P-004
opened: 2026-06-28
owner: Tim (human-approved 2026-06-28)
target: Alpha Phase 0
holdout_contract: v2.2.1
design_review: senior-trader 2026-06-28 — Phase 0a GO（P0/P1 已補）
---

# FT-014 — Morning VWAP Hold Pullback Long（SPEC）

> **Proposal**：[`P-004`](../../../workspaces/THESIS_QUEUE.md) · **Gate**：[`HOLDOUT_CONTRACT_v2.md`](../ai-backtest-tuning/HOLDOUT_CONTRACT_v2.md) v2.2.1 · **`thesis_class: mean_robust`**

## 1. Summary（THESIS_BRIEF §A–B）

**一句話**：09:15–10:30，開盤 drive 後價格 **持續在 session VWAP 上方** ≥ `hold_min_bars` 根 1m，**第一次**回踩 VWAP（± buffer）且 1m **量縮** → **做多**順勢延續；Phase 0 **long-only**；**每日 first touch only**。

**錯價因果**

- **誰在錯**：過度追價後短線獲利了結，把「開盤 drive 後第一次 VWAP 支撐」誤當反轉
- **何時**：09:15–10:30（交易所時間）
- **機制**：**continuation**（順勢回踩買入；**非** |z| fade、**非** armed spike）

**Edge 經濟學（設計審閱 · 封印認知）**

- 預期 gross **3–6** 與 G1 **> 5** 之間 **幾乎無 buffer** — fingerprint 過、grid G1 仍 fail 為 **合理預期**（ORB / FT-013 同族）。
- FT-003 timeout W180 **+35** 為 **未成交路徑** — **不得**外推為本案 fill 後 edge；僅作「順勢子集存在」的弱錨點。

## 2. 與已死 thesis 差異（§C）

| 最接近的舊 FT | 為何不是同一個 |
|---------------|----------------|
| FT-006 / FT-012 | 進場是 **VWAP 上方 hold 後回踩做多**；非 z-score **反向** fade |
| FT-003 v1 hybrid | **無** `momentum_armed` / vol_1s spike；不等 armed 回踩相位 |
| FT-010 VTP | **無** stretch-to-buffer（`stretch_k×ATR` 背離）；觸發是 **第一次觸 VWAP**，非 stretch_high 後 recency |
| FT-005 timeout | 進場錨點是 **VWAP touch + 量縮**，非 timeout 180s tick |
| FT-013 ST flip | 錨點 **session VWAP**，非 SuperTrend band flip |

## 3. 進出規則（§D · 可程式化）

| 項目 | 定義 |
|------|------|
| 方向 | Phase 0 **Long-only** |
| 進場 | §5.1 MUST-1：hold 段 + first VWAP touch + vol shrink @ **1m bar close** |
| 停損 | `k_sl × ATR(14)`（k ∈ pre-register） |
| 停利 | Phase 0 **僅** `simulate_atr_barrier_exit`（§5.0b） |
| 時間出場 | `max_hold_sec=900` barrier；10:30 後 **禁新倉** |
| 日內 flatten | **是**（持倉依 exit sim；不隔夜） |

## 4. 頻率與 Gate 粗算（§E）

| 項目 | 估計 |
|------|------|
| train 2025 預期 n | **60–120**（G3 n≥30） |
| 預期 gross/趟 | **3–6**（須 mean **> 5** 過 G1 — **下緣直接死在 G1 前**） |
| 預期 net/趟（扣 5 點） | 邊緣 — 以 CF 為準 |

### E.1 粗算錨點

| 最接近同族 | 實績 / 錨點 |
|------------|-------------|
| FT-003 timeout 子集 | W180 close_delta **+35**（順勢、**未成交** — 弱錨點 only） |
| **FT-010 VTP** 01–03 | **n=1–3**/param · best gross mean **18.95**（n=3）· **G1/G3 未過** · [`vtp-baseline`](../../../workspaces/vtp-baseline/gate_report.md) |
| FT-013 ST flip | train 2025 W30 med **−10**（n=67）— 早盤 ST 順勢 long 方向錯 |

**規則**：本案預期 gross **不得**假設優於 timeout 子集外推；若 CF n<30 → 觸發太稀，**禁** tune 時段 / 放寬 hold 救 n。

### E.2 機制標籤

- [x] **Continuation**
- [ ] Mean-reversion
- [ ] Liquidity / microstructure

### E.3 Thesis class

- [x] **`mean_robust`**
- [ ] `skew`（**禁止** CF 後事後改 class 救場）

## 5. Pre-register（§F · 開 CF 前封印）

### 5.0 參數 grid（**僅** fingerprint **通過後** tune · 見 §5.2）

| 參數 | 值 / 範圍 | Fingerprint 凍結 |
|------|-----------|------------------|
| `hold_min_bars` | {5, 10, 15}（1m 根） | **10** |
| `touch_buf_k` | {0.05, 0.10, 0.15} × ATR | **0.10** |
| `pullback_vol_ratio_max` | {0.70, 0.85} | **0.85** |
| `vwap_slope_bars` | {2, 3}（strict 遞增根數） | **3** |
| `k_sl` | {0.75, 1.0, 1.25} | **1.0** |
| `tp_atr_k` | {1.5, 2.0, 2.5} | **2.0** |
| session entry | **09:15–10:30** | 封印 |
| `no_new_entry_after` | **10:30** | 封印 |
| `max_trades_per_day` | **1**（first touch only） | 封印 |
| `min_atr_pts` | **25.0** | 封印 |
| `atr_period` | **14**（SMA TR · ORB 同族） | 封印 |

**日期封印**：valid `2026-01-01`～`2026-03-31` · holdout `2026-04-01`～`2026-06-30` — **不得**依結果增刪參。

#### 5.0b Exit sim（0c-1 / 0c-2 共用 · 封印）

| 項目 | 值 |
|------|-----|
| 函式 | [`simulate_atr_barrier_exit`](../../../apps/trading-app/src/reporting/armed_forward_counterfactual.py) |
| `EXIT_VARIANT` | **`atr_barrier_900s`** |
| `hard_stop_atr_k` | = §5.0 `k_sl` 凍結 **1.0** |
| `tp_atr_k` | **2.0** |
| `max_hold_sec` | **900**（15m — **對齊早盤 continuation 敘事**；最晚 10:30 進場 → 約 10:45 前 horizon；**非** VTP 1200s） |
| Entry 價 | bar **close**（ORB/VSF 同族；**不加** FT-013 entry+1） |
| 摩擦 | **5** 點 round-trip |
| Pilot 前瞻 | bar close vs IOC ±3 讓價 — **0c 不模擬**；gate_report 附註執行 margin |

### 5.1 Phase 0 封印 MUST

#### MUST-1 — Hold 段 · first touch · 無 lookahead

| 項目 | 封印定義 |
|------|----------|
| VWAP | **Session 累積** VWAP @ 每根 1m close（與 VTP CF `_session_vwap_series` 同語意） |
| **Hold 段** | 連續 **`hold_min_bars`** 根已收 1m：`close > session_vwap` **且** 當根及前 **`vwap_slope_bars−1`** 根 session VWAP **嚴格遞增**（hold 與 slope **同時**成立） |
| **Drive 起點** | **09:15 後**第一根可計入 hold 的 bar；09:15 前 bar **不**觸發 |
| **First touch** | hold 段成立後，**第一根**滿足 `low <= session_vwap + touch_buf_k × ATR` **且** `close >= session_vwap − touch_buf_k × ATR` |
| **Touch 解讀** | wick 可穿 VWAP+buffer、close 仍在 VWAP−buffer 上方 — **允許**；deep wick + 弱 close 在 live 常為 failed auction → Phase **0b** 對照 tick replay 語意（[`trading-app/SPEC.md`](../../../apps/trading-app/SPEC.md) §9） |
| **量縮** | touch bar `volume <= median(volume[hold 段]) × pullback_vol_ratio_max`（**已知偏鬆** — grid 含 0.70；fingerprint 0.85 封印，**禁止**事後放寬救場） |
| **進場** | 上述同 **1m bar close**；`entry_ts` = bar close ts |
| **禁止** | partial bar；hold 未完成即 touch；第二 touch 補進 |

#### MUST-2 — 摩擦

| 項目 | 封印 |
|------|------|
| 摩擦 | **5** 點/趟；`net = gross − 5` |
| gate_report | **MUST** 註明 raw close entry（ORB/VSF 同族） |

#### MUST-3 — 頻率 · funnel

| 項目 | 封印 |
|------|------|
| 方向 | **Long-only** |
| 頻率 | **max 1** entry / day |
| 10:30 窗 | `entry bar close time >= 10:30` → 不 arm |
| Funnel | `days_with_session` → `hold_pass` → `first_touch` → `vol_shrink` → `entry` |
| gate_report | **MUST** 報 funnel **絕對數** + 轉化率（避免僅百分比誤導） |

### 5.2 Phase 0 診斷順序（Playbook · 先 fingerprint 後 grid）

| 步驟 | 動作 | 通過線 |
|------|------|--------|
| **0c-1 Fingerprint** | 凍結 §5.0；2025 train；**funnel + post_entry** | W30 stop-less gross **median > 0** · n≥30 |
| **0c-1b** | W30 ≤ 0 | **MVPClosed** `mvhp_fingerprint_fail` — **不**跑 grid |
| **0c-2 Grid** | 僅 fingerprint 過 | G1–G3 · §3.1 · valid 對照 |

**預期路徑（G1 結構性張力 · MUST NOT 滑坡）**

| Scenario | 結果 | Outcome code |
|----------|------|----------------|
| **A** W30 ≤ 0, n≥30 | MVPClosed | `mvhp_fingerprint_fail` |
| **B** W30 > 0, grid G1/G2 不過 | MVPClosed | `mvhp_fingerprint_pass_g1_fail` |
| **C** train 過, valid net ≤ 0 | overfit_suspect | `mvhp_overfit_suspect`（**禁** holdout 主判） |
| **D** train + valid 對照可接受 | 人類 Go Phase 1 | — |

- **禁止**：0c-1 未過跑 grid；W30 正而改 exit / 拉窗 / 放寬 hold；gross 目標下修仍硬 tune。
- `gate_report.md` **MUST** 分節：`## Fingerprint (0c-1)` · `## Grid (0c-2)` · `## Valid 2026 Q1（參考）` · `## §3.1 disqualify（Long）`

### 5.3 Post-entry 診斷（FT-012+ MUST · 非 gate）

- 模組：[`post_entry_diagnosis.py`](../../../apps/trading-app/src/reporting/post_entry_diagnosis.py)
- CF JSON **MUST** 含 `post_entry_diagnosis_by_param`
- `gate_report` 附錄：W5/W15/W30 stop-less + MFE/MAE + `interpret_post_entry` verdict
- **用途**：區分 **direction_failed** vs **exit_kills_edge**（fingerprint W30 正但 barrier 負）
- **禁止**依 post_entry 回頭 tune train grid

### 5.4 Outcome codes（MVPClosed / 參考）

| Code | 條件 |
|------|------|
| `mvhp_fingerprint_fail` | 0c-1 W30 median ≤ 0（或 n<30） |
| `mvhp_fingerprint_pass_g1_fail` | fingerprint 過 · grid G1/G2/§3.1 不過 |
| `mvhp_overfit_suspect` | train 過 · valid 2026 Q1 net ≤ 0 |
| `mvhp_no_robust_champion` | grid 無 §3.1 合格冠軍 |
| `mvhp_train_no_go` | 其他 train gate 未過（綜合） |

## 6. Falsify（§G）

- train fingerprint W30 median ≤ 0 且 n≥30 → **`mvhp_fingerprint_fail`** · MVPClosed
- fingerprint 過、grid train net ≤ 0 / G1 不過 → **`mvhp_fingerprint_pass_g1_fail`** 或 `mvhp_train_no_go`
- train 過、valid net ≤ 0 → **`mvhp_overfit_suspect`**
- funnel `hold_pass → entry` 轉化 < 10% **且** `hold_pass` 絕對數 ≥ 20 → 結構不匹配（gate_report 註記；**非**自動 MVPClosed）
- **禁止**因 FT-013 失敗放寬 `hold_min_bars` 或拉窗至 12:00 救 n

## 7. 人類簽核（§H）

| 欄位 | 值 |
|------|-----|
| 簽核人 | Tim |
| 日期 | 2026-06-28 |
| 決策 | **approved**（Pick **A** · P-004 → FT-014） |

## 8. 設計審閱（資深 TXF · Phase 0 · 非 Pilot Go）

| 欄位 | 值 |
|------|-----|
| 審閱 | 資深 TXF 交易人員 |
| 日期 | 2026-06-28 |
| 結論 | **批准 Phase 0a CF**；P0 post_entry / outcome codes / valid 產物已入 SPEC/PLAN |
| 備註 | gross 3–6 vs G1>5 張力 acknowledged；`max_hold_sec` 封印 **900s**（非 VTP 1200s） |

## 9. CF code review（§I · Phase 0b · train 前必填）

| 欄位 | 值 |
|------|-----|
| Review 方式 | Bugbot / 人類 |
| Review 日期 | 2026-06-28 |
| 審查檔案 | `reporting/morning_vwap_hold_pullback_counterfactual.py` · tests |
| 結果 | **PASS**（見 [`gate_report.md`](../../../workspaces/mvhp-baseline/gate_report.md) §0b） |
| 備註 | 0c-1 n=7 · W30 med +38 · vol_shrink 過稀 → `mvhp_fingerprint_fail` |
