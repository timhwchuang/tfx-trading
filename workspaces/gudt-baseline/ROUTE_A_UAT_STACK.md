# FT-018b Route A UAT Stack — Research Spec

> **Status**: UAT candidate · 2026-06-30  
> **Does not replace** `SEAL_FT018b_B_PRIME.md` or `gate_report.md`.

## ID

`ft018b_route_a_uat_stack`

## Two independent legs

### Leg 1 — Route A long (trend extension)

| Field | Value |
|-------|-------|
| Router | B′ + **br5 p0-only** veto (`pre_break_br < 0.35` → skip p0, fallback ft) |
| p0 default | sealed 15m + BE + TP3 |
| Checkpoint | `ext_open > 5` AND 15m `gross > 0` (would horizon exit) |
| Extension | 60m, **no BE**, **5m EMA9>EMA21 break** (+ hard stop / trail backup) |
| ft | `drive_low_struct` unchanged |

### Leg 2 — Distribution short (separate story)

| Field | Value |
|-------|-------|
| Gate | `ext_open > 5` |
| Signal | P0+10m: `px < p0_entry` AND `BR < 0.42` → exit long |
| Confirm | P0+12m: `dump_atr ≤ −0.65` AND `−0.35 ≤ slope2 ≤ 0` |
| Short | entry @ confirm_px, stop `drive_high + 2`, hold 60m |

`dump_atr` = (signal_px − p0_entry) / ATR  
`slope2` = (confirm_px − signal_px) / ATR over 2 minutes

## Code

| Path | Role |
|------|------|
| `apps/trading-app/src/reporting/gudt_route_a_exit.py` | Checkpoint + EMA extension sim |
| `apps/trading-app/src/reporting/gudt_route_a_stack.py` | Stack composer |
| `apps/trading-app/src/reporting/gudt_wash_probe.py` | `DistributionHedgeParams.confirm_*` |
| `apps/trading-app/src/scripts/ft018_gudt_route_a_stack.py` | CLI + holdout report |

## Reproduce

```bash
cd /path/to/future
PYTHONPATH="apps/trading-app/src:packages/trading-engine/src:packages/strategies/vwap-momentum/src:packages/trading-backtest/src" \
  python3 apps/trading-app/src/scripts/ft018_gudt_route_a_stack.py \
  --from 2025-05-01 --to 2026-06-30
```

Report: `workspaces/gudt-baseline/reports/gudt_route_a_uat_stack_2025-05-01_2026-06-30.md`

## Validation ledger (merged CSV)

| Period | B′+br5 | Route A stack | Δ | flips | extend |
|--------|-------:|--------------:|--:|------:|-------:|
| 2025 H2 | +180 | +159 | −21 | 0 | 2 |
| 2026 H1 | +236 | +236 | 0 | 0 | 0 |
| **UAT 2m (2026-05..06)** | −412 | **−106** | **+305** | 1 | 1 |
| Full | +333 | **+683** | +350 | 1 | 4 |

### UAT 2m notes

- **6/29**: structural flip confirm **pass** → net −40 (vs B′ −202, vs no-flip Route A −202)
- **6/01**: Route A extend +233 (EMA5 capture)
- Remaining pain: **ft** days 6/15, 6/18 (−134 combined) — not addressable by distribution flip
- Confirm **veto** 6 days (4/10 bounce, 5/25 capitulation, etc.)

## UAT pass criteria (proposed)

1. UAT 2m net > B′+br5 baseline  
2. 2026 H1 not worse than B′+br5 (no H1 regression)  
3. No flip unless confirm passes (structural, no fixed pts)  
4. Worst day not worse than sealed B′ worst without flip

## Live wiring (TODO)

- [ ] Promote `DistributionHedgeParams.confirm_*` to strategy overlay config
- [ ] Route A checkpoint state machine in p0 exit handler
- [ ] 5m EMA from live 1m kbars (not resampled stride)
- [ ] Paper UAT 2026-07 .. 2026-08 two months
