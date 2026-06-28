# FT-011 Gate Report — scb-baseline（Phase 0）

> **Thesis H**：Session Confluence Breakout — Phase 0 **long-only**。
> **主判**：**2025 train**（Holdout v2.1）· 2026 Q1 valid 參考。

| 區間 | 產物 | Phase 0 |
|------|------|---------|
| **Train** 2025-01-01～2025-12-31 | [`counterfactual_scb_train.json`](reports/counterfactual_scb_train.json) | **未過** |
| Valid 2026-01-01～2026-03-31 | [`counterfactual_scb_valid.json`](reports/counterfactual_scb_valid.json) | 通過（參考） |

## Train — summary_by_param

| param | n | gross/趟 | net/趟 | gross_median | QSL | disqualify |
|---|---|----------|--------|--------------|-----|------------|
| rm20 | 72 | 0.39 | -4.61 | -24.65 | 0.0694 | gross_median_le_neg5,Long_net_mean_lt_neg3 |
| rm30 | 46 | 1.99 | -3.01 | -24.05 | 0.0217 | gross_median_le_neg5,Long_net_mean_lt_neg3 |

### Best passing（train）

**無通過組。**

## Train — session_bucket（G5-bucket 診斷）

### rm20

| bucket | n | gross/趟 | net/趟 |
|---|---|----------|--------|
| morning | 72 | 0.39 | -4.61 |

### rm30

| bucket | n | gross/趟 | net/趟 |
|---|---|----------|--------|
| morning | 46 | 1.99 | -3.01 |

## ORB delta（train · long · SCB 窗 · bk=0）

| param | orb_n | scb_n | filtered | orb_net | scb_net | delta | pass_rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| rm20 | 162 | 72 | 90 | -665.96 | -332.05 | 333.91 | 0.4444 |
| rm30 | 143 | 46 | 97 | -543.87 | -138.51 | 405.36 | 0.3217 |

## Valid 2026 Q1（參考 only）

| param | n | gross/趟 | net/趟 |
|---|---|----------|--------|
| rm20 | 35 | 0.69 | -4.31 |
| rm30 | 31 | 33.47 | 28.47 |

## 冠軍資格

- [ ] G1–G3
- [ ] §3.1 無 disqualify

## §Decision

| 欄位 | 值 |
|------|-----|
| 決策 | **No-Go at Phase 0** (`thesis_h_scb_no_go`) |
| 備註 | valid 過但 train 未過 — 不一致 |
| UAT | **維持** `strategy-vwap-momentum` |
| 日期 | 2026-06-28 |
