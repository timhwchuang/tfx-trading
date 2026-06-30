# GUDT B′ quick-stop oracle (early ft → p0 if dl stop before break)

Period: 2025-05-01 .. 2026-06-30

Rule: early `flow_turn+dl` re-simulated; if `stop_loss` within T sec and entry before `first_break_ts` → `p0+sealed`.

| B′ baseline | n=76 | net=+125.8 | WR=50.0% |

## Threshold sweep

| T (min) | veto days | net | Δ vs B′ | WR% |
|--------:|----------:|----:|--------:|----:|
| 5 | 2 | +286.9 | +161.0 | 51.3 |
| 10 | 2 | +286.9 | +161.0 | 51.3 |
| 15 | 2 | +286.9 | +161.0 | 51.3 |

**Best T = 5 min** → net +286.9 (Δ +161.0)

## Pick changes (best T)

| day | base net | veto net | Δ | ft hold(s) |
|-----|--------:|--------:|--:|-----------:|
| 2026-06-18 | -110.0 | -5.0 | +105.0 | 174 |
| 2025-09-05 | -45.0 | +11.0 | +56.0 | 247 |
