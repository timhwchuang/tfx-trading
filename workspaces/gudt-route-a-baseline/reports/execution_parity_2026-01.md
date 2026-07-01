# GUDT Execution Parity — 2026-01

**Period:** 2026-01-01 … 2026-01-31
**Months:** 2026-01

## Summary

| Metric | CF plan | Kernel |
|--------|--------:|-------:|
| Round-trips (n) | 5 | 5 |
| Net gross (pts) | 248.41 | 148.5 |
| Net delta | | -99.91 |
| Entry slip >1pt | 3 | |
| Exit reason mismatch | 1 | |
| Flatten substitute | 1 | |

**PASS:** True

### Warnings

- net_delta=-99.91 (warn-only)

## Per round

| day | seq | path | entry Δpx | exit plan | exit kernel | exit Δpx | plan PnL | kernel PnL | ΔPnL | mechanism |
|-----|-----|------|----------|-----------|-------------|----------|----------|------------|------|-----------|
| 2026-01-02 | 0 | flow_turn+drive_low_struct | 0.5 | horizon | horizon | -2.5 | 14.0 | 11.0 | -3.0 | match |
| 2026-01-05 | 0 | p0+sealed | 1.5 | trail_stop | trail_stop | 10.8 | 76.7 | 86.0 | 9.3 | match |
| 2026-01-14 | 0 | flow_turn+drive_low_struct | 1.5 | take_profit | session_force_flatten | -105.71 | 82.71 | -24.5 | -107.21 | flatten_substitute |
| 2026-01-22 | 0 | flow_turn+drive_low_struct | 0.5 | horizon | horizon | 0.5 | 43.0 | 43.0 | 0.0 | match |
| 2026-01-28 | 0 | flow_turn+drive_low_struct | -1.5 | horizon | horizon | -0.5 | 32.0 | 33.0 | 1.0 | match |
