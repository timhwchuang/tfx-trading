# SEAL — FT-018b Rule B′ (`bprime_v10_dl`)

> **Status**: SEALED (FT-018b research line) · **2026-06-30**  
> **Does not replace** official `gate_report.md` champion `gk1_rt0p4_ksl1p25_be0p75_ta2_td0p6_tp3`.

## Champion spec

| Field | Value |
|-------|-------|
| ID | `ft018b_bprime_v10_dl` |
| Entry | Rule **B′** (see below) |
| Exit (ft path) | `drive_low_struct` — stop = `drive_low − 2`, BE off, hold 900s |
| Exit (p0 path) | `sealed` — BE 0.75×ATR, k_sl 1.25, trail 2.0/0.6, TP 3.0 |
| Wash tune | `min_wash_k=0.25`, `br_min=0.55`, `delta_br_min=0.12`, `break_eps=0.05` |

### Rule B′ (entry router)

```
若當日有 flow_turn 且 flow_turn_ts < p0_ts:
  若 V10 veto → p0 + sealed
  否則 → flow_turn + drive_low_struct
否則:
  → p0 + sealed

若僅有 flow_turn（無 p0）:
  若 1.0 < dist_dh_atr < 3.0 → skip（不交易）
  否則 → flow_turn + drive_low_struct
```

### V10 veto（有 p0 時）

```
dist_dh_atr = (drive_high − entry_px) / ATR
ft_min = 開盤後分鐘數（自 09:45 BREAK_START）
veto = dist_dh_atr > 1.0 AND ft_min > 15
```

## Code / artifacts

| Path | Role |
|------|------|
| `apps/trading-app/src/reporting/gudt_wash_probe.py` | `rule_pick_for_day`, `_ft_veto_v10`, `summarize_rule` |
| `apps/trading-app/src/scripts/ft018_gudt_rule_b.py` | Matrix backtest CLI |
| `workspaces/gudt-baseline/reports/gudt_wash_rule_matrix_202505_202605.md` | Tune + holdout A |

## Validation ledger

| Period | n | **B′+dl** | Rule B+dl | p0+sealed | Pass? |
|--------|--:|----------:|----------:|----------:|:-----:|
| Tune 2025-05～2026-05 | 83 | **+1714** | +1296 | +337 | — |
| Holdout A 2025 H2 | 40 | **+271** | −134 | +120 | **YES** |
| Holdout A 2026 H1 | 33 | **+1360** | +1346 | +150 | YES |
| **Holdout B 2026-06** | **6** | **−362** | −429 | −390 | **NO** |

### Holdout B — 2026-06 day ledger

| day | path | net |
|-----|------|----:|
| 2026-06-01 | p0+sealed | +90 |
| 2026-06-09 | p0+sealed | −118 |
| 2026-06-15 | flow_turn+dl | −24 |
| 2026-06-18 | flow_turn+dl | −110 |
| 2026-06-22 | flow_turn+dl | +3 |
| 2026-06-29 | p0+sealed | −202 |

- Skipped vs B: **2026-06-03** ft (−67) — veto 1–3 ATR zone, no p0  
- GUDT qualifying days in cache: **7** (21 tick files; 14 non-GUDT / no entry)

## Gate verdict

| Criterion | Result |
|-----------|--------|
| Holdout A (2025 H2) net > 0 | **PASS** (+271) |
| Holdout B (2026-06) net > 0 | **FAIL** (−362) |
| Beat p0+sealed on holdout B | **FAIL** (−362 vs −390, marginal) |
| Replace `gk1_rt0p4` in gate_report | **NO** |

**Conclusion**: B′ is the best FT-018b composite found to date on tune + holdout A, but **2026-06 invalidates production seal**. Keep as documented research champion; production remains `gk1_rt0p4` + sealed exit.

## Reproduce

```bash
cd apps/trading-app
PYTHONPATH=src:../../packages/trading-engine/src:../../packages/strategies/vwap-momentum/src:../../packages/trading-backtest/src \
  python3 src/scripts/ft018_gudt_rule_b.py --from 2026-06-01 --to 2026-06-30 \
  --out-md workspaces/gudt-baseline/reports/gudt_wash_holdout_202606.md
```
