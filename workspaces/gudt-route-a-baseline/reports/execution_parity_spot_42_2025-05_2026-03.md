# GUDT Execution Parity — spot_42_2025-05_2026-03

**Period:** 2025-05-01 … 2026-03-31
**Months:** 2025-05, 2026-03

## Summary

| Metric | CF plan | Kernel |
|--------|--------:|-------:|
| Round-trips (n) | 10 | 9 |
| Net gross (pts) | 49.97 | 20.0 |
| Net delta | | -29.97 |
| Entry slip >1pt | 3 | |
| Exit reason mismatch | 1 | |
| Flatten substitute | 0 | |

**PASS:** False

### Failures

- round_count mismatch: cf=10 kernel=9
- day_mismatches=1

### Warnings

- net_delta=-29.97 (warn-only)

## Per round

| day | seq | path | entry Δpx | exit plan | exit kernel | exit Δpx | plan PnL | kernel PnL | ΔPnL | mechanism |
|-----|-----|------|----------|-----------|-------------|----------|----------|------------|------|-----------|
| 2025-05-02 | 0 | flow_turn+drive_low_struct | 0.5 | horizon | horizon | -0.5 | 33.0 | 32.0 | -1.0 | match |
| 2025-05-08 | 0 | flow_turn+drive_low_struct | 0.5 | stop_loss |  | -9.5 | 7.0 | -3.0 | -10.0 | price_mismatch |
| 2025-05-12 | 0 | flow_turn+drive_low_struct | 0.5 | trail_stop | trail_stop | 4.36 | 48.14 | 52.0 | 3.86 | match |
| 2025-05-28 | 0 | flow_turn+drive_low_struct | 0.5 | stop_loss | stop_loss | 0.5 | -5.0 | -5.0 | 0.0 | match |
| 2026-03-05 | 0 | flow_turn+drive_low_struct | -1.5 | stop_loss | stop_loss | 11.5 | -53.0 | -40.0 | 13.0 | match |
| 2026-03-10 | 0 | flow_turn+drive_low_struct | -0.5 | trail_stop | trail_stop | 7.49 | 116.01 | 124.0 | 7.99 | match |
| 2026-03-11 | 0 | flow_turn+drive_low_struct | 2.5 | dist_signal | dist_signal | -1.5 | -26.0 | -30.0 | -4.0 | match |
| 2026-03-11 | 1 | flow_turn+drive_low_struct | 0.5 | stop_loss | stop_loss | 0.5 | -66.0 | -66.0 | 0.0 | match |
| 2026-03-18 | 0 | flow_turn+drive_low_struct | None | trail_stop |  | None | 59.84 | None | None | missing_kernel |
| 2026-03-25 | 0 | p0+sealed | -19.5 | stop_loss | stop_loss | 0.52 | -64.02 | -44.0 | 20.02 | match |
