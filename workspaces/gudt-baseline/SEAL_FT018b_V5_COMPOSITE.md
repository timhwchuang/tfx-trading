# SEAL — FT-018b V5 Composite (`ft018b_v5_composite`)

> **Status**: RESEARCH SEAL · **2026-06-30**  
> **Does not replace** sealed B′ (`SEAL_FT018b_B_PRIME.md`) or official `gate_report.md` champion `gk1_rt0p4`.

## Champion spec

| Field | Value |
|-------|-------|
| ID | `ft018b_v5_composite` |
| Long leg | Rule **B′** (unchanged) |
| **br5 veto** | `pre_break_br_p0_only=True` — veto **p0 path only** when BR@break−5m < 0.35; ft winners unaffected |
| **Flip gate** | `flip_min_ext_open=5.0` — distribution short only when `(drive_high − open_0845) / ATR > 5` |
| Short leg | P0+10m: `px < p0_entry AND BR < 0.42` → exit long + short @ signal, stop `dh+2` |

### vs V4 composite

| Rule | V4 | V5 |
|------|----|----|
| br5 < 0.35 | skip **entire day** | skip **p0 pick only** (fallback early ft if any) |
| distribution flip | always when signal | only when `ext_open > 5×ATR` |

## Code / artifacts

| Path | Role |
|------|------|
| `apps/trading-app/src/reporting/gudt_wash_probe.py` | `BPrimeCompositeParams`, `apply_b_prime_composite_day`, I/O reuse |
| `apps/trading-app/src/scripts/ft018_gudt_composite.py` | `--preset v5`, `--from-csv` |
| `workspaces/gudt-baseline/reports/gudt_wash_probe_merged_202505_202606.csv` | Merged probe matrix |
| `workspaces/gudt-baseline/reports/gudt_bprime_composite_v5_2025-05-01_2026-06-30.md` | Full pick ledger |

### I/O optimizations (2026-06-30)

- `_load_day_context` reuses GDC tick cache (no second `iter_replay_ticks` pass)
- `DayWashContext.session_bars` embedded at load; `build_session_bars_by_day` reuses ctx
- `read_probe_csv` + `--from-csv` skips full probe replay for composite runs

## Validation ledger (merged CSV, 89 GUDT days)

| Period | B′ n/net | V5 n/skip/flip/net | Δ vs B′ | V4 net (ref) |
|--------|----------|-------------------|---------|--------------|
| **Full 2025-05..2026-06** | 76 / **+126** | 69 / 20 / 7 / **+551** | **+425** | +337 |
| Aug–Oct 2025 | 23 / +30 | 21 / 8 / 1 / **+18** | −12 | −162 |
| **June 2026** | 6 / **−362** | 5 / 2 / 1 / **+73** | **+435** | +73 |

### Monthly (B′ → V5)

| Month | B′ | V5 | flips |
|-------|-----|-----|------:|
| 2025-08 | +17 | −0 | 1 |
| 2025-09 | −69 | −69 | 0 |
| 2025-10 | +82 | +87 | 0 |
| 2026-03 | −67 | +8 | 0 |
| 2026-06 | **−362** | **+73** | 1 (6/29) |

## Pass / fail vs B′ seal criteria

| Gate | Result |
|------|--------|
| Full-period net > B′ | **PASS** (+551 vs +126) |
| Holdout A 2025 H2 alone | B′ +271 unchanged (V5 does not skip ft days) |
| June 2026 rescue | **PASS** (br5 p0 skip + gated flip on 6/29) |
| Replace B′ as default long | **HOLD** — V5 is composite overlay; B′ router still sealed |

## Notes

- V5 fixes V4's Aug–Oct ft-winner destruction (no whole-day br5 skip).
- Flip count drops 13 → 7 vs V4; remaining flips are high-ext_open regime days.
- Re-run: `python3 apps/trading-app/src/scripts/ft018_gudt_composite.py --preset v5 --from-csv workspaces/gudt-baseline/reports/gudt_wash_probe_merged_202505_202606.csv`
