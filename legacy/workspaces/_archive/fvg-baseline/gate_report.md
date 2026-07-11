# FT-015 Gate Report — fvg-baseline（Phase 0 · skew）

> **Thesis P-009**：BOS → unmitigated FVG → zone retest + vol_1s ≤ p40。
> **Entry**：tick in FVG zone · 順 BOS 方向 · **雙向**。
> **Exit**：`atr_barrier_900s` · G3S **n≥15**。

## Phase 0b — Code review

| MUST | 結果 |
|------|------|
| MUST-1 FT-002 §4.7 FVG/BOS | PASS（agent 2026-06-28） |
| MUST-2 摩擦 5 · tick entry | PASS |
| MUST-3 funnel + post_entry | PASS |
| skew §3.2 appendix | PASS |

## Fingerprint (0c-1)

| 區間 | W30 stop-less med | n (G3S≥15) | barrier gross/趟 | 判定 |
|------|-------------------|------------|----------------|------|
| Train 2025-01-01～2025-12-31 | -0.0 | 211 | 0.33 | **未過** |

### Funnel（絕對數）

- session_days=241 → bos_active_fvg=222 → zone_touch=211 → vol_ok=211 → entry=211

## 進場後診斷（fingerprint · 非 gate）

> stop-less forward 順向 ≠ net edge；不得用診斷結果回頭 tune train grid。

| 指標 | mean | median |
|------|------|--------|
| Barrier gross | 0.33 | -3.0 |
| 180s MFE / MAE | 20.84 / 15.86 | 17.0 / 18.0 |
| W5m stop-less gross | 1.02 | 1.0 (net med -4.0) |
| W15m stop-less gross | -0.08 | 1.0 (net med -4.0) |
| W30m stop-less gross | -2.03 | -0.0 (net med -5.0) |

**Verdict**: `direction_weak`

- W30 median -0.0 撐不過摩擦 5.0 點
- 180s 內 MAE median 18.0 ≥ MFE 17.0（逆風路徑主導）

### Long / Short

| side | n | barrier med | W30 med |
|---|---:|---:|---:|
| Long | 112 | -1.0 | 2.0 |
| Short | 99 | -5.0 | -2.0 |

## Grid (0c-2)

*未執行 — 0c-1 結果見 §Decision*

## Valid 2026 Q1（參考 only · skew valid≤0 禁 holdout）

- n=46 · gross/趟=1.1 · net/趟=-3.9

## §Decision

| 欄位 | 值 |
|------|-----|
| 決策 | **MVPClosed** — `frp_fingerprint_fail` |
| outcome | `frp_fingerprint_fail` |
| thesis_class | **skew** |
| UAT | **維持** `strategy-vwap-momentum` |
| 日期 | 2026-06-28 |
