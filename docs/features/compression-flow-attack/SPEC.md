---
id: FT-017
slug: compression-flow-attack
status: MVPClosed
closed: 2026-06-28
outcome: cfa_fingerprint_fail
thesis_class: skew
proposal_id: P-010
opened: 2026-06-28
owner: Tim (draft-proposal 2026-06-28)
target: Alpha Phase 0
holdout_contract: v2.2.1
design_review: senior-trader 2026-06-28 — PASS (P0 sealed)
---

# FT-017 — Compression Flow Attack（SPEC）

> **Proposal**：[`P-010`](../../../workspaces/THESIS_QUEUE.md) · **Gate**：[`HOLDOUT_CONTRACT_v2.md`](../ai-backtest-tuning/HOLDOUT_CONTRACT_v2.md) v2.2.1 · **`thesis_class: skew`**

## 1. Summary（THESIS_BRIEF §A–B）

**一句話**：**10:00–12:30**，過去 **30m** 1m 區間振幅 **< compress_k×ATR** 且 ATR 處於日內偏低、tick **安靜**（60s `vol_1s` mean ≤ session p50）後，若 **60s attack 窗**內 **買/賣量比 + 量能** 失衡 → **順失衡方向 tick 追價**；停損 = `max(結構距離, min_stop_atr_k×ATR)` 且 **≥ min_stop_pts**；Phase 0 **雙向** · 每日 **1 筆**。

**錯價因果**

- **誰在錯**：死魚盤流動性薄，逆勢方與觀望者低估主動單推動價格的能力
- **何時**：10:00–12:30（交易所時間；與 FT-016 gap 窗 **不重疊**）
- **機制**：**liquidity / microstructure** — compression release 後 **順 flow 追價**（**非**回踩、**非** fade）

**Edge 經濟學（設計審閱 · 封印認知）**

- 粗算 gross **3–6** — compression / breakout 族與 FT-009、P-008 同 **G1 張力**；skew 允 median 難看，**G1 gross>5 仍 MUST**。
- **不是** FT-003：高 vol_1s spike（≥150 · 全樣本 **0.3%**）— 本案 **低波壓縮** 後攻擊（[`VOLATILITY_BASELINE.md`](../../../workspaces/VOLATILITY_BASELINE.md) §B.1）。
- **禁止** `exhaustion_vol≤15` 作死魚門檻 — baseline 覆蓋 **85.7%** 秒數，過寬。

## 2. 與已死 thesis 差異（§C）

| 最接近的舊 FT | 為何不是同一個 |
|---------------|----------------|
| FT-003 v1 hybrid | **高** vol armed + VWAP 回踩；本案 **低 ATR 壓縮** + flow chase |
| FT-007 flow flip | **fade** 脈衝吸收；本案 **順** imbalance 追價 |
| FT-015 FVG retest | **結構 zone 回踩**；本案 **無** FVG/BOS 進場 |
| FT-014 / FT-010 | VWAP hold / stretch 回踩；本案 **compression + tick flow** |
| P-008 squeeze | 僅波動壓縮、**無** buy/sell ratio 確認 |
| FT-016 gap drive | **開盤 gap** 結構；本案 **盤中死魚** + microstructure |

## 3. 進出規則（§D · 可程式化）

| 項目 | 定義 |
|------|------|
| 方向 | **Long + Short**（順 attack 失衡方向） |
| 進場 | §5.1 MUST-2/3：compress + regime + quiet → attack → **首 tick close** 追價 |
| 停損 | `stop_dist = max(結構距離, min_stop_atr_k×ATR)`；`stop_dist < min_stop_pts` → 不 arm |
| 停利 | Phase 0 **僅** `simulate_atr_barrier_exit`（§5.0b） |
| 時間出場 | `max_hold_sec=900` · **12:30** 後禁新倉 |
| 日內 flatten | **是** · max **1** 筆/日 |

## 4. 頻率與 Gate 粗算（§E）

| 項目 | 估計 |
|------|------|
| train 2025 預期 n | **20–60**（G3S **≥15**） |
| 預期 gross/趟 | **3–6**（保守 · breakout/compression 族） |
| 預期 net/趟 | 邊緣 — 以 CF 為準 |

### E.1 粗算錨點（VOLATILITY_BASELINE · Apr valid）

| 指標 | 值 | 設計含意 |
|------|-----|----------|
| ATR(20) p50 | **25.6** | `compress_k=0.45` → 30m range **< ~12pt** |
| 1m range p50 | **25** | 死魚時單根 range 可 **8–15pt** → `min_stop_pts=8` 與摩擦 5 點 |
| vol_1s p50 | **4** | quiet 用 **session p50**，非 exhaustion≤15 |
| FT-007 flow | net **−0.07** · n=15 | flow 訊號未必無資訊；**方向**（fade vs chase）不同 |
| FT-015 FVG | n=211 · W30 **≈0** | 回踩進場墓區 — 本案 **無回踩** |
| FT-016 gap | W30 **+13** · G1 fail | 開盤 breakout 方向可正、**可交易性**仍死 |

**規則**：預期 gross **不得**假設優於 FT-016 barrier；fingerprint W30≤0 → 即 MVPClosed。

### E.2 機制標籤

- [ ] Continuation
- [ ] Mean-reversion
- [x] **Liquidity / microstructure**

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
| `min_stop_atr_k` | **≥ 0.75**（fingerprint **0.75**） |

## 5. Pre-register（§F · 開 CF 前封印）

### 5.0 參數 grid（**僅** fingerprint **通過後** tune · 見 §5.2）

| 參數 | 值 / 範圍 | Fingerprint 凍結 |
|------|-----------|------------------|
| `compress_lookback_min` | **30**（1m 根） | 封印 |
| `compress_k` | {0.35, 0.45, 0.55} | **0.45** |
| `atr_regime_cap` | {0.70, 0.75} | **0.75** |
| `atr_compress_floor` | **10.0**（壓縮判定；**非** exit `min_atr=25`） | 封印 |
| `quiet_window_sec` | **60** | 封印 |
| `attack_window_sec` | **60**（緊接 quiet 結束後獨立窗） | 封印 |
| `attack_ratio_min` | {0.62, 0.68, 0.74} | **0.68** |
| `vol_floor_min` | **30**（合約；實際 `max(30, session vol_1s p60)`） | 封印 |
| `min_stop_pts` | **8** | 封印 |
| `min_stop_atr_k` | {0.75, 1.0, 1.25} | **0.75** |
| `k_sl` | = `min_stop_atr_k` @ barrier（§5.0b） | **0.75** |
| `tp_atr_k` | {1.5, 2.0, 2.5} | **2.0** |
| `atr_period` | **20**（SMA TR · 同 [`volatility_baseline.py`](../../../apps/trading-app/src/reporting/volatility_baseline.py)） | 封印 |
| entry window | **10:00–12:30** | 封印 |
| `no_new_entry_after` | **12:30** | 封印 |
| `max_trades_per_day` | **1**（first attack only） | 封印 |
| `min_atr_pts` | **25.0**（**僅** barrier `atr_effective`） | 封印 |

**日期封印**：valid `2026-01-01`～`2026-03-31` · holdout `2026-04-01`～`2026-06-30` — **不得**依結果增刪參。

#### 5.0b Exit sim（0c-1 / 0c-2 共用 · 封印）

| 項目 | 值 |
|------|-----|
| 函式 | [`simulate_atr_barrier_exit`](../../../apps/trading-app/src/reporting/armed_forward_counterfactual.py) |
| `EXIT_VARIANT` | **`atr_barrier_900s`** |
| `hard_stop_atr_k` | = §5.0 `k_sl` 凍結 **0.75**（barrier；進場已含結構 stop 語意 — CF **MUST** 以 `stop_dist_pts` 與 barrier 較嚴者模擬） |
| `tp_atr_k` | **2.0** |
| `max_hold_sec` | **900** |
| `atr_effective` | `max(ATR_ref, min_atr_pts)` @ entry |
| Entry 價 | **tick close** @ attack 觸發後首 tick |
| 摩擦 | **5** 點 round-trip |
| Pilot 前瞻 | tick chase vs IOC ±3 — **0c 不模擬**；`slippage_ratio` 診斷附錄 |

### 5.1 Phase 0 封印 MUST

#### MUST-1 — Compression + regime（1m · 無 lookahead）

| 項目 | 封印定義 |
|------|----------|
| **Lookback** | 連續 **`compress_lookback_min`** 根 **已收** 1m（含當前觸發評估根） |
| **range_M** | `max(High) − min(Low)` 僅 lookback 窗內 |
| **ATR_ref** | `ATR(atr_period)` @ 當根 1m close（`atr_series_from_bars`） |
| **compress_pass** | `range_M < compress_k × max(ATR_ref, atr_compress_floor)` |
| **session_ATR_median** | 當日 09:15 起至當根（含）所有已收 1m 的 ATR_ref **中位數** |
| **regime_pass** | `ATR_ref < atr_regime_cap × session_ATR_median` |
| **評估時點（封印 A）** | `compress_pass` 與 `regime_pass` **MUST** 在 **attack 觸發當下**、以 **同一根** `signal_1m`（§MUST-3）評估；**禁止**「當日更早曾壓縮」事後 arm |
| **禁止** | partial 1m；用 `min_atr=25` **阻擋** compress_pass（僅 barrier 用 25） |

#### MUST-2 — Quiet + Attack（tick · 無 lookahead）

| 項目 | 封印定義 |
|------|----------|
| **Flow 窗** | 複用 [`RollingFlowWindow`](../../../apps/trading-app/src/reporting/flow_flip_counterfactual.py) 語意：`tick_type` 1=buy · 2=sell |
| **Quiet 窗** | 連續 **60s**；`mean(vol_1s) ≤ session_to_date vol_1s **p50**` |
| **Attack 窗** | quiet 結束後 **下一個 60s**（不重疊 quiet） |
| **Long attack** | `buy_ratio_mean ≥ attack_ratio_min` 且 `Σvol ≥ max(vol_floor_min, session vol_1s p60)` |
| **Short attack** | `sell_ratio_mean ≥ attack_ratio_min` 且同 vol 門檻 |
| **buy_ratio_mean** | attack 窗內 `buy_vol / total_vol`（volume-weighted；`total_vol=0` → 無信號） |
| **時段（封印 B）** | quiet 與 attack 窗以 **tick 時間戳** 滾動；attack 窗 **起始** tick **≥ 10:00:00** 且 attack **觸發** tick **< 12:30:00**（交易所時間；與測試 #8/#9 一致） |
| **禁止** | `exhaustion_vol≤15` 作 quiet/死魚；30–600s 事後 grid |

#### MUST-3 — Entry · 結構停損 · 1 筆/日

| 項目 | 封印定義 |
|------|----------|
| **signal_1m** | attack 觸發時刻所屬 **最後一根已收** 1m bar |
| **進場** | attack 條件成立後 **第一個** tick `close`（`entry_ts` = 該 tick） |
| **stop_dist (Long)** | `max(entry − signal_1m_low, min_stop_atr_k × atr_effective)` |
| **stop_dist (Short)** | `max(signal_1m_high − entry, min_stop_atr_k × atr_effective)` |
| **min_stop gate** | `stop_dist < min_stop_pts` → 計入 `attack_signal`、**不**計入 `entry` |
| **1 筆/日** | 首個合格 entry 後當日不再 arm |
| **方向** | Long / Short 分開計數；§3.1 / §3.2 分欄 |

#### MUST-4 — Funnel 六階（絕對數）

`days_with_session` → `compress_pass` → `regime_pass` → `quiet_pass` → `attack_signal` → `entry`

| 階段 | 定義 |
|------|------|
| `attack_signal` | quiet 後 attack 窗 ratio+vol 成立（含 stop 過窄被拒） |
| `entry` | `attack_signal` + `stop_dist ≥ min_stop_pts` + 進場窗 + barrier sim |

#### MUST-5 — 摩擦 · post_entry · skew hook

| 項目 | 封印 |
|------|------|
| 摩擦 | **5** 點/趟 |
| CF JSON | **MUST** 含 `post_entry_diagnosis_by_param` · `skew_gate_by_param` |
| P1 診斷 | `entry_slippage_sensitivity_pts ∈ {0,1,2}` 附錄（非 gate） |
| `slippage_ratio` | `slippage_pts / stop_dist_pts` p50/p90；>0.15 → gate_report 標 `execution_margin_thin` |

### 5.2 Phase 0 診斷順序（fingerprint 先於 grid）

| 步驟 | 通過線 |
|------|--------|
| **0c-1 Fingerprint** | W30 stop-less gross **median > 0** · **n ≥ 15**（G3S） |
| **0c-1b** | W30 ≤ 0 或 n<15 → **`cfa_fingerprint_fail`** · **不跑 grid** |
| **0c-2 Grid** | G1–G2 · G3S · §3.2 skew gate |

| Scenario | Outcome |
|----------|---------|
| W30 ≤ 0 · n≥15 | `cfa_fingerprint_fail` |
| W30 > 0 · grid G1/G2 不過 | `cfa_fingerprint_pass_g1_fail` / `cfa_no_skew_champion` |
| train 過 · valid net≤0 | `cfa_overfit_suspect` · **禁 holdout**（`holdout_blocked_overfit`） |

- **禁止**：fingerprint 未過跑 grid；依 funnel 放寬 ratio / 拉窗至 12:30 外 / 降低 `min_stop_pts`
- `gate_report.md` **MUST** 分節：`## Fingerprint (0c-1)` · `## Grid (0c-2)` · `## Valid 2026 Q1` · **§3.2 skew 附錄**

### 5.3 Post-entry 診斷（FT-012+ MUST · 非 gate）

- 模組：[`post_entry_diagnosis.py`](../../../apps/trading-app/src/reporting/post_entry_diagnosis.py)
- **禁止**依 post_entry 回頭 tune train grid

### 5.4 Outcome codes

| Code | 條件 |
|------|------|
| `cfa_fingerprint_fail` | 0c-1 W30 median ≤ 0 或 n<15 |
| `cfa_fingerprint_pass_g1_fail` | fingerprint 過 · grid G1/G2 不過 |
| `cfa_no_skew_champion` | grid 無 §3.2 合格冠軍 |
| `cfa_overfit_suspect` | train 過 · valid 2026 Q1 net ≤ 0 |
| `cfa_train_no_go` | 其他 train gate 未過 |

## 6. Falsify（§G）

- fingerprint W30 median ≤ 0 且 n≥15 → **`cfa_fingerprint_fail`**
- funnel `compress_pass → attack_signal` < 5% 且 `compress_pass` ≥ 20 → 結構不匹配（gate_report 註記；非自動 MVPClosed）
- funnel `attack_signal → entry` 多數死於 `min_stop_pts` → gate_report 標 `execution_margin_thin`
- **禁止**因 FT-007/015 失敗改為 fade 或回踩

## 7. 人類簽核（§H）

| 欄位 | 值 |
|------|-----|
| 簽核人 | Tim |
| 日期 | 2026-06-28 |
| 決策 | **human-approved**（2026-06-28 · Tim · 資深 TXF 0-design PASS） |

## 8. 設計審閱（Phase 0-design · 非 Pilot Go）

| 欄位 | 值 |
|------|-----|
| 審閱 | **senior-trader PASS** |
| 日期 | **2026-06-28** |
| 結論 | **P0 sealed** — 准 **Phase 0a** |
| 檢查項 | `exhaustion_vol` 未用作死魚 ✅ · `min_stop_pts=8` ✅ · 10:00–12:30 與 FT-016 錯開 ✅ · skew §E.3 ✅ · fingerprint 先於 grid ✅ · 封印 A/B 已寫入 MUST-1/2 |
| 備註 | Pilot 前 P6-5 追價路徑 + tick 分層；0c 不驗執行 |

## 9. CF code review（§I · Phase 0b · train 前必填）

| 欄位 | 值 |
|------|-----|
| Review 方式 | Bugbot / 人類 |
| Review 日期 | pending |
| 審查檔案 | `reporting/compression_flow_attack_counterfactual.py` · tests |
| 結果 | pending |
| 備註 | MUST-1 compress+regime · MUST-2 quiet/attack 窗 · MUST-3 結構 stop · post_entry · skew_gate |
