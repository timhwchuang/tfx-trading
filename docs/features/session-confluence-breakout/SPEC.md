---
id: FT-011
slug: session-confluence-breakout
status: MVPClosed
opened: 2026-06-28
owner: human+agent
target: Pilot-prep
stable_contract: packages/strategies/session-confluence-breakout/SPEC.md
audit_schema_version: 1
---

# FT-011 — Session Confluence Breakout（Thesis H）

> **SPEC** = 時段選擇性開盤區間突破 + VWAP 趨勢 + 量能/波動共振（Phase 0 **long-only**）。**主判**：Holdout v2.1 **2025 train**。

## 1. Summary

**問題**：FT-009 ORB 在 legacy 01–04 過關但 **holdout 結構失敗**（Short 厚尾、median 負）；FT-010 回踩 buffer 導致 **n≪30**。需驗證：在 **嚴格時段** 內，對純 ORB first break 加上 **VWAP 趨勢 + 量能 + ATR** 共振，能否得到 **穩定 long-only** edge。

**目標**：08:45 起 **R 分鐘** opening range；區間結束後、於 **早盤或尾盤窗** 內，當 **C1–C5** 於同一根 1m 收盤同時成立時 long 進場；出場 ATR-scaled barrier + tick 停損。

**與 live 關係**：與 `strategy-vwap-momentum` **互補**（非取代）；UAT **不切換**直至 train 過關 + valid 確認 + holdout + 人類書面 Go。

**要證偽**：confluence 濾網相對純 ORB（同 `opening_range_minutes`、bk=0）是否 **提升 net/趟** 且 **n≥30**——而非 ORB 換皮。

**使用者**：`workspaces/scb-baseline` Phase 0 counterfactual → plugin → baseline。

## 2. 現況 vs 目標

| 面向 | FT-009 ORB | FT-010 VTP | **FT-011 SCB** |
|------|------------|------------|----------------|
| 觸發 | 區間後 **first break**（雙向） | stretch 後 **回踩** buffer | **突破 OR 高** + VWAP 趨勢 + 量能 |
| 時段 | 區間後至 session 末 | 早+尾；午盤禁開 | **早 08:55–10:30** + **尾 13:00–13:35** |
| 方向 | Long / Short | long-only | **long-only** |
| VWAP | 無 | session 累積 + 斜率 | session 累積 + **3 根遞增** |
| 量能 | 無 | 縮量回踩 + 攻擊量 | **突破棒 ≥ 5 均量 ×1.4** |
| 停損尺度 | 0.75×ATR | ≥1.0×ATR（floor 9） | **≥1.2×ATR（floor 10）** |
| 頻率 | ≤1 筆/日 | ≤1 筆/日 | **≤1 筆/日** |
| Gate 主判 | legacy 01–04 | legacy 01–03 | **v2.1 2025 train** |

**本 thesis 保留什麼**：session-anchored 開盤結構（ORB）、VWAP 趨勢確認（VTP 子集）、低頻 first-signal。

**本 thesis 否決什麼**：全時段 breakout、vol_1s spike / `momentum_armed`、Phase 0 雙向 gate、回踩 buffer 路徑、前日高點突破（未 pre-register）。

## 3. 資料與指標契約（MUST）

1. **資料**：`tick_cache/{code}_{date}.csv` → 1m bar；VWAP / ATR 與 engine **`IndicatorState`** 同語意（tick 累積量加權 session VWAP；ATR = SMA(TR, **14**））。
2. **ATR 單位**：點數；`hard_stop_pts = max(hard_stop_atr_k × ATR, hard_stop_floor_pts)`。
3. **停損觸發**：回放 **tick High/Low**；**禁止**僅用 1m Close 判定停損。
4. **摩擦**：每趟 **5 點** round-trip（entry +2.5、exit +2.5）；所有 Gate / leaderboard 以 **net** 為準。
5. **交易所時間**：`exchange_time` / session 邊界；`session_bucket` 語意對齊 FT-006 / FT-010（`morning` / `afternoon` / `close`）。

## 4. 進場契約（MUST — Phase 0 CF，pre-registered）

### 4.1 開盤區間

- **起算**：`08:45`（`SESSION_START`），持續 `opening_range_minutes` 分鐘。
- **高低**：區間內 1m bar **High/Low**（不含區間外 bar）。
- **`range_end_ts`**：`08:45 + opening_range_minutes`。
- **區間寬濾網**：**無**（Phase 0 不套用 ORB `min_range_atr_k`；避免隱性 sweep）。

### 4.2 可進場時間窗

| 窗 | 條件 |
|----|------|
| 早盤 | `08:55 ≤ t < 10:30` |
| 尾盤 | `13:00 ≤ t < 13:35`（持倉須於 **13:35 前** 平倉） |
| **禁止** | `11:00 ≤ t < 13:00` 新倉 |
| 區間 | `t > range_end_ts`（區間結束後才評估突破） |

### 4.3 進場條件（同一根 1m **收盤** 全滿足）

| ID | 規則 | 可執行定義 |
|----|------|------------|
| C1 | 趨勢 | `close > session_vwap` |
| C2 | VWAP 斜率 | `vwap[t] > vwap[t-1] > vwap[t-2]`（嚴格遞增 **3** 根） |
| C3 | 突破 | `close > range_high`（**無** buffer；Phase 0 釘死 **bk=0**） |
| C4 | 波動 | `ATR(14) ≥ min_atr_threshold_points`（固定 **20**） |
| C5 | 量能 | `volume[t] ≥ mean(volume[t-5:t-1]) × volume_mult`（**1.4**） |
| C6 | 頻率 | **first valid signal only**；每交易日 **≤1** 筆 |
| C7 | 日內熔斷 | 策略內累計 net ≤ **−30** 點 → `block_new_entry` |

### 4.4 Phase 0 執行模型

- Counterfactual **僅** market entry @ bar close（+ entry friction 2.5pt）。
- Limit @ `range_high + offset` → **Phase 1b** 對照，不在 Phase 0 gate 內。

**禁止**：

- `momentum_armed` / `vol_1s` spike 任何路徑
- Phase 0 以 combined long+short 作唯一 gate
- train 外 tune；holdout 解封前看 2026 Q2
- 前日高點突破（Phase 0 **刪除**）

## 5. 出場契約（MUST）

Phase 0 **僅** barrier sim + tick 停損（對齊 FT-004/006/009）：

| 參數 | 語意 | 值 |
|------|------|-----|
| `hard_stop_atr_k` | 硬停距離 | **1.2** |
| `hard_stop_floor_pts` | 停損地板 | **10** |
| `tp_atr_k` | 止盈（相對 entry） | **1.8** |
| `max_hold_sec` | 時間停 | **1200**（20 分） |
| `exit_grace_sec` | grace 內僅 hard stop | **10** |

- `hard_stop_pts = max(hard_stop_atr_k × ATR, hard_stop_floor_pts)`
- `tp_price = entry + tp_atr_k × ATR`（Phase 0 **無**結構高點 cap；cap 留 Phase 1b）
- 尾盤進場：持倉 **不得跨越 13:35**（session 強平）

**Phase 1b（非 Phase 0 gate）**：`tp = min(entry + tp_atr_k×ATR, intraday_structure_high)` 須單獨子版本。

## 6. 日期切分與 Go / No-Go Gates

引用 [`HOLDOUT_CONTRACT_v2.md`](../ai-backtest-tuning/HOLDOUT_CONTRACT_v2.md) **§2.1**（FT-011+ MUST）：

```text
Train   2025-01-01 … 2025-12-31   主判 G1–G3 + §3.1
Valid   2026-01-01 … 2026-03-31   overfit 探測（不作主判）
Holdout 2026-04-01 … 2026-06-30   封印（06 未落地 → holdout_partial）
```

### Phase 0（counterfactual · long only · train = 2025 全年）

| Gate | 條件 | 未過 |
|------|------|------|
| **G1** | train gross/趟 **> 5** | **MVPClosed** |
| **G2** | train net/趟 **> 0**（摩擦 5） | **MVPClosed** |
| **G3** | train **n ≥ 30** | **MVPClosed** |
| **G4** | train QSL **< 25%** | 診斷；`hard_stop_atr_k` **一次**重跑 |
| **G5** | train 無單月 net/趟 **< −2** | 不穩標記 |

### §3.1 冠軍選取（MUST）

1. **net/趟最高**（平手 → n 較大）
2. **方向拆解 MUST**：Long / Short 分欄（Phase 0 僅 long，Short 欄為空）
3. **Disqualify**（任一）：
   - `gross_median ≤ −5`
   - 單一方向貢獻 **> 80%** gross PnL
   - 任一方向 train net/趟 **< −3**

無合格冠軍 → **`no_robust_champion`**，不進 Holdout。

### Valid（2026 Q1 · 參考）

| 角色 | 規則 |
|------|------|
| 主判 | **不作** Phase 0 過關依據 |
| 紅旗 | train 過但 valid net ≤ 0 → **`overfit_suspect`** |
| 動作 | gate_report **MUST** 記 valid 對照 |

### Holdout（2026 Q2 · 04–06）

見 [`HOLDOUT_CONTRACT_v2.md`](../ai-backtest-tuning/HOLDOUT_CONTRACT_v2.md) §5（H1–H5）；**低頻** thesis：三月合併 n≥20 且 net 同號。

### 診斷 Gate（非 MVPClosed）

| ID | 條件 | 用途 |
|----|------|------|
| **G5-bucket** | 早盤 / 尾盤 `session_bucket` 分欄 net/趟 | 檢討時段濾網 |
| **SCB-STRICT**（參考） | gross/趟 **> 6**、net/趟 **> 1** | 提案門檻對照，**不作**主判 |

### ORB 對照（MUST 產物）

同 `opening_range_minutes ∈ {20, 30}`、ORB **bk=0**、同窗 long-only 子集下，產出 [`scb_vs_orb_delta.json`](../../../workspaces/scb-baseline/reports/scb_vs_orb_delta.json)：

- ORB 信號數 vs SCB 信號數
- 被 confluence 濾掉筆數與 net 增量
- 漏斗：ORB entry → SCB 通過率

## 7. Pre-registered 參數格（Phase 0 ONLY）

| 軸 | 值 | 備註 |
|----|-----|------|
| `opening_range_minutes` | **20, 30** | **唯一** sweep 軸 |

**固定**（禁止 Phase 0 sweep）：

| 參數 | 值 |
|------|-----|
| `volume_mult` | 1.4 |
| `min_atr_threshold_points` | 20 |
| `hard_stop_atr_k` / `hard_stop_floor_pts` | 1.2 / 10 |
| `tp_atr_k` | 1.8 |
| `max_hold_sec` | 1200 |
| `vwap_slope_bars` | 3 |

**param key**：`rm{20|30}`（無 buffer 維度）。

**最佳組選取**：2025 train 內 **net/趟最高** 且 G1–G3 全過、§3.1 無 disqualify；平手取 **n 較大**。

## 8. Audit 與產物

| 產物 | 路徑 |
|------|------|
| CF train | `workspaces/scb-baseline/reports/counterfactual_scb_train.json` |
| CF valid | `workspaces/scb-baseline/reports/counterfactual_scb_valid.json` |
| Funnel | `workspaces/scb-baseline/reports/entry_funnel_scb.json` |
| ORB delta | `workspaces/scb-baseline/reports/scb_vs_orb_delta.json` |
| Gate report | `workspaces/scb-baseline/gate_report.md` |
| CLI | `apps/trading-app/src/scripts/ft011_scb_counterfactual.py` |

`SIGNAL_AUDIT reason=session_confluence_breakout`；欄位 MUST 含：`session_bucket`, `confluence_factors`（C1–C5 bool/bitset）, `atr`, `volume_ratio`, `opening_range_high`, `range_minutes`, `direction=long`。

**Funnel 階段**（[`ENTRY_FUNNEL_METRICS.md`](../ai-backtest-tuning/ENTRY_FUNNEL_METRICS.md) 對齊）：

`days` → `in_session_window` → `post_range` → `trend_ok`（C1+C2）→ `breakout_ok`（C3）→ `vol_ok`（C4+C5）→ `entry`

## 9. Definition of Done

### Phase 0

- [x] 本 SPEC + [`PLAN.md`](PLAN.md)
- [x] `scb_counterfactual.py` + `ft011_scb_counterfactual.py`
- [x] train + valid CF JSON + funnel + ORB delta + `gate_report.md`
- [ ] `strategy_diagnosis.md` §Decision 段

### Phase 1（train 過關後）

- [ ] `packages/strategies/session-confluence-breakout/` plugin
- [ ] `scb-baseline` config + baseline replay
- [ ] valid Q1 baseline JSON

### Phase 2（valid 過 + 人類 Go）

- [ ] holdout Q2 **一次** baseline（04–06）
- [ ] 更新 §10 §Decision

**UAT/Live**：全程 **維持** `strategy-vwap-momentum`，直至 FT-011 holdout 過關 + 人類書面同意。

## 10. §Decision — MVPClosed at Phase 0（2026-06-28）

| 欄位 | 值 |
|------|-----|
| Train（2025）主判 | **未過** — rm30 n=46 gross **+1.99** net **−3.01**；rm20 n=72 net **−4.61**；§3.1 disqualify（median 負） |
| Valid（2026 Q1） | rm30 n=31 gross **+33.47** net **+28.47**（**overfit_suspect** — train 未過） |
| ORB delta（train） | rm30：ORB 143 筆 net **−543.87** → SCB 46 筆 net **−138.51**（濾網減損但仍負） |
| 漏斗（train rm30） | breakout 59% → vol_ok 19% → entry 19% |
| 尾盤 bucket | **0 筆**（全為 morning） |
| 決策 | **MVPClosed at Phase 0**（`thesis_h_scb_no_go`） |
| Phase 0 方向 | **long-only** |
| UAT | **維持 vwap-momentum** |

產物 SSOT：[`workspaces/scb-baseline/gate_report.md`](../../../workspaces/scb-baseline/gate_report.md)。

## 參考

- PLAN：[`PLAN.md`](PLAN.md)
- Holdout v2.1：[`HOLDOUT_CONTRACT_v2.md`](../ai-backtest-tuning/HOLDOUT_CONTRACT_v2.md)
- FT-009 對照：[`opening-range-breakout/SPEC.md`](../opening-range-breakout/SPEC.md)
- FT-010 對照：[`vwap-trend-pullback/SPEC.md`](../vwap-trend-pullback/SPEC.md)
- 波動基線：[`VOLATILITY_BASELINE.md`](../../../workspaces/VOLATILITY_BASELINE.md)
- 診斷：[`strategy_diagnosis.md`](../../../workspaces/strategy_diagnosis.md)
