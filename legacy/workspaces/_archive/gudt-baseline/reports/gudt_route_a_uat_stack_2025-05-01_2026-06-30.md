# FT-018b Route A UAT stack — 2025-05-01..2026-06-30

## Spec (two independent legs)

### Leg 1 — Route A long (p0 only)
- Router: B′ + br5 p0-only veto
- Checkpoint: 15m sealed gross>0 + ext_open>5 → extend 60m
- Extension exit: **5m EMA9>EMA21 break** (fallback trail/stop)
- ft path: drive_low_struct unchanged

### Leg 2 — Distribution short (overlay)
- Gate: ext_open > 5
- Signal @ P0+10m: px < p0_entry AND BR < 0.42
- **Confirm @ P0+12m**: dump_atr ≤ −0.65 AND −0.35 ≤ slope2 ≤ 0
- Short stop: drive_high + 2, hold 60m

## Holdout / UAT ledger

| period | B′+br5 | Route A stack | Δ | flips | extend |
|--------|-------:|--------------:|--:|------:|-------:|
| 2025 H2 | +197 | +176 | -21 | 0 | 2 |
| 2026 H1 | +1360 | +1290 | -70 | 1 | 0 |
| UAT 2m | -8 | +298 | +305 | 1 | 1 |
| full | +1501 | +1781 | +280 | 2 | 4 |

**Full period:** net **+1781.4** · flip=2 · confirm_veto=6 · extend=4

## Day ledger

| day | path | long | short | net | hedge | confirm | route_a |
|-----|------|-----:|------:|----:|-------|---------|---------|
| 2025-05-02 | flow_turn+drive_low_struct | 28.0 | 0.0 | 28.0 | none | — | — |
| 2025-05-08 | flow_turn+drive_low_struct | 2.0 | 0.0 | 2.0 | none | — | — |
| 2025-05-12 | flow_turn+drive_low_struct | 43.14 | 0.0 | 43.14 | none | — | — |
| 2025-05-28 | flow_turn+drive_low_struct | -10.0 | 0.0 | -10.0 | none | — | — |
| 2025-06-03 | flow_turn+drive_low_struct | 79.0 | 0.0 | 79.0 | none | — | — |
| 2025-06-04 | flow_turn+drive_low_struct | 2.0 | 0.0 | 2.0 | none | veto | — |
| 2025-06-05 | p0+sealed | -5.0 | 0.0 | -5.0 | none | — | — |
| 2025-06-10 | p0+sealed | 84.0 | 0.0 | 84.0 | none | — | ext |
| 2025-06-17 | flow_turn+drive_low_struct | 31.0 | 0.0 | 31.0 | none | — | — |
| 2025-07-01 | flow_turn+drive_low_struct | 6.0 | 0.0 | 6.0 | none | — | — |
| 2025-07-03 | flow_turn+drive_low_struct | 23.0 | 0.0 | 23.0 | none | — | — |
| 2025-07-16 | p0+sealed | 48.0 | 0.0 | 48.0 | none | — | ext |
| 2025-07-30 | flow_turn+drive_low_struct | 22.0 | 0.0 | 22.0 | none | veto | — |
| 2025-08-05 | p0+sealed | -36.25 | 0.0 | -36.25 | none | — | — |
| 2025-08-07 | p0+sealed | -13.0 | 0.0 | -13.0 | none | veto | — |
| 2025-08-13 | flow_turn+drive_low_struct | 23.0 | 0.0 | 23.0 | none | — | — |
| 2025-08-21 | p0+sealed | -37.0 | 0.0 | -37.0 | none | — | ext |
| 2025-08-25 | flow_turn+drive_low_struct | 29.0 | 0.0 | 29.0 | none | — | — |
| 2025-08-29 | flow_turn+drive_low_struct | -9.0 | 0.0 | -9.0 | none | — | — |
| 2025-09-04 | p0+sealed | -36.7 | 0.0 | -36.7 | none | — | — |
| 2025-09-05 | flow_turn+drive_low_struct | -45.0 | 0.0 | -45.0 | none | — | — |
| 2025-09-08 | flow_turn+drive_low_struct | -30.0 | 0.0 | -30.0 | none | — | — |
| 2025-09-09 | p0+sealed | 15.0 | 0.0 | 15.0 | none | — | — |
| 2025-09-10 | flow_turn+drive_low_struct | 16.0 | 0.0 | 16.0 | none | — | — |
| 2025-09-11 | p0+sealed (veto) | -37.68 | 0.0 | -37.68 | none | — | — |
| 2025-09-12 | flow_turn+drive_low_struct | 46.0 | 0.0 | 46.0 | none | — | — |
| 2025-09-16 | flow_turn+drive_low_struct | -31.0 | 0.0 | -31.0 | none | — | — |
| 2025-09-23 | flow_turn+drive_low_struct | 34.0 | 0.0 | 34.0 | none | — | — |
| 2025-10-02 | p0+sealed | -5.0 | 0.0 | -5.0 | none | — | — |
| 2025-10-07 | p0+sealed | 42.33 | 0.0 | 42.33 | none | — | — |
| 2025-10-16 | flow_turn+drive_low_struct | 46.83 | 0.0 | 46.83 | none | — | — |
| 2025-10-21 | flow_turn+drive_low_struct | 22.0 | 0.0 | 22.0 | none | — | — |
| 2025-10-27 | p0+sealed | -48.75 | 0.0 | -48.75 | none | — | — |
| 2025-10-29 | flow_turn+drive_low_struct | 30.0 | 0.0 | 30.0 | none | — | — |
| 2025-11-04 | flow_turn+drive_low_struct | -19.0 | 0.0 | -19.0 | none | — | — |
| 2025-11-12 | flow_turn+drive_low_struct | 34.23 | 0.0 | 34.23 | none | — | — |
| 2025-11-17 | flow_turn+drive_low_struct | -13.0 | 0.0 | -13.0 | none | — | — |
| 2025-11-25 | flow_turn+drive_low_struct | -18.0 | 0.0 | -18.0 | none | — | — |
| 2025-11-27 | flow_turn+drive_low_struct | 34.0 | 0.0 | 34.0 | none | — | — |
| 2025-12-02 | flow_turn+drive_low_struct | -18.0 | 0.0 | -18.0 | none | — | — |
| 2025-12-03 | flow_turn+drive_low_struct | -42.0 | 0.0 | -42.0 | none | — | — |
| 2025-12-04 | flow_turn+drive_low_struct | 45.0 | 0.0 | 45.0 | none | — | — |
| 2025-12-08 | p0+sealed | 31.0 | 0.0 | 31.0 | none | — | — |
| 2025-12-10 | flow_turn+drive_low_struct | 3.0 | 0.0 | 3.0 | none | — | — |
| 2025-12-12 | flow_turn+drive_low_struct | -11.0 | 0.0 | -11.0 | none | — | — |
| 2025-12-19 | p0+sealed | -36.25 | 0.0 | -36.25 | none | — | — |
| 2025-12-22 | flow_turn+drive_low_struct | 21.0 | 0.0 | 21.0 | none | — | — |
| 2025-12-26 | flow_turn+drive_low_struct | 21.0 | 0.0 | 21.0 | none | — | — |
| 2025-12-29 | p0+sealed | 70.0 | 0.0 | 70.0 | none | — | — |
| 2026-01-02 | flow_turn+drive_low_struct | 9.0 | 0.0 | 9.0 | none | — | — |
| 2026-01-05 | p0+sealed | 71.7 | 0.0 | 71.7 | none | — | — |
| 2026-01-14 | flow_turn+drive_low_struct | 77.71 | 0.0 | 77.71 | none | — | — |
| 2026-01-22 | flow_turn+drive_low_struct | 38.0 | 0.0 | 38.0 | none | — | — |
| 2026-01-28 | flow_turn+drive_low_struct | 27.0 | 0.0 | 27.0 | none | — | — |
| 2026-02-03 | flow_turn+drive_low_struct | 52.0 | 0.0 | 52.0 | none | — | — |
| 2026-02-09 | flow_turn+drive_low_struct | 49.0 | 0.0 | 49.0 | none | — | — |
| 2026-02-10 | flow_turn+drive_low_struct | 45.61 | 0.0 | 45.61 | none | — | — |
| 2026-02-11 | p0+sealed | -5.0 | 0.0 | -5.0 | none | — | — |
| 2026-02-24 | p0+sealed | -57.86 | 0.0 | -57.86 | none | veto | — |
| 2026-02-25 | p0+sealed | -5.0 | 0.0 | -5.0 | none | — | — |
| 2026-03-05 | flow_turn+drive_low_struct | -58.0 | 0.0 | -58.0 | none | — | — |
| 2026-03-10 | flow_turn+drive_low_struct | 111.01 | 0.0 | 111.01 | none | — | — |
| 2026-03-11 | flow_turn+drive_low_struct | -31.0 | -71.0 | -102.0 | flip | pass | — |
| 2026-03-18 | flow_turn+drive_low_struct | 54.84 | 0.0 | 54.84 | none | — | — |
| 2026-03-25 | p0+sealed | -69.02 | 0.0 | -69.02 | none | — | — |
| 2026-04-01 | flow_turn+drive_low_struct | 62.0 | 0.0 | 62.0 | none | — | — |
| 2026-04-07 | flow_turn+drive_low_struct | 89.0 | 0.0 | 89.0 | none | — | — |
| 2026-04-08 | flow_turn+drive_low_struct | 89.91 | 0.0 | 89.91 | none | — | — |
| 2026-04-10 | flow_turn+drive_low_struct | -13.0 | 0.0 | -13.0 | none | veto | — |
| 2026-04-14 | flow_turn+drive_low_struct | 30.0 | 0.0 | 30.0 | none | — | — |
| 2026-04-15 | p0+sealed | 41.6 | 0.0 | 41.6 | none | — | — |
| 2026-04-20 | flow_turn+drive_low_struct | 9.0 | 0.0 | 9.0 | none | — | — |
| 2026-04-21 | flow_turn+drive_low_struct | 107.0 | 0.0 | 107.0 | none | — | — |
| 2026-04-23 | flow_turn+drive_low_struct | 238.0 | 0.0 | 238.0 | none | — | — |
| 2026-04-24 | p0+sealed | 161.29 | 0.0 | 161.29 | none | — | — |
| 2026-05-04 | p0+sealed | 46.0 | 0.0 | 46.0 | none | — | — |
| 2026-05-06 | flow_turn+drive_low_struct | 441.0 | 0.0 | 441.0 | none | — | — |
| 2026-05-07 | p0+sealed | -5.0 | 0.0 | -5.0 | none | — | — |
| 2026-05-14 | flow_turn+drive_low_struct | -37.0 | 0.0 | -37.0 | none | — | — |
| 2026-05-21 | p0+sealed | -5.0 | 0.0 | -5.0 | none | — | — |
| 2026-05-25 | p0+sealed | -94.02 | 0.0 | -94.02 | none | veto | — |
| 2026-05-29 | p0+sealed | -110.27 | 0.0 | -110.27 | none | — | — |
| 2026-06-01 | p0+sealed | 233.0 | 0.0 | 233.0 | none | — | ext |
| 2026-06-15 | flow_turn+drive_low_struct | -24.0 | 0.0 | -24.0 | none | — | — |
| 2026-06-18 | flow_turn+drive_low_struct | -110.0 | 0.0 | -110.0 | none | — | — |
| 2026-06-22 | flow_turn+drive_low_struct | 3.0 | 0.0 | 3.0 | none | — | — |
| 2026-06-29 | p0+sealed | -122.0 | 82.0 | -40.0 | flip | pass | — |
