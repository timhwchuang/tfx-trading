# GUDT Rule Matrix 2025-05-01..2026-05-31

| period | rule | ft_exit | n | ft_days | veto | net | mean | WR% | p0+sealed |
|--------|------|---------|---|---------|------|-----|------|-----|-----------|
| ALL | B_dl | drive_low_struct | 99 | 71 | 0 | 1296.08 | 13.09 | 55.6 | 336.8 |
| ALL | B_bailout | flow_bailout | 99 | 71 | 0 | 856.08 | 8.65 | 46.5 | 336.8 |
| ALL | Bprime_dl | drive_low_struct | 83 | 54 | 1 | 1714.4 | 20.66 | 61.4 | 336.8 |
| ALL | Bprime_bailout | flow_bailout | 83 | 54 | 1 | 1347.4 | 16.23 | 51.8 | 336.8 |
| ALL | D_reclaim | flow_bailout | 99 | 61 | 0 | 326.99 | 3.3 | 40.4 | 336.8 |
| H2_holdout | B_dl | drive_low_struct | 52 | 39 | 0 | -134.17 | -2.58 | 51.9 | 120.39 |
| H2_holdout | B_bailout | flow_bailout | 52 | 39 | 0 | -229.17 | -4.41 | 46.2 | 120.39 |
| H2_holdout | Bprime_dl | drive_low_struct | 40 | 26 | 1 | 271.15 | 6.78 | 60.0 | 120.39 |
| H2_holdout | Bprime_bailout | flow_bailout | 40 | 26 | 1 | 214.15 | 5.35 | 55.0 | 120.39 |
| H2_holdout | D_reclaim | flow_bailout | 52 | 34 | 0 | -343.76 | -6.61 | 38.5 | 120.39 |
| H1_2026 | B_dl | drive_low_struct | 37 | 25 | 0 | 1346.5 | 36.39 | 59.5 | 149.66 |
| H1_2026 | B_bailout | flow_bailout | 37 | 25 | 0 | 974.5 | 26.34 | 43.2 | 149.66 |
| H1_2026 | Bprime_dl | drive_low_struct | 33 | 21 | 0 | 1359.5 | 41.2 | 63.6 | 149.66 |
| H1_2026 | Bprime_bailout | flow_bailout | 33 | 21 | 0 | 1022.5 | 30.98 | 45.5 | 149.66 |
| H1_2026 | D_reclaim | flow_bailout | 37 | 21 | 0 | 702.0 | 18.97 | 43.2 | 149.66 |

## Rule definitions

- **B**: `flow_turn_ts < p0_ts` → flow_turn + exit; else p0 + sealed
- **B'**: B + V10 veto → p0 + sealed if p0 exists; skip ft-only in 1–3 ATR zone
- **D**: early ft → reclaim_br + wash_struct; else p0 + sealed

## Entry×exit reference

- `flow_turn+drive_low_struct`: n=96 net_total=1491.35
- `flow_turn+flow_bailout`: n=96 net_total=891.75
- `flow_turn+momentum_tail`: n=96 net_total=-403.12
- `flow_turn+momentum_tail_trail`: n=96 net_total=-393.09
- `flow_turn+sealed`: n=96 net_total=124.8
- `flow_turn+wash_struct`: n=96 net_total=-156.63
- `p0+drive_low_struct`: n=61 net_total=395.32
- `p0+flow_bailout`: n=61 net_total=319.32
- `p0+momentum_tail`: n=61 net_total=554.8
- `p0+momentum_tail_trail`: n=61 net_total=513.45
- `p0+sealed`: n=61 net_total=336.8
- `p0+wash_struct`: n=61 net_total=198.49
- `p0_quality+drive_low_struct`: n=7 net_total=97.7
- `p0_quality+flow_bailout`: n=7 net_total=-88.3
- `p0_quality+momentum_tail`: n=7 net_total=-61.88
- `p0_quality+momentum_tail_trail`: n=7 net_total=-61.88
- `p0_quality+sealed`: n=7 net_total=-36.27
- `p0_quality+wash_struct`: n=7 net_total=-11.27
- `reclaim_br+drive_low_struct`: n=48 net_total=-151.49
- `reclaim_br+flow_bailout`: n=48 net_total=313.91
- `reclaim_br+momentum_tail`: n=48 net_total=-82.94
- `reclaim_br+momentum_tail_trail`: n=48 net_total=-16.8
- `reclaim_br+sealed`: n=48 net_total=-26.72
- `reclaim_br+wash_struct`: n=48 net_total=-208.12

