# GUDT Wash Grid vs Sealed Baseline

- range: 2025-12-01 ~ 2026-05-31
- **sealed P0 baseline** (probe `p0+sealed`): n=30 · net_total=**216.41**
- wash grid best: `em_p0_mw0p25_dbr0p12_beoff_ss_atr_h900_ta2_td0p6_tp3` net_total=**108.1**
- params swept: 704
- wash grid **does not beat** sealed P0 on this exploratory pass (tune entry/exit thresholds next)

## Wash label breakdown (probe p0+sealed)

| label | n | net_total |
|-------|---|-----------|
| momentum_clean | 28 | +326.58 |
| wash_real | 2 | -110.17 |

Full JSON: `counterfactual_gudt_wash_grid_202512_202605.json`
