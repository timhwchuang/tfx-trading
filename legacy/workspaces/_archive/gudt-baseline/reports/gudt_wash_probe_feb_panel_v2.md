# GUDT Wash Probe — Panel

Exploratory FT-018b · does not overwrite sealed baseline.

## 2026-02-09

- wash_label (p0 path): `momentum_clean`
- drive_high: 32621.0 · drive_low: 32514.0

| entry | exit | net | exit_reason | w30 | w60 | sell_ratio | vol_shrink |
|-------|------|-----|-------------|-----|-----|------------|------------|
| flow_turn | momentum_tail | 65.77 | trail_stop | 74.0 | 107.0 | 0.6201 | False |
| flow_turn | momentum_tail_trail | 65.77 | trail_stop | 74.0 | 107.0 | 0.6201 | False |
| flow_turn | drive_low_struct | 49.0 | horizon | 74.0 | 107.0 | 0.6201 | False |
| flow_turn | wash_struct | 49.0 | horizon | 74.0 | 107.0 | 0.6201 | False |
| p0 | drive_low_struct | 44.0 | horizon | 30.0 | 39.0 | 0.1967 | False |
| p0 | wash_struct | 44.0 | horizon | 30.0 | 39.0 | 0.1967 | False |
| p0 | momentum_tail | 25.0 | horizon | 30.0 | 39.0 | 0.1967 | False |
| p0 | momentum_tail_trail | 25.0 | horizon | 30.0 | 39.0 | 0.1967 | False |
| reclaim_br | momentum_tail | 8.0 | horizon | 13.0 | -12.0 | 0.5932 | False |
| reclaim_br | momentum_tail_trail | 8.0 | horizon | 13.0 | -12.0 | 0.5932 | False |
| flow_turn | sealed | -5.0 | breakeven | 74.0 | 107.0 | 0.6201 | False |
| reclaim_br | drive_low_struct | -26.0 | horizon | 13.0 | -12.0 | 0.5932 | False |
| reclaim_br | sealed | -26.0 | horizon | 13.0 | -12.0 | 0.5932 | False |
| reclaim_br | wash_struct | -26.0 | horizon | 13.0 | -12.0 | 0.5932 | False |
| p0 | sealed | -53.39 | stop_loss | 30.0 | 39.0 | 0.1967 | False |

- flow_turn+wash_struct: net=49.0 · dBR=0.1333 · depth=52.0
- flow_turn+drive_low_struct: net=49.0
**Best** `flow_turn+momentum_tail` net=65.77 vs sealed p0=-53.39 (Δ=119.16)

## 2026-02-10

- wash_label (p0 path): `momentum_clean`
- drive_high: 33139.0 · drive_low: 32993.0

| entry | exit | net | exit_reason | w30 | w60 | sell_ratio | vol_shrink |
|-------|------|-----|-------------|-----|-----|------------|------------|
| flow_turn | drive_low_struct | 45.61 | trail_stop | 37.0 | 12.0 | 0.4744 | False |
| flow_turn | momentum_tail | 45.61 | trail_stop | 37.0 | 12.0 | 0.4744 | False |
| flow_turn | momentum_tail_trail | 45.61 | trail_stop | 37.0 | 12.0 | 0.4744 | False |
| flow_turn | sealed | 45.61 | trail_stop | 37.0 | 12.0 | 0.4744 | False |
| flow_turn | wash_struct | 45.61 | trail_stop | 37.0 | 12.0 | 0.4744 | False |
| p0 | sealed | -49.55 | stop_loss | -48.0 | -68.0 | 0.1043 | False |
| p0 | drive_low_struct | -53.0 | horizon | -48.0 | -68.0 | 0.1043 | False |
| p0 | momentum_tail | -53.0 | horizon | -48.0 | -68.0 | 0.1043 | False |
| p0 | momentum_tail_trail | -53.0 | horizon | -48.0 | -68.0 | 0.1043 | False |
| p0 | wash_struct | -53.0 | horizon | -48.0 | -68.0 | 0.1043 | False |

- flow_turn+wash_struct: net=45.61 · dBR=0.1667 · depth=66.0
- flow_turn+drive_low_struct: net=45.61
**Best** `flow_turn+sealed` net=45.61 vs sealed p0=-49.55 (Δ=95.16)

## 2026-02-11

- wash_label (p0 path): `momentum_clean`
- drive_high: 33500.0 · drive_low: 33367.0

| entry | exit | net | exit_reason | w30 | w60 | sell_ratio | vol_shrink |
|-------|------|-----|-------------|-----|-----|------------|------------|
| flow_turn | momentum_tail | 94.0 | take_profit | 100.0 | 273.0 | 0.4639 | False |
| flow_turn | momentum_tail_trail | 76.2 | trail_stop | 100.0 | 273.0 | 0.4639 | False |
| p0 | momentum_tail | 34.0 | horizon | 39.0 | 154.0 | 0.4826 | False |
| p0 | momentum_tail_trail | 34.0 | horizon | 39.0 | 154.0 | 0.4826 | False |
| flow_turn | drive_low_struct | 25.0 | horizon | 100.0 | 273.0 | 0.4639 | False |
| flow_turn | sealed | 25.0 | horizon | 100.0 | 273.0 | 0.4639 | False |
| flow_turn | wash_struct | 25.0 | horizon | 100.0 | 273.0 | 0.4639 | False |
| p0 | drive_low_struct | 4.0 | horizon | 39.0 | 154.0 | 0.4826 | False |
| p0 | wash_struct | 4.0 | horizon | 39.0 | 154.0 | 0.4826 | False |
| p0 | sealed | -5.0 | breakeven | 39.0 | 154.0 | 0.4826 | False |
| reclaim_br | drive_low_struct | -7.0 | horizon | 0.0 | 147.0 | 0.4261 | False |
| reclaim_br | momentum_tail | -46.25 | stop_loss | 0.0 | 147.0 | 0.4261 | False |
| reclaim_br | momentum_tail_trail | -46.25 | stop_loss | 0.0 | 147.0 | 0.4261 | False |
| reclaim_br | sealed | -46.25 | stop_loss | 0.0 | 147.0 | 0.4261 | False |
| reclaim_br | wash_struct | -46.25 | stop_loss | 0.0 | 147.0 | 0.4261 | False |

- flow_turn+wash_struct: net=25.0 · dBR=0.1821 · depth=38.0
- flow_turn+drive_low_struct: net=25.0
**Best** `flow_turn+momentum_tail` net=94.0 vs sealed p0=-5.0 (Δ=99.0)

## 2026-02-24

- wash_label (p0 path): `momentum_clean`
- drive_high: 34560.0 · drive_low: 34302.0

| entry | exit | net | exit_reason | w30 | w60 | sell_ratio | vol_shrink |
|-------|------|-----|-------------|-----|-----|------------|------------|
| reclaim_br | momentum_tail_trail | 211.63 | trail_stop | 232.0 | 228.0 | 0.4009 | False |
| reclaim_br | momentum_tail | 121.86 | take_profit | 232.0 | 228.0 | 0.4009 | False |
| flow_turn | momentum_tail | 92.0 | horizon | 97.0 | 217.0 | 0.3398 | False |
| flow_turn | momentum_tail_trail | 92.0 | horizon | 97.0 | 217.0 | 0.3398 | False |
| reclaim_br | drive_low_struct | 72.0 | horizon | 232.0 | 228.0 | 0.4009 | False |
| reclaim_br | sealed | 72.0 | horizon | 232.0 | 228.0 | 0.4009 | False |
| reclaim_br | wash_struct | 72.0 | horizon | 232.0 | 228.0 | 0.4009 | False |
| flow_turn | drive_low_struct | 3.0 | horizon | 97.0 | 217.0 | 0.3398 | False |
| flow_turn | wash_struct | 3.0 | horizon | 97.0 | 217.0 | 0.3398 | False |
| p0 | drive_low_struct | -21.0 | horizon | 31.0 | 179.0 | 0.3087 | False |
| flow_turn | sealed | -57.86 | stop_loss | 97.0 | 217.0 | 0.3398 | False |
| p0 | momentum_tail | -57.86 | stop_loss | 31.0 | 179.0 | 0.3087 | False |
| p0 | momentum_tail_trail | -57.86 | stop_loss | 31.0 | 179.0 | 0.3087 | False |
| p0 | sealed | -57.86 | stop_loss | 31.0 | 179.0 | 0.3087 | False |
| p0 | wash_struct | -57.86 | stop_loss | 31.0 | 179.0 | 0.3087 | False |

- flow_turn+wash_struct: net=3.0 · dBR=0.1253 · depth=39.0
- flow_turn+drive_low_struct: net=3.0
**Best** `reclaim_br+momentum_tail_trail` net=211.63 vs sealed p0=-57.86 (Δ=269.49)

## 2026-02-25

- wash_label (p0 path): `momentum_clean`
- drive_high: 35313.0 · drive_low: 35111.0

| entry | exit | net | exit_reason | w30 | w60 | sell_ratio | vol_shrink |
|-------|------|-----|-------------|-----|-----|------------|------------|
| p0 | momentum_tail | 119.29 | take_profit | 172.0 | 337.0 | 0.2881 | False |
| p0 | momentum_tail_trail | 103.14 | trail_stop | 172.0 | 337.0 | 0.2881 | False |
| reclaim_br | drive_low_struct | 87.14 | trail_stop | 206.0 | 423.0 | 0.6116 | False |
| reclaim_br | momentum_tail | 87.14 | trail_stop | 206.0 | 423.0 | 0.6116 | False |
| reclaim_br | momentum_tail_trail | 87.14 | trail_stop | 206.0 | 423.0 | 0.6116 | False |
| reclaim_br | sealed | 87.14 | trail_stop | 206.0 | 423.0 | 0.6116 | False |
| reclaim_br | wash_struct | 87.14 | trail_stop | 206.0 | 423.0 | 0.6116 | False |
| flow_turn | drive_low_struct | 74.14 | trail_stop | 227.0 | 392.0 | 0.3382 | False |
| flow_turn | momentum_tail | 74.14 | trail_stop | 227.0 | 392.0 | 0.3382 | False |
| flow_turn | momentum_tail_trail | 74.14 | trail_stop | 227.0 | 392.0 | 0.3382 | False |
| flow_turn | sealed | 74.14 | trail_stop | 227.0 | 392.0 | 0.3382 | False |
| flow_turn | wash_struct | 74.14 | trail_stop | 227.0 | 392.0 | 0.3382 | False |
| p0 | drive_low_struct | 25.0 | horizon | 172.0 | 337.0 | 0.2881 | False |
| p0 | wash_struct | 25.0 | horizon | 172.0 | 337.0 | 0.2881 | False |
| p0 | sealed | -5.0 | breakeven | 172.0 | 337.0 | 0.2881 | False |

- flow_turn+wash_struct: net=74.14 · dBR=0.1446 · depth=26.0
- flow_turn+drive_low_struct: net=74.14
**Best** `p0+momentum_tail` net=119.29 vs sealed p0=-5.0 (Δ=124.29)

## Panel aggregate (p0+sealed)

- days: 5 · net_total: -170.8

