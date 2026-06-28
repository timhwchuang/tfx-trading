# FT-014 Gate Report — mvhp-baseline（Phase 0）

> **Thesis P-004**：Morning VWAP hold pullback — long-only Phase 0。
> **Entry**：raw 1m bar close（ORB/VSF 同族 · 無 FT-013 entry+1）。
> **Exit**：`atr_barrier_900s` · max_hold_sec=900。

## Phase 0b — Code review

| MUST | 結果 |
|------|------|
| MUST-1 hold + slope + first touch | PASS（agent 2026-06-28） |
| MUST-2 摩擦 5 | PASS |
| MUST-3 funnel 絕對數 | PASS |
| post_entry hook | PASS |

## Fingerprint (0c-1)

| 區間 | W30 stop-less med | n | barrier gross/趟 | 判定 |
|------|-------------------|---|----------------|------|
| Train 2025-01-01～2025-12-31 | 38.0 | 7 | 24.0 | **未過** |

### Funnel（絕對數）

- session_days=241 → hold_pass=164 → first_touch=77 → vol_shrink=7 → entry=7
- hold→entry rate=0.0427

## 進場後診斷（fingerprint · 非 gate）

> stop-less forward 順向 ≠ net edge；不得用診斷結果回頭 tune train grid。

| 指標 | mean | median |
|------|------|--------|
| Barrier gross | 24.0 | 50.0 |
| 180s MFE / MAE | 34.71 / 12.86 | 50.0 / 15.0 |
| W5m stop-less gross | 20.43 | 36.0 (net med 31.0) |
| W15m stop-less gross | 24.43 | 18.0 (net med 13.0) |
| W30m stop-less gross | 36.29 | 38.0 (net med 33.0) |

**Verdict**: `direction_ok_margin_thin`

- W30 stop-less 有正 median，仍須看 barrier 與 valid
- 180s 內 MFE median 50.0 > MAE 15.0（路徑曾順向）

### Long / Short

| side | n | barrier med | W30 med |
|---|---:|---:|---:|
| Long | 7 | 50.0 | 38.0 |

## Grid (0c-2)

*未執行 — 0c-1 結果見 §Decision*

## Valid 2026 Q1（參考 only）

- n=0 · gross/趟=None · net/趟=None
- W30 stop-less med=None

## §Decision

| 欄位 | 值 |
|------|-----|
| 決策 | **MVPClosed** — `mvhp_fingerprint_fail` |
| outcome | `mvhp_fingerprint_fail` |
| UAT | **維持** `strategy-vwap-momentum` |
| Pilot 備註 | bar close vs IOC ±3 未模擬 |
| 日期 | 2026-06-28 |
