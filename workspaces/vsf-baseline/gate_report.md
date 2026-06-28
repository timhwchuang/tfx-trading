# FT-006 Gate Report — vsf-baseline

> **策略**：`vwap_stretch_fade`（VWAP Stretch Fade · Thesis C）  
> **Valid 區間**：2026-04-01 ～ 2026-04-30  
> **Config**：[`config/config.yaml`](config/config.yaml)（`stretch_k=2.0`）  
> **產物**：[`reports/counterfactual_vwap_stretch_fade.json`](reports/counterfactual_vwap_stretch_fade.json) · [`reports/baseline_valid.json`](reports/baseline_valid.json) · [`reports/baseline_holdout.json`](reports/baseline_holdout.json)

---

## Phase 0 預檢（counterfactual · atr_barrier_180s）

| 指標 | 門檻 | 值 | Pass |
|------|------|-----|------|
| 最佳組合 | k×bucket | **2.0 × mid** | — |
| gross expectancy/趟 | > 5 | **7.13**（CF n=48） | ☑ |
| net expectancy/趟 | > 0 | **2.13** | ☑ |

**Phase 0**：**通過** → 開 plugin + baseline。

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

## §Decision

| 欄位 | 值 |
|------|-----|
| 簽核人 | TBD（人類） |
| 日期 | 2026-06-28 |
| 決策 | **Holdout 未過** — 維持 Pilot-prep 凍結；勿 sweep on valid、勿切 UAT |
| Phase 0 CF | k=2.0×mid gross **+7.13**、net **+2.13**（n=48） |
| Plugin baseline | valid 82 趟 gross **+5.43**；holdout 123 趟 gross **+4.26**、net **-0.74** |
| 備註 | valid 過 G1–G4 但 net 薄；**holdout 2026-05 未過**（gross +4.26、net −0.74、123 趟）→ overfit suspect；勿 sweep on valid、勿切 UAT |
