# GUDT Rule B — flow bailout backtest

Rule: `flow_turn_ts < p0_ts` → flow_turn + ft_exit; else p0 + sealed.

| period | n | ft_days | net_total | net_mean |
|--------|---|---------|-----------|----------|
| 2025-05-01..2025-11-30 (flow_bailout) | 52 | 39 | -229.17 | -4.41 |
| 2025-05-01..2025-11-30 (drive_low_struct) | 52 | 39 | -134.17 | -2.58 |

## Entry×exit reference

- `flow_turn+drive_low_struct`: n=52 net_total=-81.47
- `flow_turn+flow_bailout`: n=52 net_total=-122.47
- `flow_turn+momentum_tail`: n=52 net_total=-271.43
- `flow_turn+momentum_tail_trail`: n=52 net_total=-248.28
- `flow_turn+sealed`: n=52 net_total=-116.62
- `flow_turn+wash_struct`: n=52 net_total=-276.73
- `p0+drive_low_struct`: n=31 net_total=197.77
- `p0+flow_bailout`: n=31 net_total=120.77
- `p0+momentum_tail`: n=31 net_total=308.15
- `p0+momentum_tail_trail`: n=31 net_total=331.3
- `p0+sealed`: n=31 net_total=120.39
- `p0+wash_struct`: n=31 net_total=162.07
- `p0_quality+drive_low_struct`: n=3 net_total=53.0
- `p0_quality+flow_bailout`: n=3 net_total=29.0
- `p0_quality+momentum_tail`: n=3 net_total=43.19
- `p0_quality+momentum_tail_trail`: n=3 net_total=43.19
- `p0_quality+sealed`: n=3 net_total=-23.7
- `p0_quality+wash_struct`: n=3 net_total=23.3
- `reclaim_br+drive_low_struct`: n=25 net_total=255.86
- `reclaim_br+flow_bailout`: n=25 net_total=388.86
- `reclaim_br+momentum_tail`: n=25 net_total=334.22
- `reclaim_br+momentum_tail_trail`: n=25 net_total=310.59
- `reclaim_br+sealed`: n=25 net_total=257.93
- `reclaim_br+wash_struct`: n=25 net_total=355.36
