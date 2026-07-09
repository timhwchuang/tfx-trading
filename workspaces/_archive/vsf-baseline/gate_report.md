# FT-006 Gate Report — vsf-baseline

> **策略**：`vwap_stretch_fade`（VWAP Stretch Fade · Thesis C）  
> **狀態**：**MVPClosed** — legacy v2.0 valid 過 / holdout 未過；**v2.1 train 2025 未過**（`thesis_c_v21_train_no_go`）  
> **Holdout 契約**：legacy [`HOLDOUT_CONTRACT_v2.md`](../../docs/features/ai-backtest-tuning/HOLDOUT_CONTRACT_v2.md) §2.0 · v2.1 複驗 2026-06-28  
> **Config**：[`config/config.yaml`](config/config.yaml)（`stretch_k=2.0`）  
> **產物**：legacy CF [`counterfactual_vwap_stretch_fade.json`](reports/counterfactual_vwap_stretch_fade.json)（**僅 2026-04**，非 v2.1 train）· v2.1 [`counterfactual_v2.1_train2025.json`](reports/counterfactual_v2.1_train2025.json) · [`baseline_valid.json`](reports/baseline_valid.json) · [`baseline_holdout.json`](reports/baseline_holdout.json)

---

## Phase 0 預檢 — legacy（counterfactual · 2026-04 only · atr_barrier_180s）

> **方法論警示**：此窗在 v2.0 為 **valid 月**，非 v2.1 train；結論僅作歷史紀錄。

| 指標 | 門檻 | 值 | Pass |
|------|------|-----|------|
| 最佳組合 | k×bucket | **2.0 × mid** | — |
| gross expectancy/趟 | > 5 | **7.13**（CF n=48） | ☑ |
| net expectancy/趟 | > 0 | **2.13** | ☑ |
| gross_median | §3.1 | **−18.75** | ⚠ 厚尾 |

**Legacy Phase 0**：當日 **通過** → 已開 plugin（現 **凍結**）。

---

## G1 — 毛 edge（plugin baseline）

| 指標 | 值 | Pass |
|------|-----|------|
| gross expectancy/趟 | 5.43 | ☑ |
| trade_count（valid 月） | 82 | |

## G2 — 淨 edge（摩擦 5 點/趟）

| 指標 | 值 | Pass |
|------|-----|------|
| net expectancy/趟 | 0.43 | ☑ |

## G3 — 頻率（< 100 趟/月）

| 指標 | 值 | Pass |
|------|-----|------|
| trade_count | 82 | ☑ |

## G4 — QSL（< 25%）

| 指標 | 值 | Pass |
|------|-----|------|
| quick_stop_loss_rate | 6.1% | ☑ |

---

## 對照

| 策略 | thesis | 備註 |
|------|--------|------|
| v1 hybrid | 回踩順勢 | FT-003 No-Go |
| FT-004 | armed 即時 | No-Go |
| FT-005 | timeout 進場 | Phase 0 No-Go |
| **FT-006** | **VWAP fade** | 本輪 |

---

## Holdout 2026-05（封印解封 · plugin baseline）

| 指標 | 門檻 | 值 | Pass |
|------|------|-----|------|
| gross expectancy/趟 | > 5 | **4.26** | ☐ |
| net expectancy/趟 | > 0 | **-0.74** | ☐ |
| trade_count | < 100/月 | **123** | ☐ |
| quick_stop_loss_rate | < 25% | **8.9%** | ☑ |

**Holdout**：**未過**（overfit suspect 或 edge 消失） · 產物：[`reports/baseline_holdout.json`](reports/baseline_holdout.json)

---

## v2.1 複驗 — Train 2025（counterfactual · atr_barrier_180s）

> **區間**：2025-01-01～2025-12-31（247 日）· 詳 [`gate_report_v2.1_train2025.md`](gate_report_v2.1_train2025.md)  
> **產物**：[`reports/counterfactual_v2.1_train2025.json`](reports/counterfactual_v2.1_train2025.json)

| k | n | gross/趟 | net/趟 | gross_median | v2.1 G1–G2 |
|---|-----|----------|--------|--------------|------------|
| 1.5 | 902 | +1.44 | **−3.56** | −7.0 | ☐ |
| **2.0**（凍結） | 268 | **−0.65** | **−5.65** | −18.75 | ☐ |
| 2.5 | 105 | +6.55 | +1.55 | **−18.75** | ☐ §3.1 |

**phase0_pass**：**False** — 無任一 k×bucket 通過 G1+G2+n≥30。

**k=2.0×mid**（legacy 冠軍組，全年）：n=96 gross **−1.07** net **−6.07**。

---

## v2.1 對照 — Valid 2026 Q1（k=2.0 凍結 · 診斷 only）

> **產物**：[`reports/counterfactual_v2.1_valid2026q1_k20.json`](reports/counterfactual_v2.1_valid2026q1_k20.json)

| n | gross/趟 | net/趟 |
|---|----------|--------|
| 298 | **−0.35** | **−5.35** |

train 未過 + valid net 負 → 不具 holdout 資格。

---

## §Decision

| 欄位 | 值 |
|------|-----|
| 簽核人 | Tim（對話 + v2.1 複驗） |
| 日期 | 2026-06-28（legacy）；**2026-06-28（v2.1 複驗）** |
| 決策 | **MVPClosed** — `thesis_c_v21_train_no_go`；legacy holdout 亦未過 |
| Legacy Phase 0 CF | 2026-04 only；k=2.0×mid gross **+7.13**、net **+2.13**（n=48）；**非** v2.1 train |
| Plugin baseline | valid 82 趟 gross **+5.43**；holdout 123 趟 gross **+4.26**、net **−0.74** |
| **v2.1 train 2025** | k=2.0 net **−5.65**；k=2.5 mean 正但 median **−18.75** → disqualify |
| **v2.1 valid Q1** | k=2.0 net **−5.35**（overfit / edge 不存在） |
| UAT/Live | **維持** `strategy-vwap-momentum` **smoke**；plugin **凍結** |
| 下一輪 | **P-001** regime fade 或新 thesis（FT-012+）；**不**復活 FT-006 參數 sweep |
