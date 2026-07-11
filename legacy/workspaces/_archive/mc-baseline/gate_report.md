# FT-004 Gate Report — mc-baseline

> **狀態：MVPClosed / No-Go（2026-06-28）** — 本回合結束；見 [`SPEC §8`](../../docs/features/momentum-continuation/SPEC.md)。

**策略**：`momentum_continuation`（Armed Forward Entry）  
**Valid 區間**：2026-04-01 ～ 2026-04-30  
**Config**：[`config/config.yaml`](config/config.yaml)  
**產物**：[`reports/baseline_valid.json`](reports/baseline_valid.json) · [`reports/counterfactual_armed_forward.json`](reports/counterfactual_armed_forward.json) · [`reports/arm_threshold_probe.json`](reports/arm_threshold_probe.json) · [`reports/adverse_guard_probe.json`](reports/adverse_guard_probe.json)

> 門檻定義：[`docs/features/momentum-continuation/SPEC.md`](../../docs/features/momentum-continuation/SPEC.md) §6

---

## G1 — 毛 edge（gross expectancy/趟 > 5）

| 指標 | 值 | Pass |
|------|-----|------|
| gross expectancy/趟 | 1.89 | ☐ |
| trade_count（valid 月） | 187 | |

## G2 — 淨 edge（net > 0，摩擦 5 點/趟）

| 指標 | 值 | Pass |
|------|-----|------|
| net expectancy/趟 | -3.11 | ☐ |

## G3 — 頻率（< 100 趟/月 vs v1 ~150）

| 指標 | 值 | Pass |
|------|-----|------|
| trade_count | 187 | ☐ |

## G4 — QSL（< 25%）

| 指標 | 值 | Pass |
|------|-----|------|
| quick_stop_loss_rate | 1.6% | ☑ |

---

## Arm tune 歷程（No-Go）

| Round | 變更 | Plugin gross | Plugin net | 趟數 |
|-------|------|--------------|------------|------|
| v0 | vol 150 | -0.02 | -5.02 | 201 |
| r1 | vol **165** | +1.39 | -3.61 | 194 |
| r1b | buy **0.85** | **+1.89** | **-3.11** | **187** |
| **r2 §b** | `max_adverse_atr_k` **0.25** | +1.89 | -3.11 | 187 |

**§b 實作**：`adverse_guard.py` — Long 若 `price < vwap - k×ATR` 則 skip（防假 spike）。Probe（k=0～1）僅濾 1 筆 CF episode；**plugin baseline 與 r1b 相同** → §b 對 4 月樣本幾乎無效。

**現行 config**：r1b + `max_adverse_atr_k: 0.25`（已接線，供後續月驗證）。

---

## v1 對照

| 指標 | v1 hybrid | **FT-004 r2** |
|------|-----------|---------------|
| trade_count | 150 | 187 |
| gross exp/趟 | -0.32 | **+1.89** |
| net exp/趟 | -5.32 | **-3.11** |
| QSL rate | 33.3% | 1.6% |

---

## §Decision

| 欄位 | 值 |
|------|-----|
| 簽核人 | Tim |
| 日期 | 2026-06-28 |
| 決策 | **No-Go — 本回合結束（MVPClosed）** |
| 備註 | Thesis A 全進場不可行。Plugin 凍結；證據留 `mc-baseline/`。見 [`SPEC §8`](../../docs/features/momentum-continuation/SPEC.md)。下一 thesis：timeout-selective（未開 ft）。 |
