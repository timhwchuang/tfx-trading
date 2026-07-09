---
id: FT-016
slug: gap-drive-continuation
status: MVPClosed
thesis_class: skew
proposal_id: P-005
opened: 2026-06-28
closed: 2026-06-28
outcome: gdc_fingerprint_pass_g1_fail
owner: Tim (human-approved 2026-06-28)
target: Alpha Phase 0
holdout_contract: v2.2.1
design_review: senior-trader 2026-06-28 — PASS (P0 sealed)
---

# FT-016 — Gap Drive Continuation（SPEC）

> **結案**：[`gate_report.md`](../../../workspaces/gdc-baseline/gate_report.md) · **`gdc_fingerprint_pass_g1_fail`** · fingerprint W30 med **+13** · grid G1 全敗 · valid net **−9.28**

## 1. Summary（THESIS_BRIEF §A–B）

**一句話**：開盤 **gap > k×ATR** 後，09:15–09:45 drive 段 **回撤 < gap×40%**，09:45 後 **破 drive 極值** → **順 gap 方向**進場；Phase 0 **雙向**；每日 **1 筆**。

**錯價因果**

- **誰在錯**：gap 後過早 fade / 逆 gap 押 mean-reversion，忽略 **drive 確認後** 的延續
- **何時**：09:15–10:30（break 進場窗）
- **機制**：**continuation**（gap 方向 drive + shallow retrace + breakout）

**Edge 經濟學（設計審閱 · 封印認知）**

- 粗算 gross **2–5** — 與 FT-009 ORB 同族 **breakout 天花板**；skew 允 median 難看，但 **G1 gross>5 仍 MUST**。
- **不是** P-003 fade — 進場 **順 gap**，非 inventory 回 prior close。
- FT-015 屍體：結構 retest n 大但 W30≈0 — 本案 **gap 錨點** 不同，仍須 fingerprint 方向指紋。

## 2. 與已死 thesis 差異（§C）

| 最接近的舊 FT | 為何不是同一個 |
|---------------|----------------|
| P-003 gap fade | **順 gap** continuation；等 drive + shallow retrace + break |
| FT-009 ORB | 錨點 **gap 大小 + 回撤深度**，非固定 R 分鐘 range 邊界 |
| FT-008 short breakout | 非 rolling N-bar；**session gap** 驅動 |
| FT-013 / P-004 | 非 ST / VWAP；**開盤結構 gap** |

## 3. 進出規則（§D · 可程式化）

| 項目 | 定義 |
|------|------|
| 方向 | **Long**（gap up）· **Short**（gap down）· 雙向 |
| 進場 | §5.1 MUST-1：gap qualify → drive 段 retrace OK → tick **破 drive_high/low** |
| 停損 | `k_sl × ATR(14)` |
| 停利 | Phase 0 **僅** `simulate_atr_barrier_exit`（§5.0b） |
| 時間出場 | `max_hold_sec=900` · **10:30** 後禁新倉 |
| 日內 flatten | **是** · max **1** 筆/日 |

## 4. 頻率與 Gate 粗算（§E）

| 項目 | 估計 |
|------|------|
| train 2025 預期 n | **40–80**（G3S **≥15**） |
| 預期 gross/趟 | **2–5**（保守 · breakout 族） |
| 預期 net/趟 | 邊緣 — 以 CF 為準 |

### E.1 粗算錨點

| 最接近同族 | 實績 / 錨點 |
|------------|-------------|
| **FT-009 ORB** | 2025 train **全 param net 負** · legacy 01–04 曾正但 holdout 掛 |
| FT-013 continuation | W30 med **−10**（long ST） |
| FT-015 skew | n=211 但 W30 **−0**（結構 retest 無 edge） |

**規則**：預期 gross **不得**假設優於 FT-009 legacy；若 fingerprint W30≤0 → 即 MVPClosed。

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
| 預期 win_rate | **35–45%**（厚尾敘事） |
| `k_sl × ATR` | **≥ 0.75**（fingerprint **1.0**） |

## 5. Pre-register（§F · 開 CF 前封印）

### 5.0 參數 grid（**僅** fingerprint **通過後** tune · 見 §5.2）

| 參數 | 值 / 範圍 | Fingerprint 凍結 |
|------|-----------|-------------------|
| `gap_k_atr` | {1.0, 1.5} | **1.0** |
| `retrace_max_frac` | {0.30, 0.40} | **0.40** |
| `drive_window_min` | **30**（1m 根 · 09:15 起） | 封印 |
| `k_sl` | {0.75, 1.0, 1.25} | **1.0** |
| `tp_atr_k` | {1.5, 2.0, 2.5} | **2.0** |
| `gap_ref` | **08:45** 第一根 1m **Open** vs **prior session close** | 封印 |
| `prior_close` | 前一交易日 session **最後一根已收** 1m **Close** | 封印 |
| `break_entry_start` | **09:45**（drive 窗結束後） | 封印 |
| `no_new_entry_after` | **10:30** | 封印 |
| `max_trades_per_day` | **1** | 封印 |
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
| `max_hold_sec` | **900** |
| Entry 價 | **tick close** @ break 確認 |
| 摩擦 | **5** 點 round-trip |
| Pilot 前瞻 | tick vs bar close — **0c 不模擬**；gate_report 附註 |

### 5.1 Phase 0 封印 MUST

#### MUST-1 — Gap · drive · retrace · break（無 lookahead）

| 項目 | 封印定義 |
|------|----------|
| **Gap 方向** | `gap_pts = open_0845 − prior_close`（見 §5.1a） |
| **Flat gap** | `\|gap_pts\| < 0.5` → **整日 skip**（無 long/short 硬分） |
| **Gap 門檻** | `\|gap_pts\| ≥ gap_k_atr × ATR(14)` @ **09:14 bar close** · **≥** 含等號 |
| **Drive 窗** | 09:15–09:45 已收 1m bar（**含** 09:15 · **不含** 09:46 起） |
| **Drive 極值** | 僅在 drive 窗內：gap up → `drive_high = max(High)`；gap down → `drive_low = min(Low)` |
| **Retrace（一次性）** | **僅** drive 窗結束（09:45 bar 收盤後）以窗內 `min(Low)` / `max(High)` **判定一次**；**不**事後更新 · 09:45 後再拉回 **不**恢復資格 |
| **Retrace 公式** | gap up：`min_low_drive ≥ open_0845 − \|gap_pts\| × retrace_max_frac`；gap down 對稱 |
| **Retrace 白話例** | gap up **100 點** · `retrace_max_frac=0.40` → drive 窗 `min(Low) ≥ open_0845 − 40` |
| **Break 進場** | retrace **OK** 後 · **≥ 09:45:00** · gap up 首 tick `close > drive_high`；gap down 首 tick `close < drive_low` |
| **進場窗** | break tick 時間 **< 10:30** |
| **1 筆/日** | 首個合格 break → entry；`break_signal` 可計、進場窗外 **不** entry |

#### MUST-1a — `prior_close` · `open_0845`（P0 · 資深 TXF 2026-06-28 封印）

| 項目 | 封印定義 |
|------|----------|
| **Session 日** | 與 ORB/VSF 同族：當日可交易 1m kbars `08:45`–`13:45` |
| **`prior_session_date`** | 當日 D 在 `tick_cache` 中 **前一個有 kbar 檔** 的交易日（非 calendar 週末跳躍外推） |
| **`prior_close`** | `prior_session_date` 當日 session 內 **時間序最後一根已收** 1m bar 的 **Close**（通常 ≈ 13:44 bar → close@13:45；**含**日盤結算前最後成交 kbar，**不**另取 R1/R2 結算參考價） |
| **缺 prior kbar** | `resolve_kbar_path(prior_session_date)` 為 None → **整日 skip**（**無** fallback · **無**插值） |
| **`open_0845`** | 當日 **第一根** `ts.time == 08:45` 且 **已收盤** 的 1m bar 之 **Open** |
| **缺 08:45 bar** | 當日 session 無完整 08:45 桶 → **整日 skip** |
| **ATR 錨** | ATR(14) @ **09:14 bar close**（SMA TR · `atr_series_from_bars` · `min_atr_pts=25`） |

#### MUST-2 — 摩擦 · ATR · 執行診斷

- 主判摩擦 **5** 點 round-trip · `atr_effective = max(atr, min_atr_pts)`
- Entry = **tick close** @ break（**無** FT-013 entry+1）
- **P1 診斷（非 gate）**：JSON 附錄 `entry_slippage_sensitivity_pts ∈ {0,1,2}` 對 gross/net 敏感度；主判仍 friction=5
- `gate_report` **MUST** 預留 `execution_margin_thin` 註記（大 gap break 追價 · Pilot IOC ±3 未在 0c 模擬）

#### MUST-3 — Funnel 五階（絕對數 · `break_signal` ≠ `entry`）

`days_with_session` → `gap_qualify` → `retrace_ok` → `break_signal` → `entry`

| 階段 | 定義 |
|------|------|
| `break_signal` | retrace OK 後，09:45–10:30 內出現 tick break `drive_high/low` |
| `entry` | `break_signal` 且 break 時間 **< 10:30** 且完成 barrier sim |

#### MUST-4 — post_entry · skew 附錄 hook（非 gate）

- CF JSON **MUST** 含 `post_entry_diagnosis_by_param` · `skew_gate_by_param`
- `gate_report` skew 附錄 **MUST**：win_rate · payoff_ratio · tail_count · **friction@7** · **top3_win_gross_share**（[`HOLDOUT_CONTRACT_v2.md`](../ai-backtest-tuning/HOLDOUT_CONTRACT_v2.md) §3.2）

### 5.2 Phase 0 診斷順序（fingerprint 先於 grid）

| 步驟 | 通過線 |
|------|--------|
| **0c-1 Fingerprint** | W30 stop-less gross **median > 0** · **n ≥ 15**（G3S） |
| **0c-1b** | W30 ≤ 0 → **`gdc_fingerprint_fail`** · **不跑 grid** |
| **0c-2 Grid** | G1–G2 · G3S · §3.2 skew gate |

| Scenario | Outcome |
|----------|---------|
| W30 ≤ 0 · n≥15 | `gdc_fingerprint_fail` |
| W30 > 0 · grid fail | `gdc_fingerprint_pass_g1_fail` / `gdc_no_skew_champion` |
| train 過 · valid net≤0 | `gdc_overfit_suspect` · **禁 holdout 封印**（[`HOLDOUT_CONTRACT_v2.md`](../ai-backtest-tuning/HOLDOUT_CONTRACT_v2.md) **v2.2.1 §4** skew 硬擋 · gate_report 標 `holdout_blocked_overfit`） |

- `gate_report.md` **MUST** 分節：`## Fingerprint (0c-1)` · `## Grid (0c-2)` · `## Valid 2026 Q1` · **§3.2 skew 附錄**（含 **friction@7** · G-SK5）

### 5.3 Post-entry 診斷（FT-012+ MUST · 非 gate）

- 模組：[`post_entry_diagnosis.py`](../../../apps/trading-app/src/reporting/post_entry_diagnosis.py)
- **禁止**依 post_entry 回頭 tune train grid

### 5.4 Outcome codes

| Code | 條件 |
|------|------|
| `gdc_fingerprint_fail` | 0c-1 W30 median ≤ 0 或 n<15 |
| `gdc_fingerprint_pass_g1_fail` | fingerprint 過 · grid G1/G2 不過 |
| `gdc_no_skew_champion` | grid 過 · §3.2 disqualify |
| `gdc_overfit_suspect` | train 過 · valid 2026 Q1 net ≤ 0 · **不得 holdout** |
| `gdc_train_no_go` | 其他 |

## 6. Falsify（§G）

- fingerprint W30 median ≤ 0 且 n≥15 → **`gdc_fingerprint_fail`**
- funnel `gap_qualify → entry` < 5% 且 gap_qualify ≥ 20 → gate_report 註記（非自動 MVPClosed）
- **禁止**因 FT-009 失敗改為 fade（P-003 路徑）

## 7. 人類簽核（§H）

| 欄位 | 值 |
|------|-----|
| 簽核人 | Tim |
| 日期 | 2026-06-28 |
| 決策 | **approved**（Pick **P-005** → FT-016） |

## 8. 設計審閱（Phase 0-design · 非 Pilot Go）

| 欄位 | 值 |
|------|-----|
| 審閱 | 資深 TXF 交易人員 |
| 日期 | 2026-06-28 |
| 結論 | **PASS（P0 封印後）** — 准 **Phase 0a** CF |
| 初審 | **Conditional PASS — Revise**（P0 四項未封印前不标 PASS） |
| P0 已封印 | `prior_close` 缺日 skip · `open_0845` 第一根已收 · retrace 一次性 · flat gap skip · skew valid 硬擋 |
| P1（0b 前） | entry slippage {0,1,2} 診斷 · gate_report friction@7 / G-SK5 |
| 預期 0c | ~60–70% `gdc_fingerprint_fail`（FT-009 同族先驗）— 可接受驗屍成本 |

## 9. CF code review（§I · Phase 0b · train 前必填）

| 欄位 | 值 |
|------|-----|
| Review 日期 | 2026-06-28 |
| 結果 | **PASS**（agent · gate_report §0b） |
