# GUDT Execution Parity — UAT_2m

**Period:** 2026-05-01 … 2026-06-30

## Net compare (CF plan vs kernel fills)

- **CF plan gross:** 362.71 pts
- **Kernel gross:** -28.0 pts
- **Delta (kernel − CF):** -390.71 pts

## Summary

| Metric | CF plan | Kernel |
|--------|--------:|-------:|
| Round-trips (n) | 13 | 13 |
| Net gross (pts) | 362.71 | -28.0 |
| Net delta | | -390.71 |
| Entry slip >1pt | 10 | |
| Exit reason mismatch | 1 | |
| Flatten substitute | 0 | |

**PASS:** True

### Warnings

- net_delta=-390.71 (warn-only)

## Per round

| day | seq | path | entry Δpx | exit plan | exit kernel | exit Δpx | plan PnL | kernel PnL | ΔPnL | mechanism |
|-----|-----|------|----------|-----------|-------------|----------|----------|------------|------|-----------|
| 2026-05-04 | 0 | p0+sealed | 1.5 | horizon | horizon | 0.5 | 51.0 | 50.0 | -1.0 | match |
| 2026-05-06 | 0 | flow_turn+drive_low_struct | 2.5 | stop_loss |  | -445.5 | 446.0 | -2.0 | -448.0 | price_mismatch |
| 2026-05-07 | 0 | p0+sealed | -0.5 | breakeven | breakeven | 1.5 | 0.0 | 2.0 | 2.0 | match |
| 2026-05-14 | 0 | flow_turn+drive_low_struct | 3.5 | stop_loss | stop_loss | 6.5 | -32.0 | -29.0 | 3.0 | match |
| 2026-05-21 | 0 | p0+sealed | -6.5 | breakeven | breakeven | 2.5 | 0.0 | 9.0 | 9.0 | match |
| 2026-05-25 | 0 | p0+sealed | -12.5 | stop_loss | stop_loss | -2.48 | -89.02 | -79.0 | 10.02 | match |
| 2026-05-29 | 0 | p0+sealed | 0.5 | stop_loss | stop_loss | 2.77 | -105.27 | -103.0 | 2.27 | match |
| 2026-06-01 | 0 | p0+sealed | -5.5 | trail_stop | trail_stop | 1.5 | 238.0 | 245.0 | 7.0 | match |
| 2026-06-15 | 0 | flow_turn+drive_low_struct | -4.5 | horizon | horizon | 5.5 | -19.0 | -9.0 | 10.0 | match |
| 2026-06-18 | 0 | flow_turn+drive_low_struct | -4.5 | stop_loss | stop_loss | 4.5 | -105.0 | -96.0 | 9.0 | match |
| 2026-06-22 | 0 | flow_turn+drive_low_struct | 0.5 | horizon | horizon | -4.5 | 8.0 | 3.0 | -5.0 | match |
| 2026-06-29 | 0 | p0+sealed | -14.5 | dist_signal | dist_signal | 4.5 | -117.0 | -98.0 | 19.0 | match |
| 2026-06-29 | 1 | p0+sealed | -3.5 | horizon | horizon | 4.5 | 87.0 | 79.0 | -8.0 | match |
