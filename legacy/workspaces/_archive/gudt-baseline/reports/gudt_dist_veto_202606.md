# GUDT Distribution Veto — June 2026 Backtest

**Base rule:** B′ (`ft018b_bprime_v10_dl`)  
**Period:** 2026-06-01 … 2026-06-30 (6 traded days, 7 GUDT qualifying)

## Veto definitions

| ID | Trigger | Action |
|----|---------|--------|
| **V1** | BR < 0.35 in 30s vol window at **break_dh − 5min** | Skip long for the day |
| **V2** | P0 + 10min: BR < 0.42 **and** px < entry | Early-exit long at +10m |
| **V3** | Same as V2 | Keep long; add short at +10m, stop `dh + 2` |
| **V4** | V1 ∧ V3 | Skip on pre-break veto; else short hedge on post-P0 dist |

## June 2026 results

| Strategy | Net | Δ vs B′ | n |
|----------|-----|---------|---|
| B′ baseline | **−362** | — | 6 |
| V1 pre-break skip | −243 | **+118** | 5 |
| V2 dist early exit | −281 | +80 | 6 |
| V3 dist + short dh+2 | −126 | +236 | 6 |
| **V4 V1 + V3** | **+73** | **+435** | 5 |

### Day-level (June)

| Day | br5pre | dist10 | B′ | V1 | V3 | V4 |
|-----|--------|--------|-----|-----|-----|-----|
| 06-01 | 0.61 | — | +90 | +90 | +90 | +90 |
| 06-09 | **0.29** | — | −118 | **skip** | −118 | **skip** |
| 06-15 | 0.62 | — | −24 | −24 | −24 | −24 |
| 06-18 | 0.51 | — | −110 | −110 | −110 | −110 |
| 06-22 | 0.35 | — | +3 | +3 | +3 | +3 |
| 06-29 | 0.66 | **Y** (br=0.40, px−117) | −202 | −202 | **+34** | **+114** |

**6/29 V4 mechanics:** long early exit ≈ −120; short @+10m (stop dh+2) ≈ +234 → day **+114**.

**6/09 V1:** pre-break sell spike (BR5=0.29); veto skips the −118 p0+sealed loser.

## Full period sanity (2025-05 … 2026-06, n=79)

| Strategy | Net | Δ vs B′ |
|----------|-----|---------|
| B′ baseline | +1269 | — |
| V1 pre-break skip | +1122 | −147 |
| V2 dist early exit | +1294 | +25 |
| V3 dist + short | +1283 | +14 |
| V4 V1 + V3 | **+1320** | **+51** |

Signal coverage (P0 days): ALL **61** days — pre_veto **12**, post_dist **14**, overlap **2**.

## Takeaways

1. **June holdout flips positive** with V4 (+73 vs −362) — mainly 6/09 skip + 6/29 short hedge.
2. **V1 alone hurts full-period** (−147): 12 skipped days include winners; use as *conditional* veto, not global.
3. **Post-P0 dist short (V3)** is the safer full-period overlay (+14 to +51 with V1); early exit (V2) similar but doesn't capture 6/29 downside as well.
4. **6/22** br5pre=0.35 exactly — at threshold edge; `<=0.35` would also skip (+3 day).

## Next

- Wire V4 into `gudt_wash_probe` as `rule_B_dist_veto` for reproducible CLI runs.
- Test `dh + 0.25×ATR` short stop (prior hedge work) under same veto frame.
- Holdout B still **research-only** — does not replace sealed `gk1_rt0p4` champion.
