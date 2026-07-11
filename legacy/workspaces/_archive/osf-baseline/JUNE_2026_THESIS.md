# June 2026 Thesis (exploration only)

```
STATUS: Research exploration (2026-06 only)
NOT: Pilot / UAT / Holdout / expectancy claim
Path support ≠ net edge after friction & execution
```

## 1. Primary story

**No primary story for June 2026 under agreed kill criteria.**

All families fail at least one of:
- median path edge @60m (or night 180m proxy) **< 8 pts** friction buffer
- stop_hit@30m > 35% (A|long)
- or n/path support too weak

| family | n | path_support | med edge@60 | kills |
|--------|---|--------------|-------------|-------|
| C|long | 9 | 11% | -178.0 | median_path_edge_60m_lt_friction_buffer_8 |
| N|long | 8 | 12% | -464.5 | median_path_edge_60m_lt_friction_buffer_8 |
| A-|short | 7 | 14% | -250.0 | median_path_edge_60m_lt_friction_buffer_8 |
| A|long | 6 | 33% | -102.5 | median_path_edge_60m_lt_friction_buffer_8, stop_hit_30m_gt_35pct |
| N-|short | 5 | 40% | -207.0 | median_path_edge_60m_lt_friction_buffer_8 |

### Individual path-OK events (not a system)

Worth remembering as **examples**, not a gate:

| id | side | story | note |
|----|------|-------|------|
| L-2026-06-01-A | long | A | edge60=288.0 |
| N-2026-06-02-N | long | N | edge60=198.0 |
| N-2026-06-03-N- | short | N- | edge60=95.0 |
| L-2026-06-04-C | long | C | edge60=124.0 |
| L-2026-06-09-A | long | A | edge60=190.0 |
| N-2026-06-09-N- | short | N- | edge60=77.0 |
| S-2026-06-23-A- | short | A- | edge60=19.0 |

## 2. Secondary

None. Short A− and night N/− do not clear friction buffer as families.

## 3. What June *did* teach (capability)

1. **Regime is two-regime**: early June bull impulse vs mid-June risk-off cascade (6/5–6/12, 6/23–26). A single long-only OSF-like stack will get chopped.
2. **Story C (flush reclaim)** felt best on 6/2 narrative, but **month median path edge is negative** once blind-scored — selection bias risk was real; measuring after lock mattered.
3. **Story A (OR hold)** works on pure trend days (6/1) but **stop_hit@30m = 50%** on the June sample of 6 — structural stops under OR high are often too tight in volatile opens.
4. **Night continuation** needs a different stop/time model; 05:00–08:45 has no 1m path — research must score to day open, not 15m bar gap.
5. Tooling now supports: month timeline, blind JSON lock, long/short MAE/MFE, friction display, aggregate kills.

## 4. Limitations

- **n ≈ 21 session days** — any median is fragile.
- Entry = **bar close** proxy; no IOC / queue / 5pt friction in fills (only display subtract).
- Blind tags still use automated seeds (trader_scan + structural OR break); not fully human-only chart mark-up.
- Gap classifier / regime auto-tags imperfect (e.g. 6/1 overnight null Monday).

## 5. Next validation (required before any SPEC)

**Do not use June envelope as a gate.**

If revisiting any story (especially C flush reclaim or A OR hold):
1. Define mechanical rules offline.
2. Run **2025 train / 2026 Q1 valid** under Alpha Playbook Holdout v2.
3. Preflight + negative library before FT draft.

## 6. 负面图书馆 / 本质差异

| Story | Kin | Risk | If reopen research |
|-------|-----|------|--------------------|
| A OR hold | FT-009 ORB | Same open-drive family | Need hold filter beyond break (e.g. 5m retest of OR high + stack) — else revisit-only |
| C flush reclaim | FT-016 gap drive / sweep families | Gap + reclaim long | Must differ: explicit multi-pool sweep + non-FVG 5m BOS vs drive extension |
| A− OR break short | fade / short breakout | Counter-trend in bull months | Only with h4 stack below; still failed June medians |
| N night | session-hold | Kernel qty=1 cross-session | Research-only until session semantics confirmed |

**Recommendation now:** do **not** open a new FT SPEC from June alone. Keep June as **journal + tooling proof**. Next human decision: pick **one** story for multi-year mechanical CF, or continue qualitative months (May/July) before coding.

## 7. Kernel / ops

- Assume **qty=1 full flat**; no scale-in / partial.
- Night hold / cross-day = research flag only.

