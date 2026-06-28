# FT-012 Gate Report — rvsf-baseline（Phase 0）

> **Code review**：PASS 2026-06-28 Bugbot RV lookahead fix
> **Thesis I**：Regime VWAP Stretch Fade — P-001 GO。
> **主判**：**2025 train**（Holdout v2.1）· 2026 Q1 valid 診斷。

| 區間 | 產物 | Phase 0 |
|------|------|---------|
| **Train** 2025-01-01～2025-12-31 | [`counterfactual_rvsf_train.json`](reports/counterfactual_rvsf_train.json) | **未過** |
| Valid 2026-01-01～2026-03-31 | [`counterfactual_rvsf_valid.json`](reports/counterfactual_rvsf_valid.json) | 未過（診斷） |

## Train — summary_by_param

| param | n | gross/趟 | net/趟 | gross_median | QSL | disqualify |
|---|---|----------|--------|--------------|-----|------------|
| k2_p25 | 110 | 0.48 | -4.52 | -7.42 | 0.0 | gross_median_le_neg5,Long_gross_share_gt_80pct,Short_net_mean_lt_neg3 |
| k2_p30 | 133 | 0.75 | -4.25 | -7.31 | 0.0 | gross_median_le_neg5,Long_gross_share_gt_80pct,Short_net_mean_lt_neg3 |
| k2_p35 | 143 | 0.78 | -4.22 | -7.31 | 0.0 | gross_median_le_neg5,Long_gross_share_gt_80pct,Short_net_mean_lt_neg3 |
| k2p5_p25 | 29 | 0.37 | -4.63 | -7.54 | 0.0 | gross_median_le_neg5,Short_gross_share_gt_80pct,Short_net_mean_lt_neg3,Long_net_mean_lt_neg3 |
| k2p5_p30 | 37 | 1.53 | -3.47 | -7.31 | 0.0 | gross_median_le_neg5,Short_gross_share_gt_80pct,Long_net_mean_lt_neg3 |
| k2p5_p35 | 40 | 0.94 | -4.06 | -7.42 | 0.0 | gross_median_le_neg5,Short_gross_share_gt_80pct,Long_net_mean_lt_neg3 |
| k3_p25 | 7 | -2.05 | -7.05 | -8.02 | 0.0 | gross_median_le_neg5,Short_net_mean_lt_neg3,Long_net_mean_lt_neg3 |
| k3_p30 | 9 | 1.49 | -3.51 | -8.02 | 0.0 | gross_median_le_neg5,Long_gross_share_gt_80pct,Short_net_mean_lt_neg3 |
| k3_p35 | 10 | 0.3 | -4.7 | -8.41 | 0.0 | gross_median_le_neg5,Long_gross_share_gt_80pct,Short_net_mean_lt_neg3 |

### Best passing（train）

**無通過組。**

## VSF delta（train · 早盤 09:00–10:30 · k=2.0 · 無 regime）

- VSF morning（無 regime）：n=**650** net_total=**−2955.09**
- RVSF：無合格冠軍（全 param train 未過）
- **解讀**：regime 濾網降頻但未改善 net；早盤無條件 fade 亦深度為負

## Valid 2026 Q1（診斷 only）

| param | n | gross/趟 | net/趟 |
|---|---|----------|--------|
| k2_p25 | 19 | -12.32 | -17.32 |
| k2_p30 | 22 | -10.55 | -15.55 |
| k2_p35 | 25 | -7.5 | -12.5 |
| k2p5_p25 | 8 | 3.02 | -1.98 |
| k2p5_p30 | 9 | -0.45 | -5.45 |
| k2p5_p35 | 10 | -2.29 | -7.29 |
| k3_p25 | 3 | 4.6 | -0.4 |
| k3_p30 | 3 | 4.6 | -0.4 |
| k3_p35 | 3 | 4.6 | -0.4 |

## §Decision

| 欄位 | 值 |
|------|-----|
| 決策 | **MVPClosed** — `thesis_i_rvsf_no_go` |
| Train 2025 | 最佳 k2_p30 n=133 net **−4.25**；全組 §3.1 disqualify |
| Valid Q1 | 全 param net 負 |
| UAT | **維持** `strategy-vwap-momentum` smoke |
| 日期 | 2026-06-28 |
