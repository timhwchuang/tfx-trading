# GUDT Rule Matrix 2025-05-01..2026-06-30

| period | rule | ft_exit | hedge | n | ft | veto | flip | net | ΔB′ | mean | WR% | p0+sealed |
|--------|------|---------|-------|---|----|------|------|-----|-----|------|-----|-----------|
| ALL | B_dl | drive_low_struct | — | 106 | 75 | 0 | 0 | 867.37 | — | 8.18 | 53.8 | -53.25 |
| ALL | B_bailout | flow_bailout | — | 106 | 75 | 0 | 0 | 427.37 | — | 4.03 | 45.3 | -53.25 |
| ALL | Bprime_dl | drive_low_struct | — | 89 | 57 | 1 | 0 | 1352.69 | — | 15.2 | 59.6 | -53.25 |
| ALL | Bprime_bailout | flow_bailout | — | 89 | 57 | 1 | 0 | 985.69 | — | 11.08 | 50.6 | -53.25 |
| ALL | D_reclaim | flow_bailout | — | 106 | 62 | 0 | 0 | -130.06 | — | -1.23 | 38.7 | -53.25 |
| ALL | Bprime_dl_hedge | drive_low_struct | distribution_short | 89 | 57 | 1 | 15 | 1402.52 | +49.83 | 15.76 | 59.6 | -53.25 |
| H2_holdout | B_dl | drive_low_struct | — | 52 | 39 | 0 | 0 | -134.17 | — | -2.58 | 51.9 | 120.39 |
| H2_holdout | B_bailout | flow_bailout | — | 52 | 39 | 0 | 0 | -229.17 | — | -4.41 | 46.2 | 120.39 |
| H2_holdout | Bprime_dl | drive_low_struct | — | 40 | 26 | 1 | 0 | 271.15 | — | 6.78 | 60.0 | 120.39 |
| H2_holdout | Bprime_bailout | flow_bailout | — | 40 | 26 | 1 | 0 | 214.15 | — | 5.35 | 55.0 | 120.39 |
| H2_holdout | D_reclaim | flow_bailout | — | 52 | 34 | 0 | 0 | -343.76 | — | -6.61 | 38.5 | 120.39 |
| H2_holdout | Bprime_dl_hedge | drive_low_struct | distribution_short | 40 | 26 | 1 | 7 | 160.76 | -110.39 | 4.02 | 57.5 | 120.39 |
| H1_2026 | B_dl | drive_low_struct | — | 44 | 29 | 0 | 0 | 917.79 | — | 20.86 | 54.5 | -240.39 |
| H1_2026 | B_bailout | flow_bailout | — | 44 | 29 | 0 | 0 | 545.79 | — | 12.4 | 40.9 | -240.39 |
| H1_2026 | Bprime_dl | drive_low_struct | — | 39 | 24 | 0 | 0 | 997.79 | — | 25.58 | 59.0 | -240.39 |
| H1_2026 | Bprime_bailout | flow_bailout | — | 39 | 24 | 0 | 0 | 660.79 | — | 16.94 | 43.6 | -240.39 |
| H1_2026 | D_reclaim | flow_bailout | — | 44 | 22 | 0 | 0 | 244.95 | — | 5.57 | 38.6 | -240.39 |
| H1_2026 | Bprime_dl_hedge | drive_low_struct | distribution_short | 39 | 24 | 0 | 7 | 1147.01 | +149.22 | 29.41 | 61.5 | -240.39 |

## Rule definitions

- **B**: `flow_turn_ts < p0_ts` → flow_turn + exit; else p0 + sealed
- **B'**: B + V10 veto → p0 + sealed if p0 exists; skip ft-only in 1–3 ATR zone
- **D**: early ft → reclaim_br + wash_struct; else p0 + sealed
- **B'+hedge_distribution_short** (counter-design v2): B' long; on P0+10min with px < P0 entry and BR < 0.42, **exit long** at signal and **flip short** (stop `drive_high + 2.0`). Not an overlay — long is closed first.

## Entry×exit reference

- `flow_turn+drive_low_struct`: n=103 net_total=1322.29
- `flow_turn+flow_bailout`: n=103 net_total=887.69
- `flow_turn+momentum_tail`: n=103 net_total=-501.99
- `flow_turn+momentum_tail_trail`: n=103 net_total=-491.96
- `flow_turn+sealed`: n=103 net_total=-62.74
- `flow_turn+wash_struct`: n=103 net_total=-309.69
- `p0+drive_low_struct`: n=67 net_total=13.32
- `p0+flow_bailout`: n=67 net_total=135.32
- `p0+momentum_tail`: n=67 net_total=347.48
- `p0+momentum_tail_trail`: n=67 net_total=306.13
- `p0+sealed`: n=67 net_total=-53.25
- `p0+wash_struct`: n=67 net_total=-182.83
- `p0_quality+drive_low_struct`: n=7 net_total=97.7
- `p0_quality+flow_bailout`: n=7 net_total=-88.3
- `p0_quality+momentum_tail`: n=7 net_total=-61.88
- `p0_quality+momentum_tail_trail`: n=7 net_total=-61.88
- `p0_quality+sealed`: n=7 net_total=-36.27
- `p0_quality+wash_struct`: n=7 net_total=-11.27
- `reclaim_br+drive_low_struct`: n=50 net_total=119.45
- `reclaim_br+flow_bailout`: n=50 net_total=584.85
- `reclaim_br+momentum_tail`: n=50 net_total=214.0
- `reclaim_br+momentum_tail_trail`: n=50 net_total=280.14
- `reclaim_br+sealed`: n=50 net_total=209.22
- `reclaim_br+wash_struct`: n=50 net_total=62.82

