---
id: FT-019
slug: sweep-fvg-breakout-trail
status: Draft
thesis_class: skew
proposal_id: P-012
opened: 2026-06-29
owner: Tim (draft-proposal 2026-06-29)
target: Alpha Phase 0
holdout_contract: v2.2.1
design_review: senior-trader 2026-06-29 — Conditional PASS (P0 sealed)
parent_ft: FT-015
---

# FT-019 — Sweep FVG Breakout Trail（SPEC）

> **Proposal**：[`P-012`](../../../workspaces/THESIS_QUEUE.md) · **Gate**：[`HOLDOUT_CONTRACT_v2.md`](../ai-backtest-tuning/HOLDOUT_CONTRACT_v2.md) v2.2.1 · **`thesis_class: skew`**  
> **非 FT-015 復活**：進場 **sweep → 5m FVG → breakout** · 出場 **`fvg_mid_trail_skew_900s`** · **long-only**

## 1. Summary（THESIS_BRIEF §A–B）

**一句話**：**Long-only** — 09:15–12:30 內，1m swing **low** 被 **浅扫**（`sweep_k×ATR`）→ **120s 内 reclaim** → 同期 **5m bullish FVG** 形成 → **首 tick close > fvg_high** 做多；初始停损 **FVG 中点**；动态 **`fvg_mid_trail_skew_900s`**（BE/trail 锚 `risk_unit`）；`max_hold_sec=900`。

**錯價因果**

- **誰在錯**：扫掉 swing 下方止损池后，未顺势持有 displacement 延续腿；或固定 barrier / zone retest 进场 **截断厚尾**
- **何時**：09:15–12:30（早盤结构段）
- **機制**：**liquidity / structure continuation** — sweep + imbalance breakout + 结构 trail

**Edge 經濟學（設計審閱 · 封印認知）**

- **母 FT 錨點（FT-015 · 非方向死）**：train n=**211** · barrier gross mean **0.33** · MFE med **~17** · **W900** combined med **+1.0** · Long W900 **+3.0** · legacy W1800 gate med **−0.0** → **`exit_kills_edge`** 非纯进场 falsify
- **本案预期 n**：**25–50**（sweep+breakout+long-only 过滤 · 低于 FRP 211）
- **G1 张力**：breakout + structure 族 · gross 目标 **3–7** · **不**保证 G1 gross>5
- **禁止**：FT-015 zone retest · 固定 1:2 主 TP · 15m 主 structure TF · 在 FT-015 上改 exit 重跑

## 2. 與已死 thesis 差異（§C）

| 最接近的舊 FT | 為何不是同一個 |
|---------------|----------------|
| **FT-015 FRP** | **breakout** `> fvg_high` · **非** tick ∈ zone + vol quiet · exit **`fvg_mid_trail`** 非 `atr_barrier` |
| **FT-018 GUDT** | 锚点 **gap drive** · stop=ATR trail · **无** sweep/FVG |
| **FT-017 CFA** | 盘中 compression flow · **非** sweep+FVG |
| **FT-002 SMC** | FVG 作 **进场触发** · 非 pullback 滤网 veto |
| **P-002 liquidity fade** | **顺** sweep 后 continuation · 非 fade |
| **FT-009 ORB** | 锚点 OR 边界 · 非 swing pool + FVG imbalance |

## 3. 進出規則（§D · 可程式化）

| 項目 | 定義 |
|------|------|
| 方向 | **Long-only** |
| 進場 | §5.1 MUST-1：sweep → reclaim → **5m bullish FVG** → tick **close > fvg_high** |
| 停損 | 初始 **`fvg_mid = (fvg_low+fvg_high)/2`** |
| 停利 / trail | §5.0b **`fvg_mid_trail_skew_900s`** |
| 時間出場 | `max_hold_sec=900` · **12:30** 後禁新倉 |
| 日內 flatten | **是** · max **1** 筆/日 |

## 4. 頻率與 Gate 粗算（§E）

| 項目 | 估計 |
|------|------|
| train 2025 預期 n | **25–50**（G3S **≥15** · 有 **fail_n** 风险） |
| 預期 gross/趟 | **3–7** |
| 預期 net/趟 | 边缘 — skew 厚尾 narrative |

### E.1 粗算錨點（FT-015 · 验尸修正）

| 指標 | FT-015 fp 實績 | FT-019 設計含意 |
|------|----------------|-----------------|
| W900 stop-less med | **+1.0**（combined） | hold 对齐窗 **未** falsify 进场方向 |
| Long W900 med | **+3.0** | **long-only** 与锚点一致 |
| W1800 legacy gate med | **−0.0** | **勿**与 W900 混读 · 非「纯方向错」 |
| barrier gross mean | **0.33** | G1 仍难 · trail + mid stop 测 **可交易性** |
| MFE med | **~17** | 厚尾 trail 有空间 · **`exit_gap`** 附錄 MUST |
| funnel | 222→211 entry | 本案 sweep+breakout 预期 **大幅减 n** |

**exit-led 锚点（若适用）**：母 FT barrier med **−3** · W900 med **+1.0** · MFE med **~17** · **`exit_gap`** ≈ **20**

**規則**：若 W900 median ≤ 0 → **`sfbt_fingerprint_fail_direction`**；**禁止**为救 n 放宽 sweep 或改 15m TF。

### E.2 機制標籤

- [x] **Continuation**
- [ ] Mean-reversion
- [x] **Liquidity / microstructure**（sweep pool）

### E.3 Thesis class（skew · MUST）

| 欄位 | pre-register |
|------|--------------|
| `payoff_ratio_min` | **2.5** |
| `tail_gross_min_pts` | **15** |
| `max_consecutive_losses` | **10** |
| `max_consecutive_loss_pts` | **150** |
| `worst_month_net_pts` | **−120** |
| `top3_win_gross_share_max` | **0.65** |
| 預期 win_rate | **30–45%** |
| 主 stop | **fvg_mid**（结构 · 非 `k_sl×ATR` 主 stop） |

## 5. Pre-register（§F · 開 CF 前封印）

### 5.0 參數 grid（**僅** fingerprint **通過後** tune · 見 §5.2）

| 參數 | 值 / 範圍 | Fingerprint 凍結 |
|------|-----------|-------------------|
| `sweep_lookback_min` | {30, 45, 60}（1m 根） | **45** |
| `sweep_k` | {0.15, 0.25, 0.35} | **0.25** |
| `reclaim_window_sec` | {60, 120, 180} | **120** |
| `structure_tf_min` | **5**（5m FVG · **MUST NOT** 15m 主 TF） | 封印 |
| `swing_lookback` | {3, 5}（5m BOS · 同 FRP 族） | **3** |
| `max_fvg_age_bars` | {4, 6, 8}（5m 根） | **6** |
| `be_risk_k` | {0.75, 1.0} | **1.0** |
| `trail_arm_risk_k` | {1.5, 2.0} | **2.0** |
| `trail_arm_atr_k` | {1.0, 1.5} | **1.5** |
| `trail_dist_atr_k` | {0.4, 0.5, 0.6} | **0.5** |
| `hard_tp_risk_k` | {none, 3.0, 4.0} | **4.0** |
| `atr_period` | **14** | 封印 |
| `min_atr_pts` | **25.0** | 封印 |
| entry window | **09:15–12:30** | 封印 |
| `no_new_entry_after` | **12:30** | 封印 |
| `max_trades_per_day` | **1** | 封印 |
| **方向** | **long-only** | 封印 |

**日期封印**：valid `2026-01-01`～`2026-03-31` · holdout `2026-04-01`～`2026-06-30` — **不得**依結果增刪參。

#### 5.0b Exit sim（0c-1 / 0c-2 共用 · 封印）

| 項目 | 值 |
|------|-----|
| 函式 | **`simulate_fvg_mid_trail_skew_exit`**（Phase 0a **新實作**） |
| `EXIT_VARIANT` | **`fvg_mid_trail_skew_900s`** |
| 初始 stop | **`fvg_mid`** @ entry 时冻结（每笔 entry 固定） |
| `risk_unit` | **`entry − fvg_mid`**（long · MUST > 0；否则 skip entry） |
| BE | 浮盈 ≥ **`be_risk_k × risk_unit`** → stop = **entry** |
| Trail arm | 浮盈 ≥ **`trail_arm_risk_k × risk_unit`** **或** ≥ **`trail_arm_atr_k × ATR`** → **取先触发** |
| Trail dist | `effective_stop = max(BE stop, peak − trail_dist_atr_k×ATR)` |
| Hard TP | 若 `hard_tp_risk_k` 非 none：浮盈 ≥ **`hard_tp_risk_k × risk_unit`** → TP @ entry + hard_tp×risk_unit |
| `max_hold_sec` | **900** |
| 摩擦 | **5** 點 round-trip |
| **MUST NOT** | 固定 **1:2** 作主 exit（`pct_hit_2R` 仅 post_entry 附錄） |

**MUST — 每 tick 狀態機（P0 · 同 FT-018 顺序 · initial stop = fvg_mid）**

| 步驟 | 動作 |
|------|------|
| 1 | 更新 **peak** |
| 2 | BE arm（`be_risk_k × risk_unit`） |
| 3 | Trail arm（risk **或** ATR 阈值 · **先触发者**） |
| 4 | 更新 `effective_stop` |
| 5 | Hard TP 检查 |
| 6 | Stop 检查 · 时间出场 |

**同 tick tie-break**：stop 优先于 TP · peak 更新先于 stop 检查 · initial stop 与 BE 同 tick → **较高 stop（long = max）**

#### 5.0c Fingerprint window（v1.5 · MUST）

| 欄位 | 值 |
|------|-----|
| `fingerprint_window_sec` | **900** |
| Gate 讀取 | **W900** `close_delta_median` |
| **Primary key** | **禁止** W1800 legacy 作 0c-1 gate |
| FT-015 錨點 | W900 **+1.0** 为历史参考 · **非** 本案 gate KPI |

### 5.1 Phase 0 封印 MUST

#### MUST-1 — Sweep → reclaim → FVG → breakout（long-only）

| 項目 | 封印定義 |
|------|----------|
| **Swing 池 L** | 过去 **`sweep_lookback_min`** 根 **1m** bar 的 **confirmed swing low**：bar `i` 为 swing low 当且仅当 `Low[i] < Low[i±1]`（左右各 1 根已收 1m · **无** 未来根） |
| **Sweep** | tick **low** < `L − sweep_k × ATR(14)` · ATR @ sweep 日 **09:14 bar close** · sweep tick **≥ 09:15** 且 **< 12:30** |
| **Reclaim** | sweep tick 后 **`reclaim_window_sec`** 内 **首** tick **close > L**（reclaim_ts 封印） |
| **FVG** | **5m bullish** FVG（[`_detect_fvgs`](../../../packages/strategies/vwap-momentum/src/strategy_vwap_momentum/structure.py)）· **`created_ts` = 第三根 5m bar 收盘** · **sweep_ts < created_ts** · **age ≤ max_fvg_age_bars** · **未 mitigated** |
| **BOS 上下文** | FVG **bullish** · 且 sweep 发生时间 **< FVG `created_ts`**（sweep 在位移前） |
| **Breakout entry** | reclaim OK 后 · **首 tick close > fvg_high** · tick 时间 **< 12:30** |
| **MUST NOT entry** | tick price ∈ `[fvg_low, fvg_high]`（**非 FT-015 zone retest**） |
| **risk_unit** | `entry − fvg_mid` **≤ 0** 或 **< `min_risk_pts`（8）** → **无 entry** · **MUST NOT** fallback 至 ATR stop |
| **1 筆/日** | 首笔合格 breakout → entry |

#### MUST-2 — 摩擦 · funnel · 附錄

- 摩擦 **5** 点 round-trip · `atr_effective = max(atr, min_atr_pts)`
- **P1 附錄（非 gate）**：`exit_gap` · `pct_mfe_ge_2R` · `pct_hit_2R_before_stop` · slippage {0,1,2}

#### MUST-3 — Funnel 六階（絕對數）

`days_with_session` → `sweep_signal` → `reclaim_ok` → `fvg_active` → `breakout_signal` → `entry`

| 階段 | 定義 |
|------|------|
| `sweep_signal` | 合格 sweep tick 出现 |
| `reclaim_ok` | reclaim 窗内 close > L |
| `fvg_active` | 5m bullish unmitigated FVG · age OK · sweep 在 FVG 前 |
| `breakout_signal` | tick close > fvg_high |
| `entry` | breakout + risk_unit OK + trail sim 完成 |

#### MUST-4 — post_entry · skew hook

- CF JSON **MUST** 含 `post_entry_diagnosis_by_param`（**W900** primary）· `skew_gate_by_param`
- `gate_report` **MUST**：`exit_gap` · friction@7 · G-SK5

### 5.2 Phase 0 診斷順序（fingerprint 先於 grid）

| 步驟 | 通過線 |
|------|--------|
| **0c-1 Fingerprint** | **W900** stop-less gross **median > 0** · **n ≥ 15**（G3S） |
| **0c-1b direction** | W900 ≤ 0 · n≥15 → **`sfbt_fingerprint_fail_direction`** |
| **0c-1b n** | W900 > 0 · n<15 → **`sfbt_fingerprint_fail_n`** |
| **0c-2 Grid** | G1–G2 · G3S · §3.2 |

| Scenario | Outcome |
|----------|---------|
| W900 ≤ 0 · n≥15 | `sfbt_fingerprint_fail_direction` |
| W900 > 0 · n<15 | `sfbt_fingerprint_fail_n` |
| W900 > 0 · grid fail | `sfbt_fingerprint_pass_g1_fail` / `sfbt_no_skew_champion` |
| train 過 · valid net≤0 | `sfbt_overfit_suspect` |

### 5.3 Post-entry（非 gate）

- [`post_entry_diagnosis.py`](../../../apps/trading-app/src/reporting/post_entry_diagnosis.py)
- **禁止**依 post_entry 回頭 tune grid 或改 `fingerprint_window_sec`

### 5.4 Outcome codes

| Code | 條件 |
|------|------|
| `sfbt_fingerprint_fail_direction` | 0c-1 W900 median ≤ 0 · n≥15 |
| `sfbt_fingerprint_fail_n` | W900 > 0 · n<15 |
| `sfbt_fingerprint_pass_g1_fail` | fingerprint 過 · grid G1/G2 不過 |
| `sfbt_no_skew_champion` | grid 過 · §3.2 disqualify |
| `sfbt_overfit_suspect` | train 過 · valid net ≤ 0 |
| `sfbt_train_no_go` | 其他 |

## 6. Falsify（§G）

- W900 median ≤ 0 且 n≥15 → **`sfbt_fingerprint_fail_direction`**
- funnel `fvg_active → entry` < 5% 且 fvg_active ≥ 20 → gate_report 註記（非自动 MVPClosed）
- fingerprint 過 · G1 fail · **`exit_gap`** 仍大 → MVPClosed · **禁止**第三 exit 变形
- **禁止** zone retest · fade · EMA overlay

## 7. 人類簽核（§H）

| 欄位 | 值 |
|------|-----|
| 簽核人 | |
| 日期 | |
| 決策 | **pending**（`draft-proposal`） |

## 8. 設計審閱（Phase 0-design · 非 Pilot Go）

| 欄位 | 值 |
|------|-----|
| 審閱 | 資深 TXF 交易人員 |
| 日期 | 2026-06-29 |
| 審閱檔案 | 本 SPEC · [`PLAN.md`](PLAN.md) |
| 結論 | **Conditional PASS — Revise（P0 已封印）** — 准 **Phase 0a 工程準備** · **0c train 待** P-012 `human-approved`（建議 **P-011 0c-1 結案後** Pick） |
| Phase 0a prompt | [`PLAN.md`](PLAN.md) §「給 Agent 的 Phase 0a 開工 prompt」 |

### 審閱摘要

- **vs FT-015**：**PASS** — 進場 **sweep → reclaim → breakout > fvg_high**（非 zone retest）· 出場 **`fvg_mid_trail_skew_900s`**（非 `atr_barrier`）· 母 FT W900 +1.0 / Long +3.0 為 **exit_kills_edge** 锚点 · **非** FT-015 復活。
- **vs FT-018**：進場 **不撞**（sweep+FVG vs gap drive）· exit 同 **skew_900s 族** · **須新函式** `simulate_fvg_mid_trail_skew_exit`（初始 stop=`fvg_mid` · `risk_unit=entry−fvg_mid`）· **0c 與 P-011 串行** · 禁止並行 skew fingerprint。
- **n 25–50 / fail_n**：**風險實在且偏高** · funnel 六階 MUST 出絕對數 · W900>0 且 n<15 → **`sfbt_fingerprint_fail_n`（無結論，非方向死）** · **禁止** 為救 n 放寬 sweep 或改 15m 主 TF。
- **5m FVG + 1m sweep timing**：TXF 早盤可接受 · P0 四項已封印（§5.1）· **0a PLAN case 1–12 + T1–T8 比特测為成敗關鍵**。
- **skew + G1 张力**：W900 fingerprint 與 G1 gross **可能分叉** · FRP barrier gross 0.33 / MFE ~17 預警 G1 仍難 · fingerprint 過而 G1 fail 且 **`exit_gap` 仍大** → MVPClosed · **禁止** 第三 exit 變形。
- **W900**：與 `max_hold_sec=900` 對齊 · **禁止** W1800 legacy 作 0c-1 gate。

### P0（0a 前 — 已写入 SPEC §5.1）

1. **Swing low** fractal 定义 inline（1m · 无 lookahead）
2. **`sweep_ts < FVG created_ts`** 严格序（第三根 5m bar 收盘）
3. **`min_risk_pts=8`** · 无 ATR stop fallback
4. **Trail arm** dual trigger（risk **或** ATR · **先触发**）

### P1（0b 前）

1. `exit_gap` · `pct_mfe_ge_2R` · `pct_hit_2R_before_stop` · slippage {0,1,2}
2. friction@7 · G-SK5 附錄

### Pick 建議

- **0-design**：P0 封印後 → **Conditional PASS** · 准 Phase 0a 工程。
- **human Pick**：**P-011（FT-018）優先** → 0c-1 結案後再 **P-012 `human-approved`** · 一次 Pick 一個 skew thesis。

## 9. CF code review（§I · Phase 0b · train 前必填）

| 欄位 | 值 |
|------|-----|
| Review 日期 | |
| 結果 | pending |
