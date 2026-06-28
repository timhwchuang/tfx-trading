---
id: FT-013
slug: supertrend-flip
status: Draft
thesis_class: mean_robust
proposal_id: P-007
opened: 2026-06-28
owner: Tim (human-approved 2026-06-28)
target: Alpha Phase 0
holdout_contract: v2.2.1
---

# FT-013 — SuperTrend Flip Continuation（SPEC）

> **Proposal**：[`P-007`](../../../workspaces/THESIS_QUEUE.md) · **Gate**：[`HOLDOUT_CONTRACT_v2.md`](../ai-backtest-tuning/HOLDOUT_CONTRACT_v2.md) v2.2.1 · **`thesis_class: mean_robust`**

## 1. Summary（THESIS_BRIEF §A–B）

**一句話**：09:15–12:00，5m SuperTrend（HL/2 ± k×ATR）**翻多**且 tick 確認收在 trend line 上方 → **做多**順勢延續；Phase 0 **long-only**；flip 後 **cooldown** 防 whipsaw。

**錯價因果**

- **誰在錯**：追價/停損盤在 kbar 級趨勢翻轉初段逆勢
- **何時**：09:15–12:00（交易所時間）
- **機制**：**continuation**（非 VWAP fade、非 tick momentum armed）

## 2. 與已死 thesis 差異（§C）

| 最接近的舊 FT | 為何不是同一個 |
|---------------|----------------|
| FT-004/005 | 觸發是 **5m band flip**，非 `momentum_armed` / timeout tick |
| FT-009 ORB | 無 opening range；訊號為 ATR 通道方向 |
| P-004 VWAP pullback | 進場錨點 **SuperTrend line**，非 VWAP 支撐 |
| FT-010 VTP | 非 stretch-to-buffer；頻率預期 **80–150**/年 |

## 3. 進出規則（§D · 可程式化）

| 項目 | 定義 |
|------|------|
| 方向 | Phase 0 **Long-only**（Short 留 Phase 0b 診斷） |
| 進場 | 已收 **5m** bar SuperTrend 由 bear→bull；下一 tick `close > supertrend_line`；距上一 flip ≥ `cooldown_bars` |
| 停損 | `k_sl × ATR20`（k ∈ pre-register，**≥ 0.75**） |
| 停利 / trail | `atr_barrier_180s` 或 `k_tp/k_trail × ATR`（grid 預登） |
| 時間出場 | 12:00 後禁新倉；日內 flatten |
| 日內 flatten | **是** |

> 進場/出場細節之 **封印 MUST** 見 §5.1（開 CF 前不得改）。

## 4. 頻率與 Gate 粗算（§E）

| 項目 | 估計 |
|------|------|
| train 2025 預期 n | **80–150**（G3 n≥30） |
| 預期 gross/趟 | **3–6**（須 mean **> 5** 過 G1） |
| 預期 net/趟（扣 5 點） | 邊緣正 — 以 CF 為準 |

### E.1 粗算錨點

| 最接近同族 MVPClosed | v2.1 train 實績 |
|----------------------|-----------------|
| FT-004 momentum continuation | gross **+1.89**/趟 — G1 未過 |
| FT-005 timeout continuation | timeout 子集 gross **+5.48** — 全 cohort No-Go |

### E.2 機制標籤

- [x] **Continuation**
- [ ] Mean-reversion
- [ ] Liquidity / microstructure

### E.3 Thesis class

- [x] **`mean_robust`**
- [ ] `skew`

## 5. Pre-register（§F · 開 CF 前封印）

### 5.0 參數 grid（**僅** fingerprint **通過後** tune · 見 §5.2）

| 參數 | 值 / 範圍 | Phase 0 第一輪 |
|------|-----------|----------------|
| `atr_period` | {10, 14} | **10**（凍結） |
| `st_mult` | {2.5, 3.0, 3.5} | **3.0**（凍結至 fingerprint 過） |
| `cooldown_bars` | {3, 6} | **6**（凍結） |
| `k_sl` | {0.75, 1.0, 1.25} | **1.0**（凍結） |
| session | 09:15–12:00 entry | 封印 |
| `no_new_entry_after` | **12:00** | 封印 |
| `direction` | Phase 0 **Long-only** | 封印 |

**日期封印**：valid `2026-01-01`～`2026-03-31` · holdout `2026-04-01`～`2026-06-30` — **不得**依結果增刪參。

### 5.1 Phase 0 封印 MUST（資深交易員 review · 2026-06-28）

下列三項 **MUST** 寫死於 `*_counterfactual.py` 與 tests；Phase 0b review **逐條對照**。

#### MUST-1 — 無 repaint（SuperTrend · flip 確認 tick）

| 項目 | 封印定義 |
|------|----------|
| K 線 | SuperTrend **僅**用 **已收** 5m bar；**禁止** partial / 當根 intrabar 更新 band 或 flip 狀態 |
| 暖機 | 當日 session 09:15 前 bar **不**產生 flip 信號；跨日 lookback 僅供 ATR/ST 計算，不觸發進場 |
| Flip 判定 | bar `b` 收盤後：前一根 ST 方向 = bear，當根 = bull（標準 HL/2 ± k×ATR SuperTrend 定義，寫死於 CF） |
| **Flip 確認 tick** | `entry_arm_ts` = bar `b` 的 **5m bucket 收盤時戳**（exchange time）；**第一個**滿足 `tick.ts >= entry_arm_ts` **且** `tick.close > supertrend_line(b)` 的 tick 為 **唯一**合法進場錨點 |
| Fill 價 | 該確認 tick 的 `close`（與其他 CF 一致；**不加**額外 intrabar 理想價） |
| 測試 | tests **MUST** 含：partial bar 不 flip、flip 後第二 tick 才 confirm、同 bar 內 ST 線漂移不補進場 |

#### MUST-2 — Fill / 滑價（相對停損 · 摩擦內建）

| 項目 | 封印定義 |
|------|----------|
| 摩擦 | 每趟 round-trip **5 點**（`SHARED_ASSUMPTIONS` §3.1）；**所有** net / G2 已內建 |
| 滑價假設 | CF 主路徑 **`slippage_pts = 1`**（單邊進場劣化 1 點；可 pre-register 敏感性 {0, 1, 2} **僅**附錄，不改主判） |
| 停損尺度 | 進場時 `stop_dist_pts = k_sl × ATR20`（Phase 0 凍結 k_sl=**1.0** → 典型 **~0.75–1.25×ATR**，**非** legacy 固定 6 點） |
| **量化 MUST** | `gate_report.md` **MUST** 表：`slippage_ratio_p50 = slippage_pts / stop_dist_pts`（及 p90）；並對照 **legacy 參考** `6 / ATR20`（≈ strategy_diagnosis **0.23×ATR** 尺度）供人類解讀 |
| 解讀門檻 | 若 `slippage_ratio_p50 > 0.15`（1–2 點占停損 >15%）→ gate_report **MUST** 標 `execution_margin_thin`（非自動 MVPClosed，供 Phase 0b 討論） |

#### MUST-3 — Whipsaw × cooldown × 12:00 flatten（摩擦疊加 · long-only）

| 項目 | 封印定義 |
|------|----------|
| 方向 | Phase 0 **僅 Long**；Short flip **不**進場（留 post_entry 診斷欄位即可） |
| Cooldown | 兩次 **long** flip 進場間隔 ≥ `cooldown_bars` 根 **已收** 5m bar；冷卻期內 flip **忽略** |
| 12:00 窗 | `tick.ts >= 12:00` → **禁止**新進場；持倉依 exit 規則 **日內 flatten** |
| 尾盤 flip | 11:45 後新 flip **不** arm（pre-register `last_entry_before=11:45`，避免進場即 flatten 純送摩擦） |
| Funnel MUST | `flip_detected` → `cooldown_pass` → `window_pass` → `entry`；**另**報 `flips_per_day` p50/p90、**理論摩擦上限** = `entries_per_day × 5` |
| 對照 | 同一 train 窗 **P-004 順勢指紋**（VWAP hold pullback）**不**混跑；FT-013 結果與 P-004 僅 **post_entry W30 median** 文字對照，不共用 grid |

### 5.2 Phase 0 診斷順序（Playbook · **先 fingerprint 後 grid**）

**禁止**第一輪就掃 `st_mult` / `cooldown` grid。

| 步驟 | 動作 | 通過線 |
|------|------|--------|
| **0c-1 Fingerprint** | 凍結 §5.0 單點參數；跑 **2025 train**；產 **funnel** + **`post_entry_diagnosis`** | flip→entry 漏斗可解讀；**W30 stop-less gross median > 0**（順勢指紋）且 n≥30 |
| **0c-1b 判斷** | 若 W30 median ≤ 0 | **MVPClosed**（whipsaw / 方向錯）— **不**進 0c-2 |
| **0c-2 Grid** | 僅 fingerprint 過 → 跑 §5.0 全 grid | G1–G3 · §3.1 · valid 對照 |

`gate_report.md` **MUST** 分節：`## Fingerprint (0c-1)` 與 `## Grid (0c-2)`；**禁止**用 grid 最佳組回頭粉飾 fingerprint 敘事。

**Post-entry / funnel（FT-012+ Playbook MUST）**

- 模組：[`post_entry_diagnosis.py`](../../../apps/trading-app/src/reporting/post_entry_diagnosis.py)
- JSON 含 `post_entry_diagnosis_by_*`；`gate_report` 附錄 W5/W15/W30 stop-less + MFE/MAE
- **不進** G1–G3；**禁止**依 post_entry 回頭 tune train grid

## 6. Falsify（§G）
- train net ≤ 0 → MVPClosed
- train 過、valid net ≤ 0 → `overfit_suspect`
- train flip 後 W30 stop-less **median ≤ 0** 且 n≥30 → whipsaw / 非順勢指紋 → **MVPClosed（0c-1 即停，不跑 grid）**
- §3.1 單邊 / median disqualify（long-only Phase 0 仍看 Long 欄）
## 7. 人類簽核（§H）

| 欄位 | 值 |
|------|-----|
| 簽核人 | Tim |
| 日期 | 2026-06-28 |
| 決策 | **approved**（P-007 → FT-013 · mean_robust · long-only Phase 0） |

## 8. CF code review（§I · Phase 0b · train 前必填）

| 欄位 | 值 |
|------|-----|
| Review 方式 | |
| Review 日期 | |
| 審查檔案 | `reporting/supertrend_flip_counterfactual.py` · `tests/reporting/test_supertrend_flip_counterfactual.py` |
| 結果 | |
| 備註 | MUST-1/2/3 逐條 PASS · fingerprint 順序 · 無 partial-bar flip |

## 參考

- PLAN：[`PLAN.md`](PLAN.md)
- Playbook：[`ALPHA_RESEARCH_PLAYBOOK.md`](../ai-backtest-tuning/ALPHA_RESEARCH_PLAYBOOK.md)
- Workspace（待建）：`workspaces/stf-baseline/`
