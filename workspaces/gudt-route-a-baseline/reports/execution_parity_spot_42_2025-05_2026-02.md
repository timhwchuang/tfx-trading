# GUDT Execution Parity — spot_42_2025-05_2026-02

**Period:** 2025-05-01 … 2026-02-28
**Months:** 2025-05, 2026-02

## Summary

| Metric | CF plan | Kernel |
|--------|--------:|-------:|
| Round-trips (n) | 60 | 59 |
| Net gross (pts) | 1032.06 | 810.0 |
| Net delta | | -222.06 |
| Entry slip >1pt | 20 | |
| Exit reason mismatch | 8 | |
| Flatten substitute | 3 | |

**PASS:** False

### Failures

- round_count mismatch: cf=60 kernel=59
- day_mismatches=1

### Warnings

- net_delta=-222.06 (warn-only)

## Per round

| day | seq | path | entry Δpx | exit plan | exit kernel | exit Δpx | plan PnL | kernel PnL | ΔPnL | mechanism |
|-----|-----|------|----------|-----------|-------------|----------|----------|------------|------|-----------|
| 2025-05-02 | 0 | flow_turn+drive_low_struct | 0.5 | horizon | horizon | -0.5 | 33.0 | 32.0 | -1.0 | match |
| 2025-05-08 | 0 | flow_turn+drive_low_struct | 0.5 | stop_loss |  | -9.5 | 7.0 | -3.0 | -10.0 | price_mismatch |
| 2025-05-12 | 0 | flow_turn+drive_low_struct | 0.5 | trail_stop | trail_stop | 4.36 | 48.14 | 52.0 | 3.86 | match |
| 2025-05-28 | 0 | flow_turn+drive_low_struct | 0.5 | stop_loss | stop_loss | 0.5 | -5.0 | -5.0 | 0.0 | match |
| 2025-06-03 | 0 | flow_turn+drive_low_struct | 2.5 | stop_loss |  | -81.5 | 84.0 | 0.0 | -84.0 | price_mismatch |
| 2025-06-04 | 0 | flow_turn+drive_low_struct | 0.5 | horizon | session_force_flatten | 42.0 | 7.0 | 48.5 | 41.5 | flatten_substitute |
| 2025-06-05 | 0 | p0+sealed | 0.5 | breakeven | breakeven | 4.5 | 0.0 | 4.0 | 4.0 | match |
| 2025-06-10 | 0 | p0+sealed | 1.5 | horizon | horizon | 2.5 | 89.0 | 90.0 | 1.0 | match |
| 2025-06-17 | 0 | flow_turn+drive_low_struct | 0.5 | trail_stop | trail_stop | 0.5 | 36.0 | 36.0 | 0.0 | match |
| 2025-07-01 | 0 | flow_turn+drive_low_struct | -0.5 | horizon | horizon | 0.5 | 11.0 | 12.0 | 1.0 | match |
| 2025-07-03 | 0 | flow_turn+drive_low_struct | 0.5 | horizon | horizon | -0.5 | 28.0 | 27.0 | -1.0 | match |
| 2025-07-16 | 0 | p0+sealed | -4.5 | trail_stop | trail_stop | 4.5 | 53.0 | 62.0 | 9.0 | match |
| 2025-07-30 | 0 | flow_turn+drive_low_struct | 0.5 | horizon | horizon | 0.5 | 27.0 | 27.0 | 0.0 | match |
| 2025-08-05 | 0 | p0+sealed | 0.5 | stop_loss | stop_loss | 1.75 | -31.25 | -30.0 | 1.25 | match |
| 2025-08-07 | 0 | p0+sealed | -0.5 | horizon | horizon | -0.5 | -8.0 | -8.0 | 0.0 | match |
| 2025-08-13 | 0 | flow_turn+drive_low_struct | -0.5 | horizon | horizon | 1.5 | 28.0 | 30.0 | 2.0 | match |
| 2025-08-21 | 0 | p0+sealed | -3.5 | stop_loss | stop_loss | 2.5 | -32.0 | -26.0 | 6.0 | match |
| 2025-08-25 | 0 | flow_turn+drive_low_struct | 0.5 | horizon | horizon | -2.5 | 34.0 | 31.0 | -3.0 | match |
| 2025-08-29 | 0 | flow_turn+drive_low_struct | -1.5 | stop_loss | stop_loss | 0.5 | -4.0 | -2.0 | 2.0 | match |
| 2025-09-04 | 0 | p0+sealed | 0.5 | stop_loss | stop_loss | 3.2 | -31.7 | -29.0 | 2.7 | match |
| 2025-09-05 | 0 | flow_turn+drive_low_struct | 0.5 | stop_loss | stop_loss | 2.5 | -40.0 | -38.0 | 2.0 | match |
| 2025-09-08 | 0 | flow_turn+drive_low_struct | 0.5 | horizon | horizon | -0.5 | -25.0 | -26.0 | -1.0 | match |
| 2025-09-09 | 0 | p0+sealed | -2.5 | horizon | horizon | -0.5 | 20.0 | 22.0 | 2.0 | match |
| 2025-09-10 | 0 | flow_turn+drive_low_struct | -0.5 | horizon | horizon | -1.5 | 21.0 | 20.0 | -1.0 | match |
| 2025-09-11 | 0 | p0+sealed (veto) | -4.5 | stop_loss | stop_loss | 0.18 | -32.68 | -28.0 | 4.68 | match |
| 2025-09-12 | 0 | flow_turn+drive_low_struct | 0.5 | horizon | horizon | -0.5 | 51.0 | 50.0 | -1.0 | match |
| 2025-09-16 | 0 | flow_turn+drive_low_struct | 0.5 | horizon | horizon | -1.5 | -26.0 | -28.0 | -2.0 | match |
| 2025-09-23 | 0 | flow_turn+drive_low_struct | 0.5 | horizon | horizon | -2.5 | 39.0 | 36.0 | -3.0 | match |
| 2025-10-02 | 0 | p0+sealed | -2.5 | horizon | horizon | -1.5 | 0.0 | 1.0 | 1.0 | match |
| 2025-10-07 | 0 | p0+sealed | -2.5 | trail_stop | trail_stop | 1.17 | 47.33 | 51.0 | 3.67 | match |
| 2025-10-16 | 0 | flow_turn+drive_low_struct | -0.5 | trail_stop | trail_stop | -1.33 | 51.83 | 51.0 | -0.83 | match |
| 2025-10-21 | 0 | flow_turn+drive_low_struct | -0.5 | horizon | horizon | -3.0 | 27.0 | 24.5 | -2.5 | match |
| 2025-10-27 | 0 | p0+sealed | -0.5 | stop_loss | stop_loss | 0.25 | -43.75 | -43.0 | 0.75 | match |
| 2025-10-29 | 0 | flow_turn+drive_low_struct | 0.5 | trail_stop | trail_stop | 2.5 | 35.0 | 37.0 | 2.0 | match |
| 2025-11-04 | 0 | flow_turn+drive_low_struct | 1.5 | stop_loss | stop_loss | -1.5 | -14.0 | -17.0 | -3.0 | match |
| 2025-11-12 | 0 | flow_turn+drive_low_struct | 1.5 | trail_stop | trail_stop | 0.27 | 39.23 | 38.0 | -1.23 | match |
| 2025-11-17 | 0 | flow_turn+drive_low_struct | -2.5 | stop_loss | stop_loss | 5.5 | -8.0 | 0.0 | 8.0 | match |
| 2025-11-25 | 0 | flow_turn+drive_low_struct | 0.5 | stop_loss | stop_loss | 1.5 | -13.0 | -12.0 | 1.0 | match |
| 2025-11-27 | 0 | flow_turn+drive_low_struct | 0.5 | trail_stop | trail_stop | -0.5 | 39.0 | 38.0 | -1.0 | match |
| 2025-12-02 | 0 | flow_turn+drive_low_struct | -0.5 | stop_loss | stop_loss | -0.5 | -13.0 | -13.0 | 0.0 | match |
| 2025-12-03 | 0 | flow_turn+drive_low_struct | -0.5 | stop_loss | stop_loss | 0.5 | -37.0 | -36.0 | 1.0 | match |
| 2025-12-04 | 0 | flow_turn+drive_low_struct | -0.5 | stop_loss |  | -51.5 | 50.0 | -1.0 | -51.0 | price_mismatch |
| 2025-12-08 | 0 | p0+sealed | -1.5 | trail_stop | trail_stop | 0.5 | 36.0 | 38.0 | 2.0 | match |
| 2025-12-10 | 0 | flow_turn+drive_low_struct | 0.5 | stop_loss |  | -7.5 | 8.0 | 0.0 | -8.0 | price_mismatch |
| 2025-12-12 | 0 | flow_turn+drive_low_struct | 0.5 | stop_loss | stop_loss | 4.5 | -6.0 | -2.0 | 4.0 | match |
| 2025-12-19 | 0 | p0+sealed | -5.5 | stop_loss | stop_loss | -0.25 | -31.25 | -26.0 | 5.25 | match |
| 2025-12-22 | 0 | flow_turn+drive_low_struct | 0.5 | horizon | horizon | -1.5 | 26.0 | 24.0 | -2.0 | match |
| 2025-12-26 | 0 | flow_turn+drive_low_struct | 0.5 | horizon | horizon | -0.5 | 26.0 | 25.0 | -1.0 | match |
| 2025-12-29 | 0 | p0+sealed | -3.5 | take_profit | session_force_flatten | -9.0 | 75.0 | 69.5 | -5.5 | flatten_substitute |
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
| 2026-02-25 | 0 | p0+sealed | None | breakeven |  | None | 0.0 | None | None | missing_kernel |
