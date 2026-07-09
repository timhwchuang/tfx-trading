# FT-023 — Review (Bugbot)

| Round | Date | Critical/High | Status |
|-------|------|---------------|--------|
| 1 | 2026-07-02 | 1H + 3M | fixed |
| 2 | 2026-07-02 | 1H + 1M | fixed |
| 3 | 2026-07-02 | 1H (live partial ticks) | fixed |

## Round 1 — fixed

| Severity | Location | Fix |
|----------|----------|-----|
| High | live coordinator | `GudtWashBetaLiveBootstrapCoordinator` + `attach` isinstance order |
| Medium | `wash_beta.py` exit clamp | Realign exit tick/px when before entry |
| Medium | replay plan | `MIN_REPLAY_HOLD_SEC` on same-second exit |
| Medium | `ft023_parity_check` | Preserve `day_count` aggregate failures |

## Round 2 — fixed

| Severity | Location | Fix |
|----------|----------|-----|
| High | live `as_of_ts` | `apply_intraday_plan(..., as_of_ts=None)` |
| Medium | month filter | Drop out-of-month day failures from aggregate |

## Round 3 — fixed

| Severity | Location | Fix |
|----------|----------|-----|
| High | live 09:14 partial ticks | `build_wash_beta_live_intraday_plan` — exit at config flatten ts, not last partial tick |

## Live kbar session filter (night session)

FT-022 HEAD had `_load_today_bars() → load_kbars_csv` without `_session_bars`, so night bars made `_open_0845` return None until `no_open_0845` at 09:14. Fixed: `_session_bars(load_kbars_csv(path))` — shared by Route A and wash-beta coordinators. Tests: `test_load_today_bars_filters_night_session_before_open_0845`, `test_wash_beta_coordinator_filters_night_session_bars`.

Execution parity **PASS** `44/44` (2026 H1, 2026-07-02).
