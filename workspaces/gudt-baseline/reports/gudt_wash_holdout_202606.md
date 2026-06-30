# GUDT Rule Matrix 2026-06-01..2026-06-30

| period | rule | ft_exit | n | ft_days | veto | net | mean | WR% | p0+sealed |
|--------|------|---------|---|---------|------|-----|------|-----|-----------|
| ALL | B_dl | drive_low_struct | 7 | 4 | 0 | -428.71 | -61.24 | 28.6 | -390.05 |
| ALL | B_bailout | flow_bailout | 7 | 4 | 0 | -428.71 | -61.24 | 28.6 | -390.05 |
| ALL | Bprime_dl | drive_low_struct | 6 | 3 | 0 | -361.71 | -60.28 | 33.3 | -390.05 |
| ALL | Bprime_bailout | flow_bailout | 6 | 3 | 0 | -361.71 | -60.28 | 33.3 | -390.05 |
| ALL | D_reclaim | flow_bailout | 7 | 1 | 0 | -457.05 | -65.29 | 14.3 | -390.05 |

## Rule definitions

- **B**: `flow_turn_ts < p0_ts` → flow_turn + exit; else p0 + sealed
- **B'**: B + V10 veto → p0 + sealed if p0 exists; skip ft-only in 1–3 ATR zone
- **D**: early ft → reclaim_br + wash_struct; else p0 + sealed

## Entry×exit reference

- `flow_turn+drive_low_struct`: n=7 net_total=-169.06
- `flow_turn+flow_bailout`: n=7 net_total=-4.06
- `flow_turn+momentum_tail`: n=7 net_total=-98.87
- `flow_turn+momentum_tail_trail`: n=7 net_total=-98.87
- `flow_turn+sealed`: n=7 net_total=-187.54
- `flow_turn+wash_struct`: n=7 net_total=-153.06
- `p0+drive_low_struct`: n=6 net_total=-382.0
- `p0+flow_bailout`: n=6 net_total=-184.0
- `p0+momentum_tail`: n=6 net_total=-207.32
- `p0+momentum_tail_trail`: n=6 net_total=-207.32
- `p0+sealed`: n=6 net_total=-390.05
- `p0+wash_struct`: n=6 net_total=-381.32
- `reclaim_br+drive_low_struct`: n=2 net_total=270.94
- `reclaim_br+flow_bailout`: n=2 net_total=270.94
- `reclaim_br+momentum_tail`: n=2 net_total=296.94
- `reclaim_br+momentum_tail_trail`: n=2 net_total=296.94
- `reclaim_br+sealed`: n=2 net_total=235.94
- `reclaim_br+wash_struct`: n=2 net_total=270.94

