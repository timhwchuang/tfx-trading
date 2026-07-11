# GUDT Execution Parity — custom_2026-01-01_2026-06-30

**Period:** 2026-01-01 … 2026-06-30

## Net compare (CF plan vs kernel fills)

- **CF plan gross:** 1551.5 pts
- **Kernel gross:** 653.0 pts
- **Delta (kernel − CF):** -898.5 pts

## Summary

| Metric | CF plan | Kernel |
|--------|--------:|-------:|
| Round-trips (n) | 40 | 40 |
| Net gross (pts) | 1551.5 | 653.0 |
| Net delta | | -898.5 |
| Entry slip >1pt | 24 | |
| Exit reason mismatch | 6 | |
| Flatten substitute | 1 | |

**PASS:** True

### Warnings

- net_delta=-898.5 (warn-only)

## Per round

| day | seq | path | entry Δpx | exit plan | exit kernel | exit Δpx | plan PnL | kernel PnL | ΔPnL | mechanism |
|-----|-----|------|----------|-----------|-------------|----------|----------|------------|------|-----------|
| 2026-01-02 | 0 | flow_turn+drive_low_struct | 0.5 | horizon | horizon | -2.5 | 14.0 | 11.0 | -3.0 | match |
| 2026-01-05 | 0 | p0+sealed | 1.5 | trail_stop | trail_stop | 10.8 | 76.7 | 86.0 | 9.3 | match |
| 2026-01-14 | 0 | flow_turn+drive_low_struct | 1.5 | take_profit | session_force_flatten | -105.71 | 82.71 | -24.5 | -107.21 | flatten_substitute |
| 2026-01-22 | 0 | flow_turn+drive_low_struct | 0.5 | horizon | horizon | 0.5 | 43.0 | 43.0 | 0.0 | match |
| 2026-01-28 | 0 | flow_turn+drive_low_struct | -1.5 | horizon | horizon | -0.5 | 32.0 | 33.0 | 1.0 | match |
| 2026-02-03 | 0 | flow_turn+drive_low_struct | 0.5 | stop_loss |  | -60.5 | 57.0 | -4.0 | -61.0 | price_mismatch |
| 2026-02-09 | 0 | flow_turn+drive_low_struct | 0.5 | horizon | horizon | -0.5 | 54.0 | 53.0 | -1.0 | match |
| 2026-02-10 | 0 | flow_turn+drive_low_struct | 0.5 | trail_stop | trail_stop | -1.11 | 50.61 | 49.0 | -1.61 | match |
| 2026-02-11 | 0 | p0+sealed | -3.5 | breakeven | breakeven | 1.5 | 0.0 | 5.0 | 5.0 | match |
| 2026-02-24 | 0 | p0+sealed | -1.5 | stop_loss | stop_loss | 6.36 | -52.86 | -45.0 | 7.86 | match |
| 2026-02-25 | 0 | p0+sealed | 4.5 | breakeven | breakeven | 0.5 | 0.0 | -4.0 | -4.0 | match |
| 2026-03-05 | 0 | flow_turn+drive_low_struct | -1.5 | stop_loss | stop_loss | 11.5 | -53.0 | -40.0 | 13.0 | match |
| 2026-03-10 | 0 | flow_turn+drive_low_struct | -0.5 | trail_stop | trail_stop | 7.49 | 116.01 | 124.0 | 7.99 | match |
| 2026-03-11 | 0 | flow_turn+drive_low_struct | 2.5 | dist_signal | dist_signal | -1.5 | -26.0 | -30.0 | -4.0 | match |
| 2026-03-11 | 1 | flow_turn+drive_low_struct | 0.5 | stop_loss | stop_loss | 0.5 | -66.0 | -66.0 | 0.0 | match |
| 2026-03-18 | 0 | flow_turn+drive_low_struct | 6.0 | trail_stop | trail_stop | -3.34 | 59.84 | 50.5 | -9.34 | match |
| 2026-03-25 | 0 | p0+sealed | -19.5 | stop_loss | stop_loss | 0.52 | -64.02 | -44.0 | 20.02 | match |
| 2026-04-01 | 0 | flow_turn+drive_low_struct | -2.5 | horizon | horizon | -5.5 | 67.0 | 64.0 | -3.0 | match |
| 2026-04-07 | 0 | flow_turn+drive_low_struct | 0.5 | stop_loss |  | -96.5 | 94.0 | -3.0 | -97.0 | price_mismatch |
| 2026-04-08 | 0 | flow_turn+drive_low_struct | 0.5 | trail_stop | trail_stop | -1.41 | 94.91 | 93.0 | -1.91 | match |
| 2026-04-10 | 0 | flow_turn+drive_low_struct | 0.5 | horizon | horizon | -0.5 | -8.0 | -9.0 | -1.0 | match |
| 2026-04-14 | 0 | flow_turn+drive_low_struct | 1.5 | stop_loss |  | -36.5 | 35.0 | -3.0 | -38.0 | price_mismatch |
| 2026-04-15 | 0 | p0+sealed | 0.5 | trail_stop | trail_stop | -0.1 | 46.6 | 46.0 | -0.6 | match |
| 2026-04-20 | 0 | flow_turn+drive_low_struct | 0.5 | horizon | horizon | -1.5 | 14.0 | 12.0 | -2.0 | match |
| 2026-04-21 | 0 | flow_turn+drive_low_struct | -0.5 | horizon | horizon | -0.5 | 112.0 | 112.0 | 0.0 | match |
| 2026-04-23 | 0 | flow_turn+drive_low_struct | -2.5 | stop_loss |  | -243.5 | 243.0 | 2.0 | -241.0 | price_mismatch |
| 2026-04-24 | 0 | p0+sealed | -8.5 | take_profit | take_profit | -4.79 | 166.29 | 170.0 | 3.71 | match |
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
