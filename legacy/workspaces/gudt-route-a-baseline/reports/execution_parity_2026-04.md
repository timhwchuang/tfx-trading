# GUDT Execution Parity — 2026-04

**Period:** 2026-04-01 … 2026-04-30
**Months:** 2026-04

## Summary

| Metric | CF plan | Kernel |
|--------|--------:|-------:|
| Round-trips (n) | 10 | 10 |
| Net gross (pts) | 864.8 | 901.0 |
| Net delta | | 36.2 |
| Entry slip >1pt | 4 | |
| Exit reason mismatch | 5 | |
| Flatten substitute | 2 | |

**PASS:** True

### Warnings

- net_delta=36.2 (warn-only)

## Per round

| day | seq | path | entry Δpx | exit plan | exit kernel | exit Δpx | plan PnL | kernel PnL | ΔPnL | mechanism |
|-----|-----|------|----------|-----------|-------------|----------|----------|------------|------|-----------|
| 2026-04-01 | 0 | flow_turn+drive_low_struct | -2.5 | horizon | session_force_flatten | 172.0 | 67.0 | 241.5 | 174.5 | flatten_substitute |
| 2026-04-07 | 0 | flow_turn+drive_low_struct | 0.5 | stop_loss |  | -96.5 | 94.0 | -3.0 | -97.0 | price_mismatch |
| 2026-04-08 | 0 | flow_turn+drive_low_struct | 0.5 | trail_stop | trail_stop | -1.41 | 94.91 | 93.0 | -1.91 | match |
| 2026-04-10 | 0 | flow_turn+drive_low_struct | 0.5 | horizon | horizon | -0.5 | -8.0 | -9.0 | -1.0 | match |
| 2026-04-14 | 0 | flow_turn+drive_low_struct | 1.5 | stop_loss |  | -36.5 | 35.0 | -3.0 | -38.0 | price_mismatch |
| 2026-04-15 | 0 | p0+sealed | 0.5 | trail_stop | trail_stop | -0.1 | 46.6 | 46.0 | -0.6 | match |
| 2026-04-20 | 0 | flow_turn+drive_low_struct | 0.5 | horizon | horizon | -1.5 | 14.0 | 12.0 | -2.0 | match |
| 2026-04-21 | 0 | flow_turn+drive_low_struct | -0.5 | horizon | horizon | -0.5 | 112.0 | 112.0 | 0.0 | match |
| 2026-04-23 | 0 | flow_turn+drive_low_struct | -2.5 | stop_loss |  | -243.5 | 243.0 | 2.0 | -241.0 | price_mismatch |
| 2026-04-24 | 0 | p0+sealed | -8.5 | take_profit | session_force_flatten | 234.71 | 166.29 | 409.5 | 243.21 | flatten_substitute |
