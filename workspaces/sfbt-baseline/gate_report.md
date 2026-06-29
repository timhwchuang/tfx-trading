# FT-019 Gate Report — sfbt-baseline（Phase 0 · skew · exit-led）

> **Thesis P-012**：Sweep FVG breakout trail — **long-only** · sweep→reclaim→breakout.
> **Exit**：`fvg_mid_trail_skew_900s` · BE@1×risk → trail@2×risk/1.5×ATR@0.5 → TP@4×risk · G3S **n≥15**.
> **Fingerprint**：**W900** stop-less gross median > 0.

## Phase 0-design

| 項目 | 結果 |
|------|------|
| 資深 TXF Conditional PASS | PASS（2026-06-29 · P0 封印） |

## Phase 0b — Code review

| MUST | 結果 |
|------|------|
| MUST-1 sweep/reclaim/FVG 序 · breakout 非 retest | PASS（agent 2026-06-29） |
| MUST-2 fvg_mid trail · risk_unit · tie-break | PASS |
| MUST-3 W900 fingerprint | PASS |
| MUST-4 skew · exit_gap 附錄 | PASS |

## Fingerprint (0c-1)

| 區間 | W900 stop-less med | n | trail gross/趟 | 判定 |
|------|-------------------|---|----------------|------|
| Train 2025-01-01～2025-12-31 | 1.0 | 229 | 1.19 | **通過** |

### Funnel（絕對數 · long-only）

- session_days=241 → sweep_signal=241 → reclaim_ok=241 → fvg_active=232 → breakout_signal=231 → entry=229

## 進場後診斷（fingerprint · 非 gate）

> stop-less forward 順向 ≠ net edge；不得用診斷結果回頭 tune train grid。

| 指標 | mean | median |
|------|------|--------|
| Barrier gross | 1.19 | 0.0 |
| 180s MFE / MAE | 22.69 / 16.43 | 17.0 / 13.0 |
| W5m stop-less gross | 3.83 | 2.0 (net med -3.0) |
| W15m stop-less gross | 1.14 | 1.0 (net med -4.0) |
| W30m stop-less gross | 3.25 | 2.0 (net med -3.0) |

**Verdict**: `direction_weak`

- W30 median 2.0 撐不過摩擦 5.0 點
- 180s 內 MFE median 17.0 > MAE 13.0（路徑曾順向）

### Long / Short

| side | n | barrier med | W30 med |
|---|---:|---:|---:|
| Long | 229 | 0.0 | 2.0 |

## Exit 診斷（fingerprint · 非 gate）

- **exit_gap** ≈ MFE_med − gross_med = **17.0**
- **pct_hit_2R** = 0.1528
- **pct_mfe_ge_1atr** = 0.3231
- MFE median = 17.0 · gross median = 0.0

## Skew 附錄（fingerprint · 診斷）

- payoff_ratio=1.575 · tail_count=66
- net_mean@friction7=-5.81 · top3_share=0.081
- slippage extra mean net: {'extra_0': -3.81, 'extra_1': -4.81, 'extra_2': -5.81}

## Grid (0c-2)

*未完整執行（11,664 combo 全 grid 記憶體/時間成本過高）· fingerprint frozen exit 已 G1 fail（gross **1.19** < 5）· 判定同 grid fail*

## Valid 2026 Q1（參考 · skew 硬擋）

- n=52 · gross/趟=3.11 · net/趟=-1.89
- **holdout_blocked_overfit** — valid net≤0 禁 holdout（HOLDOUT v2.2.1 §4）

## §Decision

| 欄位 | 值 |
|------|-----|
| 決策 | **MVPClosed** — `sfbt_fingerprint_pass_g1_fail` |
| outcome | `sfbt_fingerprint_pass_g1_fail` |
| thesis_class | **skew** |
| UAT | **維持** `strategy-vwap-momentum` |
| 日期 | 2026-06-29 |
