# FT-008 Gate Report — sb-baseline（Phase 0）

> **狀態：MVPClosed / No-Go at Phase 0** — 見 [`SPEC`](../../docs/features/short-breakout/SPEC.md)。

**區間**：2026-01-01 ～ 2026-04-30
**產物**：[`reports/counterfactual_short_breakout.json`](reports/counterfactual_short_breakout.json)

## Phase 0 預檢

| 通過 | False |
| gross_mean 門檻 | > 5.0 |
| net_mean 門檻 | > 0.0 |
| min_n | 30 |

**FT-004 對照**（armed 全進 valid）：gross ~ **1.89**/趟（G1 未過）

**無任一組通過 Phase 0 門檻。**

## summary_by_param（atr_barrier_180s）

| param | n | gross/趟 | net/趟 |
|---|---|----------|--------|
| lb10_bk0 | 1736 | 1.35 | -3.65 |
| lb10_bk0.1 | 1563 | 1.38 | -3.62 |
| lb15_bk0 | 1482 | 1.13 | -3.87 |
| lb15_bk0.1 | 1332 | 1.24 | -3.76 |
| lb5_bk0 | 2136 | 1.25 | -3.75 |
| lb5_bk0.1 | 1951 | 1.21 | -3.79 |

## summary_by_param（fixed_scalp_120s）

| param | n | gross/趟 | net/趟 |
|---|---|----------|--------|
| lb10_bk0 | 1736 | 0.97 | -4.03 |
| lb10_bk0.1 | 1563 | 1.02 | -3.98 |
| lb15_bk0 | 1482 | 0.94 | -4.06 |
| lb15_bk0.1 | 1332 | 1.06 | -3.94 |
| lb5_bk0 | 2136 | 0.83 | -4.17 |
| lb5_bk0.1 | 1951 | 0.82 | -4.18 |

## §Decision

| 欄位 | 值 |
|------|-----|
| 決策 | **No-Go at Phase 0** (`thesis_e_phase0_no_go`) |
| 日期 | 2026-06-28 |
