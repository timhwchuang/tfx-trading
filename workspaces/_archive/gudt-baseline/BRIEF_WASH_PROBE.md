# FT-018b Wash Probe (exploratory)

Wash labels: `momentum_clean` | `wash_fake` | `wash_real` | `ambiguous`

Entry keys: `p0`, `flow_turn`, `reclaim_br`, `p0_quality`  
Exit keys: `sealed`, `wash_struct`, `drive_low_struct`, `flow_bailout`, `momentum_tail`, `momentum_tail_trail`

Panel days: 2026-01-05, 2026-02-09, 2026-02-10, 2026-05-29, 2026-04-21, 2026-03-10

Defaults: min_wash_k=0.25, br_min=0.55, delta_br_min=0.12, break_eps=0.05

**Research seal**: `SEAL_FT018b_B_PRIME.md` — Rule B′ + drive_low (holdout A pass, **2026-06 fail**).

Does **not** overwrite sealed `gate_report.md` or `counterfactual_gudt_train.json`.
