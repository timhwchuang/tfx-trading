# GUDT Execution Parity — 2026-03

**Period:** 2026-03-01 … 2026-03-31
**Months:** 2026-03

## Summary

| Metric | CF plan | Kernel |
|--------|--------:|-------:|
| Round-trips (n) | 6 | 6 |
| Net gross (pts) | -33.17 | -5.5 |
| Net delta | | 27.67 |
| Entry slip >1pt | 4 | |
| Exit reason mismatch | 0 | |
| Flatten substitute | 0 | |

**PASS:** True

### Warnings

- net_delta=27.67 (warn-only)

## Per round

| day | seq | path | entry Δpx | exit plan | exit kernel | exit Δpx | plan PnL | kernel PnL | ΔPnL | mechanism |
|-----|-----|------|----------|-----------|-------------|----------|----------|------------|------|-----------|
| 2026-03-05 | 0 | flow_turn+drive_low_struct | -1.5 | stop_loss | stop_loss | 11.5 | -53.0 | -40.0 | 13.0 | match |
| 2026-03-10 | 0 | flow_turn+drive_low_struct | -0.5 | trail_stop | trail_stop | 7.49 | 116.01 | 124.0 | 7.99 | match |
| 2026-03-11 | 0 | flow_turn+drive_low_struct | 2.5 | dist_signal | dist_signal | -1.5 | -26.0 | -30.0 | -4.0 | match |
| 2026-03-11 | 1 | flow_turn+drive_low_struct | 0.5 | stop_loss | stop_loss | 0.5 | -66.0 | -66.0 | 0.0 | match |
| 2026-03-18 | 0 | flow_turn+drive_low_struct | 6.0 | trail_stop | trail_stop | -3.34 | 59.84 | 50.5 | -9.34 | match |
| 2026-03-25 | 0 | p0+sealed | -19.5 | stop_loss | stop_loss | 0.52 | -64.02 | -44.0 | 20.02 | match |
