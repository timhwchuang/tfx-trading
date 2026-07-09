---
id: GATE-COVERAGE-PREFLIGHT
parent: ALPHA-PLAYBOOK
status: Active
opened: 2026-06-28
version: 1.0
---

# Gate Coverage Preflight — Alpha Phase 0-design（Methods SSOT）

> **定位**：FT-011+ **0-design** 專用 — 在 `human-approved` 與 Phase **0a** 之前，驗證每個 **核心 gate** 在 train 策略時段內**可觸發**且**隱含樣本數**合理。  
> **平行於**：[`ENTRY_FUNNEL_METRICS.md`](ENTRY_FUNNEL_METRICS.md)（Phase 3.6 §C · 已有策略診斷）— **不可混用**。  
> **資料 SSOT**：[`workspaces/VOLATILITY_BASELINE.md`](../../../workspaces/VOLATILITY_BASELINE.md) · `workspaces/reports/volatility_baseline.json`  
> **流程**：[`ALPHA_RESEARCH_PLAYBOOK.md`](ALPHA_RESEARCH_PLAYBOOK.md) v1.6 §2 Phase 0-design-3

---

## 1. 適用與禁止

| MUST | 說明 |
|------|------|
| **時點** | THESIS_BRIEF §E.4 填完 → **Preflight PASS** → `human-approved` → 0-design Senior PASS → 0a |
| **失敗處置** | **退回 SPEC/PLAN**（`design-revise`）或 **`design-closed`** — **禁止** 0a、`*_counterfactual.py`、0c-1 fingerprint |
| **與 fingerprint 無關** | 上游 gate=0 → **無進場樣本** → 不是 `*_fingerprint_fail_*`；不得用 fingerprint 語彙結案 |
| **0a 漏網** | 若 CF funnel 發現 upstream core gate=0 → **立即停止**；outcome=`spec_anchor_mismatch`；**禁止**跑 0c-1 |

**新案** upstream=0 → **`design-closed`**，**不得**標 `MVPClosed`（MVPClosed 僅限已產生樣本後的 train／fingerprint 管線）。  
**已跑完 CF 的歷史案**（如 FT-017）可保留 `MVPClosed` **事實**，但 canonical outcome = **`spec_anchor_mismatch`**。

---

## 2. 指標類型（SPEC MUST 標註）

| 類型 | 例 | 錨點注意 |
|------|-----|----------|
| `points_fixed` | `min_stop_pts=8` | 對照 §A `range_1m` / ATR ratio |
| `atr_multiple` | `compress_k × ATR` | 寫清 ATR 週期與 evaluation point |
| `range_aggregate` | 30×1m `maxHigh−minLow` | **≠** 單根 `range_1m`（見 VOLATILITY_BASELINE §E.2） |
| `vol_percentile` / `vol_floor` | session vol p50 | 對照 §B `vol_1s` 分布 |
| `price_level` | tick close | **禁止**當 range／compress 錨點 |

---

## 3. Baseline 欄位映射（常見）

| 設計意圖 | 正確錨點 | 常見誤讀 |
|----------|----------|----------|
| 單分鐘窄幅 | `range_1m.p50`（§A） | tick close 價位 |
| 30m 箱體 | 自算 **range_M** 或 sensitivity 表 | 用 `range_1m.p50`（量級差 ~5–10×） |
| 爆量進場 | `vol_1s` + `threshold_coverage`（§B.1） | 敘事「萬口」無分位 |
| ATR 停損尺度 | `ATR20.p50`（§A） | 固定 6pt 當全年尺度 |

---

## 4. 硬規則（BLOCK → 退回 SPEC/PLAN）

### 4.1 Bar 觸發率

在 **train 日曆**、**策略時段**（與 CF 一致，例 10:00–12:30 ET）內，對每個標記 **`core`** 的 MUST gate：

| 條件 | 處置 |
|------|------|
| `est_pass_rate_train` **&lt; 1%** 或 **&gt; 95%** | **BLOCK** — 不得 `human-approved` |
| 核心 gate A &lt;1% | 不得討論 gate B/C、不得宣稱 downstream「已驗證」 |

> **啟發式限制**：skew 低頻可能 bar 率 &gt;1% 仍無法過 G3S；故 **§4.2 隱含 n** 與 bar 率 **並列**。

### 4.2 隱含年進場數（MUST）

粗算：

`est_annual_n ≈ 交易日(247) × 核心_gate_通過率 × 下游轉化率（保守）`

| Thesis class | BLOCK 若 `est_annual_n` &lt; |
|--------------|------------------------------|
| **mean_robust** | **15**（G3=30 的一半） |
| **skew** | **8**（G3S=15 的一半） |

### 4.3 Outcome

| Outcome | 階段 | 下一步 |
|---------|------|--------|
| **`spec_anchor_mismatch`** | **0-design** | Revise SPEC/PLAN 或 `design-closed` |
| └ `compress_gate_unreachable` 等 | 備註／子類 | 同上 |
| `*_fingerprint_fail_*` | **0c-1 only** | 前提：**entry 路徑已產生樣本** |

---

## 5. est_pass_rate 估算方法（v1 · 不必等腳本）

CF 實作前 **MUST** 用下列之一（Senior 審 **數字**，非敘事）：

### 5.1 欄位引用法（vol / 固定門檻）

1. 讀 `workspaces/reports/volatility_baseline.json`（或跑 `ft003_volatility_baseline.py`）。
2. **vol 類**：用 `threshold_coverage.pct_samples_gte` — 語意同 [`volatility_baseline.py`](../../../apps/trading-app/src/reporting/volatility_baseline.py) `build_threshold_coverage` / `threshold_pct_gte`。
3. **ATR／range 比**：用 §A 月表 `range_1m`、`ATR20` 粗算門檻在分布中的位置；**禁止**只用 narrative「~12pt」。

### 5.2 range_aggregate 類（30m range_M 等）

baseline **無現成欄位**時：

1. preflight 表 **MUST** 填「手算來源」（spreadsheet / 抽樣日 / 與 FT-017 同型 sensitivity 表）。
2. 列出：`min` / `p50` / `p90` of `range_M/ATR` vs 門檻 `compress_k`。
3. Senior **MUST** 對照數字簽核 — 空白或「應該夠」= **BLOCK**。

### 5.3 下游轉化率

保守預設（無同族實績時）：每多一層獨立 gate × **0.3–0.7**（取決於 gate 相關性；相關性高取高、互斥取低）。  
有同族 funnel 時：引用最近 MVPClosed `gate_report` funnel 比例。

---

## 6. THESIS_BRIEF §E.4 表模板

| gate_id | metric_def | baseline_column | threshold | est_pass_rate_train | est_annual_n | core? | verdict |
|---------|------------|-----------------|-----------|---------------------|--------------|-------|---------|
| MUST-1 | 例：30m range_M ≤ k×ATR | 手算 range_M/ATR | k=0.45 | ___% | ___ | Y | PASS/BLOCK |
| MUST-2 | … | … | … | … | … | Y/N | … |

**verdict=BLOCK** 任一列 core gate → 整案 **不得** `human-approved`。

---

## 7. 附錄 A — FT-017 canonical case

> 詳述：[`cfa-baseline/gate_report.md`](../../../workspaces/cfa-baseline/gate_report.md) §驗屍 · [`CORPSE_ATLAS.md`](../../../workspaces/CORPSE_ATLAS.md) §FT-017

| 項目 | 值 |
|------|-----|
| **canonical outcome** | **`spec_anchor_mismatch`**（0-design） |
| **舊標 mislabel** | `cfa_fingerprint_fail` — **非** fingerprint 失敗 |
| funnel | session=241 → compress=**0** → … → attack=236 → entry=**0** |
| 10:00–12:30 compress bars | **0 / 36,391** |
| range_M/ATR p50 | **5.32** vs 設計隱含 **~0.45** |
| 單根 1m range p50（同窗） | **9.0 pt**（錯誤敘事錨點 ~12pt 單根） |
| `compress_k` sensitivity | 0.35–0.55 → **0 bar**；~2.0 → ~0.3% bar（診斷 only · **禁止** rescue） |

**教訓**：沒樣本不是方向錯，是規格從一開始就進不了場 — **要在寫 CF 之前擋下**。

---

## 8. 參考

- Playbook：[`ALPHA_RESEARCH_PLAYBOOK.md`](ALPHA_RESEARCH_PLAYBOOK.md) v1.6
- Brief 模板：[`THESIS_BRIEF.md`](../_template/THESIS_BRIEF.md) §E.1.1 · §E.4
- 資深審查：[`senior-trading-professional.md`](../../../prompts/roles/senior-trading-professional.md) Alpha 0-design
- Phase 2 工具（defer）：`gate_coverage_preflight.py` — FT-018 前可選實作
