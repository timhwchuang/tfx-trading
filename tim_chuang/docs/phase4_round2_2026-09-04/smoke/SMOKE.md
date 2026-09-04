# A′ cost-floor smoke (not go/no-go)

Measurement only. One conservative cell, eight v1 hi-freq **calendar** dates.
This does **not** elect parameters and is **not** a go/no-go. n≪30 is expected.
If many trades flatten at 13:40 before 2R, that is the scale card (2R ≈ day-range P50 243), not a cost-floor bug.

- git: `fc3d83d625fde5b41a1838181d2fe077e76dac81`
- range: `2025-05-07T00:00:00` → `2025-09-16T23:59:00`
- n_1m: 106903
- fill_mode: `conservative`

## Cell (hi-freq blotter alignment; stop is A′)

- entry_price: `top`
- min_points: 15.0 (not config default 20)
- stop_buffer: 3.0 (pad, not R)
- take_profit: `2R`
- require_external: False
- min_r_points: 15.0 (3× round-trip, not noise)

## Aggregates

- n_trades (window): 8
- n_trades on 8 dates: 8
- flatten share (window): 0.625
- R min / P50 (window): 29.00 / 70.00
- r_below_floor unique `(date, side)`: 0
- r_below_floor raw 5m closes: 0

## Scorecard (8 v1 fill dates)

A′ stops will not replay the v1 blotter rows. `no_trade` is a valid outcome.

| date | n | side | reason | R | 2R | day H−L | 2R > H−L |
|---|---:|---|---|---:|---:|---:|---|
| 2025-05-14 | 1 | short | stop | 69.00 | 138.00 | 204.00 | no |
| 2025-05-15 | 1 | short | stop | 62.00 | 124.00 | 133.00 | no |
| 2025-05-26 | 1 | short | flatten | 119.00 | 238.00 | 183.00 | yes |
| 2025-07-09 | 1 | short | stop | 29.00 | 58.00 | 323.00 | no |
| 2025-07-15 | 1 | long | flatten | 322.00 | 644.00 | 365.00 | yes |
| 2025-07-21 | 1 | long | flatten | 68.00 | 136.00 | 129.00 | yes |
| 2025-08-15 | 1 | long | flatten | 162.00 | 324.00 | 195.00 | yes |
| 2025-09-15 | 1 | short | flatten | 71.00 | 142.00 | 179.00 | no |

## Appendix (other fills in the load window)

No other fills in the load window.

Do not read n or flatten share as edge.
A′ day-session elect is a dead end; this smoke is not a license to grid.
