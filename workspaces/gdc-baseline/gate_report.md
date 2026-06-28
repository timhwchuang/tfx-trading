# FT-016 Gate Report — gdc-baseline（Phase 0 · skew）

> **Thesis P-005**：Gap drive continuation — gap>k×ATR · drive retrace · break 極值。
> **Entry**：tick break post-09:45 · **雙向** · friction **5**。
> **Exit**：`atr_barrier_900s` · G3S **n≥15**。

## Phase 0-design

| 項目 | 結果 |
|------|------|
| 資深 TXF P0 封印 | PASS（2026-06-28） |

## Phase 0b — Code review

| MUST | 結果 |
|------|------|
| MUST-1 / §5.1a gap · drive · retrace | PASS（agent 2026-06-28） |
| MUST-2 摩擦 5 · slippage 診斷 | PASS |
| MUST-3 funnel · break≠entry | PASS |
| MUST-4 post_entry · skew 附錄 | PASS |

## Grid (0c-2)

- `gk1_rt0p3_ksl0p75_tp1p5`: n=68 gross=0.41 net=-4.59
- `gk1_rt0p3_ksl0p75_tp2`: n=68 gross=1.92 net=-3.08
- `gk1_rt0p3_ksl0p75_tp2p5`: n=68 gross=1.52 net=-3.48
- `gk1_rt0p3_ksl1_tp1p5`: n=68 gross=-0.48 net=-5.48
- `gk1_rt0p3_ksl1_tp2`: n=68 gross=1.03 net=-3.97
- `gk1_rt0p3_ksl1_tp2p5`: n=68 gross=0.63 net=-4.37
- `gk1_rt0p3_ksl1p25_tp1p5`: n=68 gross=-0.94 net=-5.94
- `gk1_rt0p3_ksl1p25_tp2`: n=68 gross=0.56 net=-4.44
- `gk1_rt0p3_ksl1p25_tp2p5`: n=68 gross=0.17 net=-4.83
- `gk1_rt0p4_ksl0p75_tp1p5`: n=79 gross=2.52 net=-2.48
- `gk1_rt0p4_ksl0p75_tp2`: n=79 gross=4.3 net=-0.7
- `gk1_rt0p4_ksl0p75_tp2p5`: n=79 gross=3.6 net=-1.4
- `gk1_rt0p4_ksl1_tp1p5`: n=79 gross=1.51 net=-3.49
- `gk1_rt0p4_ksl1_tp2`: n=79 gross=3.29 net=-1.71
- `gk1_rt0p4_ksl1_tp2p5`: n=79 gross=2.6 net=-2.4
- `gk1_rt0p4_ksl1p25_tp1p5`: n=79 gross=1.96 net=-3.04
- `gk1_rt0p4_ksl1p25_tp2`: n=79 gross=3.75 net=-1.25
- `gk1_rt0p4_ksl1p25_tp2p5`: n=79 gross=3.05 net=-1.95
- `gk1p5_rt0p3_ksl0p75_tp1p5`: n=66 gross=0.14 net=-4.86
- `gk1p5_rt0p3_ksl0p75_tp2`: n=66 gross=1.5 net=-3.5
- `gk1p5_rt0p3_ksl0p75_tp2p5`: n=66 gross=1.5 net=-3.5
- `gk1p5_rt0p3_ksl1_tp1p5`: n=66 gross=-0.83 net=-5.83
- `gk1p5_rt0p3_ksl1_tp2`: n=66 gross=0.53 net=-4.47
- `gk1p5_rt0p3_ksl1_tp2p5`: n=66 gross=0.53 net=-4.47
- `gk1p5_rt0p3_ksl1p25_tp1p5`: n=66 gross=-1.31 net=-6.31
- `gk1p5_rt0p3_ksl1p25_tp2`: n=66 gross=0.05 net=-4.95
- `gk1p5_rt0p3_ksl1p25_tp2p5`: n=66 gross=0.05 net=-4.95
- `gk1p5_rt0p4_ksl0p75_tp1p5`: n=77 gross=2.34 net=-2.66
- `gk1p5_rt0p4_ksl0p75_tp2`: n=77 gross=4.0 net=-1.0
- `gk1p5_rt0p4_ksl0p75_tp2p5`: n=77 gross=3.64 net=-1.36
- `gk1p5_rt0p4_ksl1_tp1p5`: n=77 gross=1.26 net=-3.74
- `gk1p5_rt0p4_ksl1_tp2`: n=77 gross=2.93 net=-2.07
- `gk1p5_rt0p4_ksl1_tp2p5`: n=77 gross=2.56 net=-2.44
- `gk1p5_rt0p4_ksl1p25_tp1p5`: n=77 gross=1.72 net=-3.28
- `gk1p5_rt0p4_ksl1p25_tp2`: n=77 gross=3.39 net=-1.61
- `gk1p5_rt0p4_ksl1p25_tp2p5`: n=77 gross=3.02 net=-1.98

**best_passing**: None

## Valid 2026 Q1（參考 · skew 硬擋）

- n=15 · gross/趟=-4.28 · net/趟=-9.28
- **holdout_blocked_overfit** — valid net≤0 禁 holdout（HOLDOUT v2.2.1 §4）

## §Decision

| 欄位 | 值 |
|------|-----|
| 決策 | **MVPClosed** — `gdc_fingerprint_pass_g1_fail` |
| outcome | `gdc_fingerprint_pass_g1_fail` |
| thesis_class | **skew** |
| UAT | **維持** `strategy-vwap-momentum` |
| 日期 | 2026-06-28 |
