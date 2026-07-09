# OSF — Opening Sweep + 15m FVG + 5m Trigger (Phase 0)

Long-only · bar-based · SessionBarCache SSOT.

## Stack

| Layer | TF | Rule |
|-------|-----|------|
| HTF | daily | Close > D-1 and Close > MA20 |
| HTF | 4h | bullish BOS + discount (10-bar range) |
| HTF | 1h | no bearish BOS + higher lows or bullish BOS |
| Liquidity | 1m | OR + dawn_low + overnight_low pools |
| Gap | 1m | gap_up / gap_down / flat at day open |

Overnight / gap window (**disk SSOT**): last date with day-session 1m bars → that
day 15:00 → day open. Dates with bars = trading days; dates without bars are not.
No `trade_days` / holiday calendar in this path — assume kbar cache is complete.
| Setup | 15m | sweep pool + reclaim + bullish FVG + displacement |
| Trigger | 5m | retest FVG upper zone, bullish close |

## Memory

- One `OsfBarStore.load_range` per **batch** (disk once for the date range).
- Load window sized by `daily_lookback + batch_span` (linear); closed TFs rebuilt
  **untrimmed** from 1m so early batch days are not dropped by SessionBarCache TF trim.
- `OsfDayContext.snapshot(as_of)` bisect + capped cache (48 minute-truncated keys).

## HTF modes

`none` | `h4_only` (default mainline) | `h4_h1` | `full`

## Liquidity modes

`pools` (dawn + overnight) | `or_only` | `pools_or` (union)

## Post-trigger

MAE/MFE at 15/30/60/120m via 1m High/Low.