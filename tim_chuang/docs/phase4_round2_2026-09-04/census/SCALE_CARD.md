# TMFR1 IS scale card

Measured from tape. Numbers are the grid's licence to exist, not a vibe.
Recite before `decide()`: [TMF_DESK_CARD.md](../../TMF_DESK_CARD.md).

- git: `14c56c2fc8aa19363e50cc90bd12a60a62a8c34b`
- range: `2025-03-03` → `2025-11-06`
- n_1m: 194149; median day close: 22585.0
- round-trip at that close: **4.9 pts**

## Three layers (do not mix)

| Layer | Tape measure | P50 | P90 | Role |
|---|---|---:|---:|---|
| Cost floor | round-trip | 4.9 | — | R below this is not a trade |
| Noise 1m (day) | high−low | 10.0 | 23.0 | ≥5 pts share 90% |
| Noise 1m (09:15–13:40) | high−low | 10.0 | 21.0 | arm window |
| Noise 1m (08:50–09:14) | high−low | 19.0 | 39.0 | no_trade_before is right |
| Decision 5m | high−low | 25.0 | 55.0 | one decide bar |
| ATR(14) day 5m chained | Wilder | 30.25 | 48.15 | |
| ATR(14) day 5m reset | Wilder last/day | 21.26 | 30.8 | |
| Session range | day 1m H−L | 243.0 | 421.0 | 2R must fit before 13:40 |

## Session clock (1m high−low)

| Window | n | P50 | P90 | Remember |
|---|---:|---:|---:|---|
| open_0850_0915 | 4275 | 19.0 | 39.0 | fattest 1m; no_trade_before |
| am_0915_1030 | 12807 | 14.0 | 28.0 | fattest tradable; easiest to stop out |
| mid_1100_1300 | 20409 | 8.0 | 16.0 | thin; limits often unfilled |
| close_1330_1345 | 2724 | 8.0 | 18.0 | flatten/settlement; do not wait for 2R |
| night | 142325 | 6.0 | 15.0 | thinner 1m; prev_night still feeds day Setup A |

## v1 vs A′ R on first joined setups (FVG≥15, buffer=3)

- unique joins: **17** (long 5 / short 12)
- shorts with v1 R exactly = 3: **12**
- v1 R P50: 3.0
- A′ sweep-extreme R P50: 119.0 (long 162.0 / short 105.0)
- A′ R min: 29.0; below min_r=15: 0
