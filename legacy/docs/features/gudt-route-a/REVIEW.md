# FT-021 — GUDT Route A（REVIEW）

> Bugbot review log · 2026-06-30

## Round 1

4 **High** findings → fixed:

| Severity | Location | Finding | Fix |
|----------|----------|---------|-----|
| High | `route_a_exit.py:179` | Invalid indentation broke import | Fixed dedent |
| High | `params.py:17` | `live_get` 3-arg call | Match ORB 2-arg pattern |
| High | `strategy.py:166` | Replay skipped events on position mismatch | Wait instead of advance `_event_idx` |
| High | `ft021_*.py` | Hardcoded `RouteAStackParams()` | `stack_params_from_gudt()` |

## Round 2

**Bugbot found no bugs.**

## Parity

`ft021_parity_check.py` **PASS** (2025-05-01 .. 2026-06-30):

- CF net **+683.4** (target +683 ±15)
- extend_days **4**, flip_days **1**
- H1 2026 **+236.5**, UAT 2m **−106.29** vs br5 **−411.61**
- decision_mismatches **0**

## Status

**Draft** — plugin + parity harness complete; kernel baseline requires tick_cache.
