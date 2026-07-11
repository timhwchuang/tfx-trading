# GUDT execution parity — spot-check log

`--append-spot-log` on `ft021_execution_parity.py` appends rows here.

| Date run | Command | Months / slice | n (CF/kernel) | Net: cf / kernel / Δ | PASS/FAIL | Notes |
|----------|---------|----------------|---------------|----------------------|-----------|-------|
| 2026-07-01 | `--slice UAT_2m` | UAT_2m | 13/13 | cf=362.71 kernel=-28.0 Δ=-390.71 | PASS | Primary UAT gate; kernel net incl. friction |
| 2026-07-01 | `--months 2026-04` | 2026-04 | 10/10 | (see execution_parity_2026-04.json) | PASS | Holdout month |
| 2026-07-01 | `--months 2026-03` (ioc=6) | 2026-03 | 6/6 | cf=-33.17 kernel=-5.5 Δ=27.67 | PASS | after ioc_slippage_points: 6 |
| 2026-07-01 | `--from 2026-01-01 --to 2026-06-30` | 2026 H1 | 40/40 | cf=1551.5 kernel=653.0 Δ=-898.5 | PASS | fast-path + event jump |
| 2026-07-01 | `--months 2025-11` | 2025-11 | 5/5 | cf=43.23 kernel=47.0 Δ=3.77 | PASS | holdout spot audit |

Legacy failures (pre ioc=6 / pre hull-fix): 2026-02-25, 2026-03-18 entry IOC miss — resolved with ioc=6.
