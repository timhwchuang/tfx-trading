---
id: FT-015
slug: fvg-retest-pullback
status: MVPClosed
closed: 2026-06-28
outcome: frp_fingerprint_fail
thesis_class: skew
proposal_id: P-009
opened: 2026-06-28
owner: Tim (human-approved 2026-06-28)
target: Alpha Phase 0
holdout_contract: v2.2.1
design_review: pending
---

# FT-015 — FVG Retest Pullback（SPEC）

> **Proposal**：[`P-009`](../../../workspaces/THESIS_QUEUE.md) · **Gate**：[`HOLDOUT_CONTRACT_v2.md`](../ai-backtest-tuning/HOLDOUT_CONTRACT_v2.md) v2.2.1 · **`thesis_class: skew`**

## 1. Summary

**一句話**：5m **同向 BOS** 後留下未 mitigated **FVG**；09:15–12:30 tick **回測 zone** 且 **vol_1s ≤ session p40** → **順 BOS 方向**進場；Phase 0 **雙向**；每日 first retest only。

**錯價因果**

- **誰在錯**：追價後在結構缺口（FVG）過度反應，忽略 BOS 方向延續
- **何時**：09:15–12:30
- **機制**：**liquidity / structure continuation**（非 VWAP fade、非 OR 堆疊）

## 2. 與已死 thesis 差異

| 最接近的舊 FT | 為何不是同一個 |
|---------------|----------------|
| FT-002 SMC filter | FVG zone 是 **進場觸發**，非 pullback 濾網 veto |
| P-004 / FT-014 | 錨點 **結構缺口**，非 VWAP hold/touch |
| FT-010 VTP | 非 stretch-to-buffer |
| FT-011 SCB | 無 session confluence / OR 堆疊 |

## 3. 進出規則

| 項目 | 定義 |
|------|------|
| 方向 | **Long + Short**（順 BOS） |
| 進場 | tick.close ∈ [fvg_low, fvg_high] · vol_1s ≤ p40(session-to-date) |
| 停損 | `k_sl × ATR(14)` |
| 停利 | `simulate_atr_barrier_exit` · `atr_barrier_900s` |
| 時間出場 | max_hold_sec=900 · 12:30 後禁新倉 |
| 日內 flatten | **是** · max 1 筆/日 |

## 4. 頻率與 Gate

| 項目 | 估計 |
|------|------|
| train 2025 預期 n | **40–80**（G3S **≥15**） |
| 預期 gross/趟 | **4–7** |
| class | **skew** — §3.2 G-SK1–SK5 |

### E.3 Skew pre-register

| 欄位 | 值 |
|------|-----|
| payoff_ratio_min | **2.5** |
| tail_gross_min_pts | **15** |
| max_consecutive_losses | **10** |
| max_consecutive_loss_pts | **150** |
| worst_month_net_pts | **−120** |
| top3_win_gross_share_max | **0.65** |
| k_sl | **≥ 0.75**（fingerprint **1.0**） |

## 5. Pre-register

### 5.0 Grid（僅 fingerprint 過後）

| 參數 | 值 / 範圍 | Fingerprint |
|------|-----------|-------------|
| `swing_lookback` | {3, 5} | **3** |
| `max_fvg_age_bars` | {6, 12}（5m 根） | **6** |
| `vol_pct_max` | {0.40} | **0.40** |
| `k_sl` | {0.75, 1.0, 1.25} | **1.0** |
| `tp_atr_k` | {1.5, 2.0, 2.5} | **2.0** |
| FVG/BOS | FT-002 [`structure.py`](../../../packages/strategies/vwap-momentum/src/strategy_vwap_momentum/structure.py) §4.7 | 封印 |
| entry window | 09:15–12:30 | 封印 |

#### 5.0b Exit

| 項目 | 值 |
|------|-----|
| EXIT_VARIANT | **`atr_barrier_900s`** |
| max_hold_sec | **900** |
| 摩擦 | **5** |

### 5.1 MUST

| MUST | 定義 |
|------|------|
| MUST-1 | `compute_structure` / FT-002 §4.7 · 僅已收 5m · partial FVG touch ≠ mitigated |
| MUST-2 | tick entry · 摩擦 5 |
| MUST-3 | funnel：bos_active_fvg → zone_touch → vol_ok → entry · 1 筆/日 |
| MUST-4 | vol_1s = 同秒 tick volume 合計 · threshold = session-to-date **p40** |

### 5.2 Phase 0 流程

| 步驟 | 通過線 |
|------|--------|
| 0c-1 | W30 stop-less med **> 0** · **n ≥ 15** |
| 0c-2 | G1–G2 · G3S · §3.2 skew gate |

### 5.4 Outcome codes

| Code | 條件 |
|------|------|
| `frp_fingerprint_fail` | 0c-1 W30≤0 或 n<15 |
| `frp_fingerprint_pass_g1_fail` | fingerprint 過 · grid G1/G2 不過 |
| `frp_no_skew_champion` | grid 過 · §3.2 disqualify |
| `frp_overfit_suspect` | train 過 · valid net≤0（**禁 holdout**） |

## 6. Falsify

- funnel 轉化 < 5% 且 bos_active_fvg ≥ 20 → gate_report 註記
- train n < 15 → `frp_fingerprint_fail`
- W30 med ≤ 0 → 假 FVG / 方向錯

## 7. 人類簽核

| 欄位 | 值 |
|------|-----|
| 簽核人 | Tim |
| 日期 | 2026-06-28 |
| 決策 | **approved**（P-009 GO） |

## 9. CF code review

| 欄位 | 值 |
|------|-----|
| Review 日期 | 2026-06-28 |
| 結果 | **PASS**（見 gate_report §0b） |
| 備註 | 0c-1 W30 med −0 · n=211 · 方向錯 · grid 跳過 |
