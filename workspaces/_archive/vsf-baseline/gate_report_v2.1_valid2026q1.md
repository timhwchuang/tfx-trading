# FT-006 Gate Report — vsf-baseline（Phase 0）

> **狀態：MVPClosed / No-Go at Phase 0** — 見 [`SPEC §8`](../../docs/features/vwap-stretch-fade/SPEC.md)。

**Valid**：2026-01-01 ～ 2026-03-31
**產物**：[`reports/counterfactual_vwap_stretch_fade.json`](reports/counterfactual_vwap_stretch_fade.json)

## Phase 0 預檢

| 通過 | False |
| gross_mean 門檻 | > 5.0 |
| net_mean 門檻 | > 0.0 |
| min_n | 30 |

**無任一組通過 Phase 0 門檻。**

## summary_by_k（atr_barrier_180s）

| k | n | gross/趟 | net/趟 |
|---|---|----------|--------|
| 2.0 | 298 | -0.35 | -5.35 |

## §Decision

| 欄位 | 值 |
|------|-----|
| 決策 | **No-Go at Phase 0** (`thesis_c_phase0_no_go`) |
| 日期 | 2026-06-28 |
