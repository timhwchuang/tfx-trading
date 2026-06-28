# FT-008 Gate Report — sb-baseline（Phase 0 v2 close_1h_only）

> **Variant**：`v2_close_1h_only` — 僅收盤前 1h（12:45–13:45）1m 突破順勢。

| 區間 | 產物 | Phase 0 |
|------|------|---------|
| Valid 2026-04-01～2026-04-30 | [`counterfactual_v2_close_1h_valid.json`](reports/counterfactual_v2_close_1h_valid.json) | **通過** |
| 01–04 2026-01-01～2026-04-30 | [`counterfactual_v2_close_1h_0104.json`](reports/counterfactual_v2_close_1h_0104.json) | **未過** |

## Valid — summary_by_param（atr_barrier_180s）

| param | n | gross/趟 | net/趟 |
|---|---|----------|--------|
| lb10_bk0 | 72 | 6.39 | 1.39 |
| lb10_bk0.1 | 67 | 7.24 | 2.24 |
| lb15_bk0 | 72 | 6.39 | 1.39 |
| lb15_bk0.1 | 67 | 7.24 | 2.24 |
| lb5_bk0 | 77 | 5.14 | 0.14 |
| lb5_bk0.1 | 73 | 5.51 | 0.51 |

### Best passing (valid)

- lb10_bk0.1: n=67 gross=7.24 net=2.24

## 01–04 — summary_by_param（atr_barrier_180s）

| param | n | gross/趟 | net/趟 |
|---|---|----------|--------|
| lb10_bk0 | 210 | 4.37 | -0.63 |
| lb10_bk0.1 | 198 | 4.4 | -0.6 |
| lb15_bk0 | 203 | 3.76 | -1.24 |
| lb15_bk0.1 | 191 | 3.57 | -1.43 |
| lb5_bk0 | 224 | 3.58 | -1.42 |
| lb5_bk0.1 | 213 | 3.4 | -1.6 |

### Best passing (01–04)

**無通過組。**

## v1 對照

| 版本 | valid 最佳 | 01–04 最佳 |
|------|-----------|------------|
| v1 全時段（子集） | close_1h lb10_bk0.1 gross +7.24 | close_1h gross +4.40 |
| **v2 close_1h_only** | 7.24 | — |

## §Decision

| 欄位 | 值 |
|------|-----|
| 決策 | **Hold** — valid 過、01–04 未過（overfit 風險）；不開 plugin |
| 日期 | 2026-06-28 |
