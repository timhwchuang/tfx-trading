# GUDT Execution Parity — 2025-11

**Period:** 2025-11-01 … 2025-11-30
**Months:** 2025-11

## Net compare (CF plan vs kernel fills)

- **CF plan gross:** 43.23 pts
- **Kernel gross:** 47.0 pts
- **Delta (kernel − CF):** 3.77 pts

## Summary

| Metric | CF plan | Kernel |
|--------|--------:|-------:|
| Round-trips (n) | 5 | 5 |
| Net gross (pts) | 43.23 | 47.0 |
| Net delta | | 3.77 |
| Entry slip >1pt | 3 | |
| Exit reason mismatch | 0 | |
| Flatten substitute | 0 | |

**PASS:** True

### Warnings

- net_delta=3.77 (warn-only)

## Per round

| day | seq | path | entry Δpx | exit plan | exit kernel | exit Δpx | plan PnL | kernel PnL | ΔPnL | mechanism |
|-----|-----|------|----------|-----------|-------------|----------|----------|------------|------|-----------|
| 2025-11-04 | 0 | flow_turn+drive_low_struct | 1.5 | stop_loss | stop_loss | -1.5 | -14.0 | -17.0 | -3.0 | match |
| 2025-11-12 | 0 | flow_turn+drive_low_struct | 1.5 | trail_stop | trail_stop | 0.27 | 39.23 | 38.0 | -1.23 | match |
| 2025-11-17 | 0 | flow_turn+drive_low_struct | -2.5 | stop_loss | stop_loss | 5.5 | -8.0 | 0.0 | 8.0 | match |
| 2025-11-25 | 0 | flow_turn+drive_low_struct | 0.5 | stop_loss | stop_loss | 1.5 | -13.0 | -12.0 | 1.0 | match |
| 2025-11-27 | 0 | flow_turn+drive_low_struct | 0.5 | trail_stop | trail_stop | -0.5 | 39.0 | 38.0 | -1.0 | match |
