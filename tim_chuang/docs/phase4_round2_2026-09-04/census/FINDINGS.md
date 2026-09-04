# Indicator census findings (IS 2025-03-03 → 2025-11-06)

Detector-only. `SetupA.decide` was not called. Bias filter matches Setup A
(`discount`→long, `premium`→short). Join uses `_swept_level` / `preferred_event`.
Raw JSON: [census.json](census.json).

## Verdict

**Detector prints. External does not. Join is rare. Fills are rarer.**
**v1 shorts do not have a risk model: R is identically `stop_buffer`.**

Do not loosen sweep. Do not treat `min_r_points=15` as a TMF noise floor.
Scale card: [SCALE_CARD.md](SCALE_CARD.md).
Desk card (before `decide()`): [TMF_DESK_CARD.md](../../TMF_DESK_CARD.md).

## Detector is not silent

| Print | Count on this tape |
|---|---:|
| CHoCH bullish internal | 752 |
| CHoCH bearish internal | 770 |
| BOS bullish internal | 677 |
| BOS bearish internal | 510 |
| **any `scope=external`** | **0** |
| FVG any size | 7,558 |
| FVG ≥15 / ≥20 / ≥30 | 1,354 / 880 / 411 |
| PDH/PDL/night sweep **onset** | 50 / 48 / 52 / 42 |
| same levels **taken** onset | 187 / 131 / 185 / 125 |

`require_external=True` → 0 intents in round 1 because **the detector never
emits external events on this IS tape**, not because Setup A failed to join
them. Session-high/low BOS as “external” is a dead print here.

Taken onsets are ~3–4× sweep onsets. Live-taken bars dwarf live-swept bars
(PDH 14,781 taken vs 836 swept). Most of the day the level is already `taken`.
That is why round-1 “92% `no_sweep`” is the filter working: Setup A refuses
`taken` (trend continuation).

## Setup A join (arm window 09:15–13:40, skip settlement)

171 day sessions, 8,559 5m closes. **Unique** = `(date, side, interact_ts)`.

| Gate | Unique long | Unique short | Unique total |
|---|---:|---:|---:|
| bias + live swept | 21 | 30 | 51 |
| + any event | 10 | 17 | 27 |
| + CHoCH | 10 | 16 | 26 |
| + FVG ≥15 | 7 | 12 | 19 |
| + FVG ≥20 | 6 | 11 | 17 |
| + FVG ≥30 | 3 | 8 | 11 |

FVG unique rows are **not nested under event** (census counts live FVG on a
swept ident even with no CHoCH/BOS). Canonical tradable join for A′ is the
scale card: **17** = bias + sweep + any event + FVG≥15 (5 long / 12 short).
The two extra census longs (7 vs 5) have FVG but no structure event.

Round-1 mid combo (`min_points=20`) placed 38 intents and **filled 5**. The drop
to 5 fills is **limit fill / one-position / cancel**, not a missing CHoCH.
Requiring CHoCH (A′ step 4) removes ~1 unique short and zero longs.

Even if every scale-card join filled, **17 < `MIN_IS_TRADES=30`**. Stop
geometry will not manufacture sample size. Keep the gate; this year of day-only
Setup A cannot elect. Full year (~1.4× IS) still likely < 30.

## Scale card (same IS tape, 194,149 × 1m)

Recomputed, not copied. Day 1m P50/P90 = 10/23; arm-window 10/21; open 19/39;
5m range 25/55; Wilder ATR(14) chained 30/48; day H−L 243/421; round-trip 4.9 pts
at median close 22585 (4.92 pts at 23000).

First unique join (bias+sweep+event+FVG≥15): **17** (5 long / 12 short).
All 12 shorts have v1 R **exactly 3**. A′ sweep-extreme R P50 = 119 (long 162 /
short 105), min 29, none < 15. So `min_r=15` is a cost kill-switch that will not
fire on this geometry; 2R ≈ 238 vs day range P50 243.

A slightly larger “23 first-complete” count without the same unique+bias rules
does not change the identity: shorts pay `stop_buffer`, not sweep-reversal.

## What this does *not* say

- It does not say the 17 joined setups have edge.
- Bar counts (e.g. 272 `short_swept`) are **not** trade counts.
- Chained ATR 30/48 vs an earlier 27/47 quote is the same order of magnitude,
  not a 3-point stop.

## Next (roadmap Setup A′ step 2)

Stop geometry is in `setup_a.py` (`_structural_stop`). Next: cost-floor kill
(`min_r_points` / `r_below_floor`, still not implemented) + 8 timestamps /
~20 days conservative smoke. Report A′ R, 13:40 flatten share vs 2R.
No 432-cell grid.
