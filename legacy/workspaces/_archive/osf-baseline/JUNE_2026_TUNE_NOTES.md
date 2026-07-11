# June 2026 Story Tune Notes (one pass only)

```
STATUS: Research exploration (2026-06 only) — STORY TUNE DONE
NOT: Pilot / UAT / Holdout / expectancy
Path support ≠ net edge after friction & execution
```

## Process

1. Module: `apps/trading-app/src/reporting/june_story_tune.py`
2. `/review` → fixes → re-review **PASS**
3. Single `run_tune()` on locked June timeline — **no second knob pass**

Artifact: `june_2026_tune_results.json`  
Days with OR/context: **21** · Variants: **24** (A+ 12 · C+ 6 · A−+ 6)

## Soft success (pre-declared)

| rule | threshold |
|------|-----------|
| n | ≥ 5 |
| median path_edge @60m | ≥ 8 (friction buffer) |
| stop_hit @30m | ≤ 35% |
| path_support_rate | > 0 |

## Verdict

### **No stronger story. Soft winners = 0. Park June path-OK families.**

| family | best variant (by med edge, n≥3) | n | med edge@60 | support | stop@30 | vs baseline |
|--------|----------------------------------|---|-------------|---------|---------|-------------|
| A+ | `…_stopor_high_minus_30_hold3` (all A+ tied on edge) | 4 | **−102.5** | 0.25 | 0.50† | same med as A\|long baseline (−102.5); n 6→4 via h4 dual_above |
| C+ | `…_poolpools_pref_buf0` | 3 | **−111.0** | 0.333 | 0.00 | better med than C\|long (−178) but n&lt;5; any/or_only n=5 still med ~−120 |
| A−+ | *(no n≥3)* all variants n=2 | 2 | **−91.5** | 0.00 | 0.00 | dual_below kills sample; path never supports narrative |

† Wider stops (`or_mid` / `or_low`) drop stop_hit@30m to **0%** but **do not change path_edge** (MAE/MFE is independent of stop_ref). Story path is still net negative.

**Positive median path_edge variants: 0 / 24.**

## Story reading (trader, not gate)

### A+ (OR break + 5m hold + h4 dual_above)

- Stack filter removes 2 of 6 baseline A days → **n=4**, still fails friction buffer and (with tight stop) stop rate.
- `hold_bars` 3 vs 5 and `h1 not_below` **did not change June set** — same four entries, same med edge.
- **Narrative not stronger**: still “open drive works only on pure trend days; structural stop under OR is theater when path MAE dominates.”

### C+ (flush reclaim + h4 dual_above + pool knobs)

- h4 dual_above cuts baseline C n=9 → **5** (any / or_only) or **3** (pools_pref).
- Best med edge among n≥5 is still **~−117 to −123** (or_only slightly better than any).
- pools_pref best med **−111** but **n=3** — classic selection illusion, not a system.
- stop_buffer 0/20 does not move path edge (stop is path metric side-channel only).
- **Slightly less awful than raw C**, still nowhere near friction buffer. Reclaim-on-h4-above is **not** a June primary.

### A−+ (OR low break short + h4 dual_below)

- Only **2** days qualify under dual_below; **path_support_rate = 0**.
- Stack filter is correct discipline for shorts in a mixed month — and it reveals the story has **no June body**.

## What June tune *did* teach

1. **Knob axes that only change stop_hit without path edge** (A+ stop modes) are risk-ops, not narrative repair.
2. **h4 dual_above / dual_below** correctly shrinks n; it does **not** flip median path edge positive on this month.
3. Baseline path-OK *events* remain anecdotes; mechanical re-emit under stack still fails family kill criteria.
4. **Do not open FT SPEC from June.** Do not re-grid June.

## Next (only if human reopens)

| option | when |
|--------|------|
| Multi-year mechanical CF on **one** story (prefer C reclaim or A OR hold) under Holdout v2 | After intentional multi-year design, not more June knobs |
| Qualitative other months (May / July) | If still chart-reading before coding |
| Park | **Default** |

## Negative library (unchanged)

| Story | Kin | Tune outcome |
|-------|-----|--------------|
| A+ | FT-009 ORB | Stack + stop grid cannot clear June path edge |
| C+ | FT-016 / sweep families | Slight med improvement; still fail buffer |
| A−+ | short breakout | dual_below → n=2, zero path support |

---

*One June pass complete. Results frozen in `june_2026_tune_results.json`. No further June parameter search planned.*
