# GUDT Execution Parity — custom_2026-01-01_2026-06-30

**Period:** 2026-01-01 … 2026-06-30

## Net compare (CF plan vs kernel fills)

- **CF plan gross:** 11536.0 pts
- **Kernel gross:** 11294.0 pts
- **Delta (kernel − CF):** -242.0 pts

## Summary

| Metric | CF plan | Kernel |
|--------|--------:|-------:|
| Round-trips (n) | 44 | 44 |
| Net gross (pts) | 11536.0 | 11294.0 |
| Net delta | | -242.0 |
| Entry slip >1pt | 31 | |
| Exit reason mismatch | 0 | |
| Flatten substitute | 0 | |

**PASS:** True

### Warnings

- net_delta=-242.0 (warn-only)

## Per round

| day | seq | path | entry Δpx | exit plan | exit kernel | exit Δpx | plan PnL | kernel PnL | ΔPnL | mechanism |
|-----|-----|------|----------|-----------|-------------|----------|----------|------------|------|-----------|
| 2026-01-02 | 0 | wash_beta | -0.5 | session_force_flatten | session_force_flatten | -8.0 | 433.0 | 425.5 | -7.5 | match |
| 2026-01-05 | 0 | wash_beta | 3.5 | session_force_flatten | session_force_flatten | -7.0 | 409.0 | 398.5 | -10.5 | match |
| 2026-01-14 | 0 | wash_beta | 0.5 | session_force_flatten | session_force_flatten | -7.0 | -4.0 | -11.5 | -7.5 | match |
| 2026-01-22 | 0 | wash_beta | -0.5 | session_force_flatten | session_force_flatten | -5.0 | -21.0 | -25.5 | -4.5 | match |
| 2026-01-28 | 0 | wash_beta | -4.5 | session_force_flatten | session_force_flatten | -8.0 | 170.0 | 166.5 | -3.5 | match |
| 2026-02-03 | 0 | wash_beta | 1.5 | session_force_flatten | session_force_flatten | -8.0 | -61.0 | -70.5 | -9.5 | match |
| 2026-02-09 | 0 | wash_beta | -2.5 | session_force_flatten | session_force_flatten | -8.0 | -208.0 | -213.5 | -5.5 | match |
| 2026-02-10 | 0 | wash_beta | 1.5 | session_force_flatten | session_force_flatten | -8.0 | 399.0 | 389.5 | -9.5 | match |
| 2026-02-11 | 0 | wash_beta | -9.5 | session_force_flatten | session_force_flatten | -8.0 | 335.0 | 336.5 | 1.5 | match |
| 2026-02-24 | 0 | wash_beta | 9.5 | session_force_flatten | session_force_flatten | -4.0 | 741.0 | 727.5 | -13.5 | match |
| 2026-02-25 | 0 | wash_beta | -10.5 | session_force_flatten | session_force_flatten | -8.0 | 222.0 | 224.5 | 2.5 | match |
| 2026-03-05 | 0 | wash_beta | 0.5 | session_force_flatten | session_force_flatten | -8.0 | -208.0 | -216.5 | -8.5 | match |
| 2026-03-10 | 0 | wash_beta | 3.5 | session_force_flatten | session_force_flatten | -8.0 | -476.0 | -487.5 | -11.5 | match |
| 2026-03-11 | 0 | wash_beta | -8.5 | session_force_flatten | session_force_flatten | -6.0 | 710.0 | 712.5 | 2.5 | match |
| 2026-03-17 | 0 | wash_beta | -0.5 | session_force_flatten | session_force_flatten | -8.0 | 188.0 | 180.5 | -7.5 | match |
| 2026-03-18 | 0 | wash_beta | 16.5 | session_force_flatten | session_force_flatten | -8.0 | 315.0 | 290.5 | -24.5 | match |
| 2026-03-25 | 0 | wash_beta | -14.5 | session_force_flatten | session_force_flatten | -8.0 | -136.0 | -129.5 | 6.5 | match |
| 2026-04-01 | 0 | wash_beta | -0.5 | session_force_flatten | session_force_flatten | -7.0 | 375.0 | 368.5 | -6.5 | match |
| 2026-04-07 | 0 | wash_beta | -1.5 | session_force_flatten | session_force_flatten | -4.0 | 45.0 | 42.5 | -2.5 | match |
| 2026-04-08 | 0 | wash_beta | 0.5 | session_force_flatten | session_force_flatten | -8.0 | 428.0 | 419.5 | -8.5 | match |
| 2026-04-10 | 0 | wash_beta | 5.5 | session_force_flatten | session_force_flatten | -8.0 | 335.0 | 321.5 | -13.5 | match |
| 2026-04-14 | 0 | wash_beta | 1.5 | session_force_flatten | session_force_flatten | -8.0 | 341.0 | 331.5 | -9.5 | match |
| 2026-04-15 | 0 | wash_beta | -0.5 | session_force_flatten | session_force_flatten | -8.0 | 273.0 | 265.5 | -7.5 | match |
| 2026-04-16 | 0 | wash_beta | 0.5 | session_force_flatten | session_force_flatten | -8.0 | 318.0 | 309.5 | -8.5 | match |
| 2026-04-20 | 0 | wash_beta | -0.5 | session_force_flatten | session_force_flatten | -5.0 | -150.0 | -154.5 | -4.5 | match |
| 2026-04-21 | 0 | wash_beta | 2.5 | session_force_flatten | session_force_flatten | -3.0 | 341.0 | 335.5 | -5.5 | match |
| 2026-04-23 | 0 | wash_beta | -1.5 | session_force_flatten | session_force_flatten | -3.0 | -865.0 | -866.5 | -1.5 | match |
| 2026-04-24 | 0 | wash_beta | -18.5 | session_force_flatten | session_force_flatten | -8.0 | 956.0 | 966.5 | 10.5 | match |
| 2026-04-27 | 0 | wash_beta | -1.5 | session_force_flatten | session_force_flatten | -8.0 | -23.0 | -29.5 | -6.5 | match |
| 2026-05-04 | 0 | wash_beta | -12.5 | session_force_flatten | session_force_flatten | -8.0 | 642.0 | 646.5 | 4.5 | match |
| 2026-05-06 | 0 | wash_beta | -2.5 | session_force_flatten | session_force_flatten | -8.0 | -135.0 | -140.5 | -5.5 | match |
| 2026-05-07 | 0 | wash_beta | -4.5 | session_force_flatten | session_force_flatten | -8.0 | 42.0 | 38.5 | -3.5 | match |
| 2026-05-14 | 0 | wash_beta | -25.5 | session_force_flatten | session_force_flatten | -5.0 | -264.0 | -243.5 | 20.5 | match |
| 2026-05-21 | 0 | wash_beta | 3.5 | session_force_flatten | session_force_flatten | -5.0 | 594.0 | 585.5 | -8.5 | match |
| 2026-05-25 | 0 | wash_beta | 1.5 | session_force_flatten | session_force_flatten | -8.0 | 733.0 | 723.5 | -9.5 | match |
| 2026-05-27 | 0 | wash_beta | 1.5 | session_force_flatten | session_force_flatten | -7.0 | 347.0 | 338.5 | -8.5 | match |
| 2026-05-29 | 0 | wash_beta | 1.5 | session_force_flatten | session_force_flatten | -8.0 | 642.0 | 632.5 | -9.5 | match |
| 2026-06-01 | 0 | wash_beta | -0.5 | session_force_flatten | session_force_flatten | -2.0 | 657.0 | 655.5 | -1.5 | match |
| 2026-06-03 | 0 | wash_beta | -1.5 | session_force_flatten | session_force_flatten | -8.0 | 83.0 | 76.5 | -6.5 | match |
| 2026-06-09 | 0 | wash_beta | 28.5 | session_force_flatten | session_force_flatten | -8.0 | 1038.0 | 1001.5 | -36.5 | match |
| 2026-06-15 | 0 | wash_beta | 1.5 | session_force_flatten | session_force_flatten | -4.0 | -77.0 | -82.5 | -5.5 | match |
| 2026-06-18 | 0 | wash_beta | -11.5 | session_force_flatten | session_force_flatten | -4.0 | 270.0 | 277.5 | 7.5 | match |
| 2026-06-22 | 0 | wash_beta | -0.5 | session_force_flatten | session_force_flatten | -5.0 | 1022.0 | 1017.5 | -4.5 | match |
| 2026-06-29 | 0 | wash_beta | -0.5 | session_force_flatten | session_force_flatten | -1.0 | 760.0 | 759.5 | -0.5 | match |
