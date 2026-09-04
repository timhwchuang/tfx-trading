# Phase 4 round-2 indicator census

Detector-only. Does not call `SetupA.decide`. Same IS window as round-1 blotter.
Join counts apply Setup A bias (`discount` long / `premium` short).
Interpretation: [FINDINGS.md](FINDINGS.md).

- git: `14c56c2fc8aa19363e50cc90bd12a60a62a8c34b`
- range: `2025-03-03` → `2025-11-06`
- day 5m: 10176 across 171 sessions
- arm window (09:15–13:40, skip settlement): 8559

## Onsets (state first becomes swept/taken)

| level | sweep_onset | taken_onset | live_swept_bars | live_taken_bars |
|---|---:|---:|---:|---:|
| pdh | 50 | 187 | 836 | 14781 |
| pdl | 48 | 131 | 1005 | 11055 |
| prev_night_high | 52 | 185 | 956 | 18027 |
| prev_night_low | 42 | 125 | 1041 | 12336 |

## Structure events (unique prints)

```json
{
  "choch|bullish|internal": 752,
  "choch|bearish|internal": 770,
  "bos|bearish|internal": 510,
  "bos|bullish|internal": 677
}
```

## FVG formed (unique)

```json
{
  "ge_15": 1354,
  "ge_20": 880,
  "ge_30": 411,
  "any": 7558
}
```

## Setup A join in arm window (bar counts / unique sweeps)

Bar counts are 5m closes where the live swept level still qualifies. Unique is `(date, side, interact_ts)`.

```json
{
  "bars": {
    "bars": 8559,
    "long_swept": 243,
    "short_swept": 272,
    "long_any_event": 87,
    "short_any_event": 166,
    "long_choch": 87,
    "short_choch": 155,
    "long_external": 0,
    "short_external": 0,
    "long_fvg15": 52,
    "short_fvg15": 104,
    "long_fvg20": 45,
    "short_fvg20": 89,
    "long_fvg30": 29,
    "short_fvg30": 63
  },
  "unique_sweeps": {
    "short_swept": 30,
    "short_any_event": 17,
    "short_choch": 16,
    "short_fvg15": 12,
    "short_fvg20": 11,
    "long_swept": 21,
    "long_any_event": 10,
    "long_choch": 10,
    "short_fvg30": 8,
    "long_fvg15": 7,
    "long_fvg20": 6,
    "long_fvg30": 3
  }
}
```
