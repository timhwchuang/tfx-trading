# A′ funnel + limit fill rate (not go/no-go)

Measurement only. One conservative hi-freq cell on the IS tape.
This does **not** elect parameters and is **not** a go/no-go.
Detector unique joins (layer A) are not the fill-rate denominator.
Headline is **n_spells / n_fills**. Round-1's 38 was every-5m `intents_emitted`.

v1 hi-freq `entry_stopped`×4 / stop×3 / target×1 / flatten×0 is **not** an A′ target.
That cell used nearer-stop + `max_hold=12`. A′ smoke on the same eight dates is
already stop×3 / flatten×5 / no `entry_stopped`. Wider structural R (scale card
min 29, P50 119) and `max_hold=10000` push deaths to 13:40.
**flatten≠0 is not a broker bug.**

- git: `57fb0b5096b2d7615aa0d18de737754f8494ba9e`
- range: `2025-03-03T08:46:00` → `2025-11-06T23:59:00`
- n_1m: 194149
- fill_mode: `conservative`

## Cell

- entry_price: `top`
- min_points: 15.0
- stop_buffer: 3.0 (pad)
- take_profit: `2R`
- require_external: False
- min_r_points: 15.0

## Layer A — detector unique `(date, side, interact_ts)`

Nested join: bias + sweep + event + FVG≥15 (same rule as the scale card's 17).
Census FVG rows are not nested under event; those extra longs are not here.
Nested CHoCH+FVG≥15 is computed on this tape, not assumed from the event layer.

- nested any-event + FVG≥15: **17** (long 5 / short 12)
- nested CHoCH + FVG≥15: **16** (long 5 / short 11)
- chosen FVG vs sweep: same 5m 0 / next 5m bar 0 / later 17
- shadowed impulse (same/next existed, latest-wins picked later): 0

CHoCH barely moves unique (17→16). same+next = 0+0, shadowed = 0.
That is the 3b number: latest-wins FVG on the sweep bar or the next 5m
in the **same session**. Hard-cutting impulse to same/next would keep
only those buckets; later joins drop out first — not CHoCH.
Night 15:05 is not the day session's next 5m.

## Layer B — decide() spells + conservative fill

A spell is one arm until fill or death. Re-arm after cancel is a second spell.
13:40 unfilled is broker **expire** (no cancel intent). `fill_rate = n_fills / n_spells`.
Nested unique joins are not `n_spells`: occupancy, invalid stop, tick rounding,
and a missing sweep bar sit between detector and arm. Scale-card `min_r=15` kills 0
on this geometry, so that drop is not the cost floor.

- n_spells: **42**
- n_fills: **8** (n_fills == n_result_trades == 8)
- fill_rate: **0.190**
- cancel_thesis: 32
- unfilled_flatten (expire at flatten, no cancel): 2
- still_open: 0
- raw 5m arm-closes (appendix; round-1 38 was this kind of count): 42

Fill exit reasons (A′ trades, not v1):

- entry_stopped: 0
- stop: 3
- target: 0
- flatten: 5

Do not read n or fill rate as edge. CHoCH / impulse FVG are **not** in `decide()`.
A′ day-session elect on this geometry is **closed**. Do not implement 3b
to keep sample, and do not open a second-round grid.
