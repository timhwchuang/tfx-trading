# GUDT Rule B — flow bailout backtest

Rule: `flow_turn_ts < p0_ts` → flow_turn + ft_exit; else p0 + sealed.

| period | n | ft_days | net_total | net_mean |
|--------|---|---------|-----------|----------|
| 2026-01-01..2026-05-31 (flow_bailout) | 37 | 25 | 974.5 | 26.34 |
| 2026-01-01..2026-05-31 (drive_low_struct) | 37 | 25 | 1346.5 | 36.39 |

## Entry×exit reference

- `flow_turn+drive_low_struct`: n=35 net_total=1445.82
- `flow_turn+flow_bailout`: n=35 net_total=917.22
- `flow_turn+momentum_tail`: n=35 net_total=-319.69
- `flow_turn+momentum_tail_trail`: n=35 net_total=-320.81
- `flow_turn+sealed`: n=35 net_total=192.51
- `flow_turn+wash_struct`: n=35 net_total=41.1
- `p0+drive_low_struct`: n=24 net_total=112.55
- `p0+flow_bailout`: n=24 net_total=150.55
- `p0+momentum_tail`: n=24 net_total=159.65
- `p0+momentum_tail_trail`: n=24 net_total=119.15
- `p0+sealed`: n=24 net_total=149.66
- `p0+wash_struct`: n=24 net_total=-48.58
- `p0_quality+drive_low_struct`: n=3 net_total=13.7
- `p0_quality+flow_bailout`: n=3 net_total=-148.3
- `p0_quality+momentum_tail`: n=3 net_total=-136.07
- `p0_quality+momentum_tail_trail`: n=3 net_total=-136.07
- `p0_quality+sealed`: n=3 net_total=-43.57
- `p0_quality+wash_struct`: n=3 net_total=-65.57
- `reclaim_br+drive_low_struct`: n=19 net_total=-278.35
- `reclaim_br+flow_bailout`: n=19 net_total=49.05
- `reclaim_br+momentum_tail`: n=19 net_total=-261.16
- `reclaim_br+momentum_tail_trail`: n=19 net_total=-171.39
- `reclaim_br+sealed`: n=19 net_total=-241.65
- `reclaim_br+wash_struct`: n=19 net_total=-430.48
