# GUDT exit counterfactual 2025-04-01..2026-06-30

## B′ — conditional break/dl (ft leg only re-simulated)

| variant | n | net | mean | WR% |
|---------|--:|----:|-----:|----:|
| B′ + drive_low_struct (baseline) | 76 | +125.8 | +1.7 | 50.0 |
| B′ + conditional break/dl | 76 | -121.2 | -1.6 | 47.4 |
| Δ | | **-247.0** | | |

### ft days where conditional dl differs (|Δ|≥10)

| day | dl | cond | Δ | dl exit | cond exit |
|-----|---:|-----:|--:|---------|-----------|
| 2025-06-03 | +79.0 | -36.2 | -115.2 | stop_loss | stop_loss |
| 2026-06-22 | +3.0 | -104.5 | -107.5 | horizon | stop_loss |
| 2025-11-17 | -13.0 | +52.0 | +65.0 | stop_loss | trail_stop |
| 2025-08-29 | -9.0 | -36.2 | -27.2 | stop_loss | stop_loss |
| 2025-05-28 | -10.0 | -36.2 | -26.2 | stop_loss | stop_loss |
| 2025-11-25 | -18.0 | -36.2 | -18.2 | stop_loss | stop_loss |
| 2025-11-04 | -19.0 | -36.2 | -17.2 | stop_loss | stop_loss |

## Fixed-time entry (all GUDT qualifying days)

Reference: flow_turn+dl matrix n=59 WR=50.8% net=-250.5

| entry | exit | n | net | mean | WR% |
|-------|------|--:|----:|-----:|----:|
| 09:15 | sealed | 89 | -51.0 | -0.6 | 25.8 |
| 09:15 | drive_low_struct | 89 | +844.7 | +9.5 | 55.1 |
| 09:15 | conditional_break_dl | 89 | +292.4 | +3.3 | 47.2 |
| 09:30 | sealed | 89 | +2133.7 | +24.0 | 50.6 |
| 09:30 | drive_low_struct | 89 | +3019.8 | +33.9 | 73.0 |
| 09:30 | conditional_break_dl | 89 | +2526.5 | +28.4 | 67.4 |
