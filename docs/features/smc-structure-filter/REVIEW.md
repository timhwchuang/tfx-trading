---
id: FT-002
slug: smc-structure-filter
reviewer: senior-trading-professional
reviewed: 2026-06-18
spec_version: 2
verdict: PASS_WITH_NOTES
---

# FT-002 SMC Structure Filter — 資深交易人員 Re-Review

> 審閱對象：[`SPEC.md`](SPEC.md) v2（精煉後）、[`PLAN.md`](PLAN.md) v2。  
> 角色：[`prompts/roles/senior-trading-professional.md`](../../../prompts/roles/senior-trading-professional.md)  
> Gate 參照：[`txf-gates.md`](../../../prompts/roles/references/txf-gates.md)、[`uat/APP.md`](../../uat/APP.md) Phase 5

**情境**：策略研究 / ft 設計審閱（非 Pilot Go/No-Go、非 Live）。

---

## 1. 關鍵分析

### 對前一版 review 的回應 — 是否到位？

| 前一版疑慮 | v2 狀態 | 判定 |
|------------|---------|------|
| FVG「完全回填」未定義 | §4.7 寫死 `low<=fvg_low AND high>=fvg_high`；partial touch 明確排除 | **PASS** |
| swing pivot lag | §4.5 確認 lag = L 根 5m | **PASS** |
| active_fvg 多個取誰 | §4.7 同向 + 最新未 mitigated | **PASS** |
| range session 邊界 | §4.3 08:45 起算 + 夜盤排除 + `used_long_lookback` 剝離 | **PASS** |
| structure_stale 未規範 | §6.3 RiskGate + 策略對稱 atr_stale | **PASS** |
| no-lookahead | §4.2 1m/5m 雙層已收盤 | **PASS** |
| sweep 互斥只寫 app | §5.2 三處 + §5.3 SWEEP 映射 | **PASS** |
| Land 文件漂移 | §9 強制三份 package SPEC | **PASS** |
| UAT vs Pilot 混淆 | §8.2 兩層 gate 表 | **PASS** |
| harness armed 重算 | PLAN Phase 2 `as_of_ts` 重算 | **PASS** |
| min_strength 誤解 | §1 + §4.10 雙重警告 | **PASS** |

### 交易視角總評

v2 把「discretionary SMC 畫線」壓成 **可測、可版本化的 v0.1**，方向正確。仍須記住：

- 這仍是 **日內 5m 結構 proxy**，不是 order-flow 聖杯
- swing 確認 lag（預設 2 根 5m = 10 分鐘）會讓濾網 **慢於** tick 爆量；這是設計取捨，不是 bug — harness 要看 veto 是否擋掉「慢半拍仍賺」的單
- `bias==Neutral` 放行（permissive）保留微結構哲學，但代表 **結構濾網在 choppy 日可能幾乎不 veto** — CAL-8 要看 veto_rate 是否過低而無統計力

**結論**：文件已達 **可開 Phase 1 實作** 水準。

---

## 2. 風險評估（含模型、執行、制度）

### 模型風險（仍須 harness 驗證）

- **Regime-specific**：低波日 `eff = |px-range_mid|/atr` 可能長期 Neutral → 濾網形同虛設；高波日 veto 可能過猛。三組 counterfactual 必做。
- **FVG 在 TXF 假突破日**：mitigation 定義清楚，但 **假 FVG** 仍會產生；near-miss 審閱不可省。
- **與 trend 重疊**：structure 與 trend 可能高度相關；若 delta 只比 trend 好 0.05 expectancy，**不值得**多一層複雜度 — CAL-8 要寫明「相對 trend 的增量」。

### 執行風險

- `structure_stale` 與 `atr_stale` 共用 refresh 週期 — kbars 掛了兩個都算不出，會 **雙重擋 entry**；合理，但 Ops 要認得 log 裡兩種 `risk_blocked`。
- backtest 無 order book：harness 的 friction-adjusted 報表 **不能**當 Pilot 唯一依據。

### 制度風險

- §8.2 寫對了：**CAL-8 Go ≠ Pilot Ready**。勿在週報寫「SMC 過了可以 Pilot」。
- 互斥 fail-fast 正確；sweep grid 若有人手改 jsonl 繞過，仍是人為風險 — 接受。

---

## 3. 建議行動或設計考量

### Phase 1 前 — 無需再改 SPEC（可選小補）

1. **實作時**在 `structure_veto` audit 加 `structure_as_of_bar_ts`（SPEC SHOULD 已涵蓋概念）— 方便 near-miss 對照「濾網用的是哪根 5m」。
2. harness 報表固定輸出一列：**structure veto_rate vs trend veto_rate** 同區間對照。
3. Phase 2 決策閘維持：**無正 delta → 不進 Phase 3** — 不要因工程動能硬推。

### 交易校準（CAL-8 時我會看）

- 三組 friction-adjusted expectancy 表
- structure only 相對 trend only 的 **增量** Δexpectancy（多日穩定）
- veto_rate 落在 15–45% 較健康；<5% 或 >70% 直接 No-Go
- ≥3 near-miss：veto 後 30m 價格走勢（是否真擋掉好單）

---

## 4. 協作備註

| 角色 | Re-review 後動作 |
|------|------------------|
| **Daily Reviewer** | Phase 2 報表模板進 WeeklyStatus；CAL-8 簽名欄 |
| **永豐 API Specialist** | 驗證 §4.2 closed bar 與 API ts 對齊；模擬 vs 實盤 kbar 差異清單 |
| **Ops** | UAT 強制 `KBARS_ARCHIVE=1`；structure_stale 演練腳本併入 Phase 4 UAT |
| **工程** | Phase 3 完成時 **同 PR** 更新 engine SPEC，避免漂移 |

---

## 5. 免責與人類決策權

本審閱為 **ft 設計 PASS（附註）**，不代表 SMC 有統計優勢、不代表可開 `structure_filter_enabled`、不代表 Pilot/Live 核准。

**Verdict：`PASS_WITH_NOTES`** — 可進入 Phase 1 實作；統計優勢須等 Phase 2 harness + CAL-8。

---

## Phase 5 對照（交易視角 — 若日後 structure 參與 Pilot）

> 僅在 CAL-8 Go **且** 人類決定將 structure 納入 Pilot 策略時適用；**現階段不適用**。

- [ ] 樣本量（20 日 + 80 筆 + 最近 10 日 35 筆）
- [ ] Expectancy gross + net / Sharpe / MDD
- [ ] Tick 分層（type0_pct × conversion）
- [ ] structure_veto near-miss ≥3 + 前 5 大虧損日親閱
- [ ] 零 Critical（10 日）
- [ ] determinism + 真實 tick/kbar audit 比對
→ 結論：屆時另開 Pilot 審查，**不與 CAL-8 混為一談**

---

## Phase 1 實作 Re-Review（2026-06-18）

**範圍**：`structure.py` + `test_structure.py`（零 kernel 改動）

### 初審（code review）→ 修正 → 複審

| 初審 issue | 共識 | 處置 |
|------------|------|------|
| HIGH §4.10 `eff==0` 未 Neutral | **同意** | `min_strength==0` 時要求 `eff > 0` |
| MEDIUM level2 測試未覆蓋 | **同意** | 重寫 fixture + 斷言 BOS + mid/offset |
| MEDIUM FVG 未走 `compute_structure` | **同意** | 新增 e2e 測試 |
| MEDIUM gap 測試缺 BOS 斷言 | **同意** | `assert last_bos is None` |
| MEDIUM `used_long_lookback` 死分支 | **同意**（保留參數、單一路徑 + 註解 Phase 3） | 已簡化 |
| LOW BOS timing 測試弱 | **同意** | 嚴格 `bos_ts > confirm_ts` |
| LOW 夜盤污染 | **同意** | 新增 `test_night_session_bar_excluded` |
| LOW `atr=0` 行為 | **同意**（SPEC 允許跳過 Level-2） | 新增測試 |

**不採納**：無（初審 HIGH/MEDIUM 全數同意修正）

### 驗收

- `python3 run_tests.py`（vwap-momentum）：**55 passed**
- `bash scripts/run-all-tests.sh`：**全綠**
- runtime 行為：**未改**（filter 未接線）

**Phase 1 Verdict：`PASS`** — 可進 Phase 2 harness。

---

## Phase 2 實作 Re-Review（2026-06-18）

**範圍**：`structure_calibration.py` + `structure_calibration_cli.py` + A/B-class tests（零 runtime 改動）

### 初審 → 修正 → 複審

| 初審 issue | 共識 | 處置 |
|------------|------|------|
| MEDIUM trend 未對齊 live `select_recent_trading_days_closes` | **同意** | `_closes_for_trend` 改用 calendar helper |
| MEDIUM `atr or 1.0` 扭曲 Level-2 | **同意** | 傳入真實 `cand.atr`（含 0） |
| MEDIUM `phase3_gate` 僅看 structure delta | **同意** | 改為 structure net > 0 **且** 增量 vs trend |
| LOW CLI 未入 `cli_help` / SPEC | **同意** | 已註冊 |
| LOW 未使用 `trend_cfg` 參數 | **同意** | 自 `counterfactual_regime_allows` 移除 |

**不採納**：無

### 驗收

- `bash scripts/run-all-tests.sh`：**全綠**
- harness 輸出：`structure_events.csv`、`structure_armed_join.csv`（+ 三組 scenario join）
- 三組 counterfactual + friction-adjusted net expectancy：**已實作**
- ≥5 日 UAT 重現：**待累積**（不擋 Phase 2 land）

**Phase 2 Verdict：`PASS`** — harness 就緒；統計 Go/No-Go 待 B-class UAT 累積 + CAL-8。

---

## Phase 3 實作 Re-Review（2026-06-18）

**範圍**：A1–A8（`StructureRefreshPort`、`structure_stale`、config 互斥、`param_sweep` structure grid、`structure_calibration_cli --sweep`、文件更新）

### 初審 → 修正 → 複審

| 初審 issue | 共識 | 處置 |
|------------|------|------|
| HIGH `param_sweep` structure harness **覆寫** `veto_metrics`（trend） | **同意** | 獨立 `structure_veto_metrics` key；trend 仍寫 `veto_metrics` |
| MEDIUM regime 互斥 combo **靜默 skip** | **同意** | `logger.warning("skip mutually exclusive regime combo")` |
| MEDIUM `structure_refresh` 匯入 private `_kbars_raw_to_records` | **同意** | 公開 `kbars_raw_to_records`；`kbar_archiver` 同步改用 |
| MEDIUM `exchange_dt=None` 時 fallback `datetime.now()` | **同意** | 優先 `bars[-1].ts + 1min`，最後才 `now()` |
| MEDIUM 缺 `structure_stale` **允許 exit** 測試 | **同意** | `test_structure_stale_allows_exit_when_position_open` |
| LOW engine/package SPEC §9 未更新 | **延後** | 依 SPEC §9 留 Phase 5 Land 同 PR 更新 |

**不採納**：無

### 驗收

- `bash scripts/run-all-tests.sh`：**全綠**
- `structure_filter_enabled` 預設 **false** — runtime 行為與 Phase 2 等價
- `param_sweep` structure grid 輸出 `structure_veto_metrics`（不污染 trend `veto_metrics`）
- Phase 4 待辦維持：`regime_allows_entry`、`structure_veto` audit、armed enrichment

**Phase 3 Verdict：`PASS`** — 可進 Phase 4 策略接線 + UAT；CAL-8 仍待 ≥5 日 UAT 累積。