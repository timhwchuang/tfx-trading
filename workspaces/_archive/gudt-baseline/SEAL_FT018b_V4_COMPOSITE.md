# SEAL — FT-018b B′ Composite V4 (`bprime_v4_dist`)

> **Status**: RESEARCH SEAL · **2026-06-30**  
> **Does not replace** `SEAL_FT018b_B_PRIME.md` or production `gk1_rt0p4`.

## Spec (`preset=v4`)

| Leg | Rule |
|-----|------|
| Long | B′ (`flow_turn` / `p0+sealed`, V10 veto) |
| Entry veto | Skip day if `pre_break_br < 0.35` (5min before break) |
| Short | P0+10min: `px < p0_entry` AND `BR < 0.42` → exit long + flip short, stop `dh+2` |

CLI: `apps/trading-app/src/scripts/ft018_gudt_composite.py --preset v4`

## Holdout test — 2026-01..04 (seal window)

| | n | Net | WR% |
|--|--:|----:|----:|
| B′ alone | 26 | **+1124** | 73.1% |
| **V4 composite** | 22 | **+1053** | 77.3% |
| Δ | −4 traded / 7 skipped | **−71** | — |

### By month (01..04)

| Month | B′ n | B′ | V4 n | V4 | Δ |
|-------|-----:|---:|-----:|---:|--:|
| 2026-01 | 5 | +223 | 4 | +146 | −78 |
| 2026-02 | 6 | +79 | 5 | +13 | −66 |
| 2026-03 | 5 | +7 | 4 | +112 | **+105** |
| 2026-04 | 10 | +815 | 9 | +783 | −32 |
| **Total** | **26** | **+1124** | **22** | **+1053** | **−71** |

## Full 2026 H1 + Jun (01..06)

| Month | B′ n | B′ | V4 n | V4 | Δ |
|-------|-----:|---:|-----:|---:|--:|
| 2026-01 | 5 | +223 | 4 | +146 | −78 |
| 2026-02 | 6 | +79 | 5 | +13 | −66 |
| 2026-03 | 5 | +7 | 4 | +112 | +105 |
| 2026-04 | 10 | +815 | 9 | +783 | −32 |
| 2026-05 | 7 | +236 | 7 | +195 | −41 |
| 2026-06 | 6 | −362 | 5 | +73 | **+435** |
| **Total** | **39** | **+998** | **34** | **+1321** | **+323** |

## Gate verdict

| Criterion | 01..04 | 01..06 |
|-----------|--------|--------|
| Net > 0 | PASS | PASS |
| Beat B′ alone | **FAIL (−71)** | PASS (+323) |
| Replace B′ seal | **NO** | **NO** |

**Conclusion**: V4 composite is a **research overlay** tuned for June wash/distribution regime. On 2026-01..04 holdout it **underperforms B′** (−71); flip/br5 skip costs more than it saves outside 3月/6月. Keep B′ as research champion; V4 documented for optional distribution handling only.
