# GUDT conditional tail exit (B′ + br5-only picks)

Period: 2025-05-01 .. 2026-06-30

Tail leg (p0 only): no hard TP, hold 30m, trail_dist=1.0×ATR, BE=0.75.
ft path: unchanged drive_low_struct.

| spec | tail days | net | Δ | WR% | worst | capture |
|------|----------:|----:|--:|----:|------:|--------:|
| baseline | 0 | +333.1 | +0.0 | 52.2 | -202.3 | 43% |
| clean | 36 | +21.4 | -311.6 | 43.5 | -202.3 | 49% |
| ext | 15 | +140.6 | -192.5 | 47.8 | -202.3 | 44% |
| clean_and_ext | 12 | +140.6 | -192.5 | 47.8 | -202.3 | 44% |
| clean_or_ext | 39 | +21.4 | -311.6 | 43.5 | -202.3 | 49% |

**Best gated:** `ext` → net +140.6

## Tail-trigger days (best spec)

- 2025-06-10: ext=9.6 base=+18 → tail=-5 (-23) [momentum_clean] breakeven
- 2025-07-16: ext=6.64 base=+12 → tail=+16 (+4) [momentum_clean] horizon
- 2025-08-07: ext=14.18 base=-13 → tail=-10 (+3) [momentum_clean] horizon
- 2025-08-21: ext=7.02 base=+20 → tail=-5 (-25) [momentum_clean] breakeven
- 2026-01-02: ext=6.12 base=-36 → tail=-36 (+0) [momentum_clean] stop_loss
- 2026-01-05: ext=8.06 base=+72 → tail=+58 (-14) [momentum_clean] trail_stop
- 2026-02-10: ext=6.71 base=-50 → tail=-50 (+0) [wash_real] stop_loss
- 2026-02-24: ext=10.88 base=-58 → tail=-58 (+0) [momentum_clean] stop_loss
- 2026-04-10: ext=6.29 base=-61 → tail=-61 (+0) [wash_real] stop_loss
- 2026-04-15: ext=8.62 base=+42 → tail=+30 (-12) [momentum_clean] trail_stop
- 2026-04-24: ext=9.85 base=+161 → tail=+131 (-31) [momentum_clean] trail_stop
- 2026-05-21: ext=10.27 base=-5 → tail=-5 (+0) [momentum_clean] breakeven
- 2026-05-25: ext=11.81 base=-94 → tail=-94 (+0) [momentum_clean] stop_loss
- 2026-06-01: ext=5.79 base=+90 → tail=-5 (-95) [momentum_clean] breakeven
- 2026-06-29: ext=5.1 base=-202 → tail=-202 (+0) [wash_real] stop_loss
