# backfilldata — Authoritative Spec

> **Module**: `backfilldata` (not `backfilldate`) · **Entry**: `python -m backfilldata` · **Parent**: `apps/trading-app`  
> **Depends on**: `storage.tick_loader`, `storage.kbar_loader`, Shioaji · **Owns**: `tick_rollover` (settlement afternoon TMFR2→TMFR1)

---

## 1. Purpose

Fill local tick/kbar CSV caches via Shioaji historical APIs. Complements live UAT archiving; does not replace it.

| Scenario | Tool |
|----------|------|
| Daily accumulation while live runs | `python -m live` + archive ports |
| Backfill past calendar days (post-close) | `python -m backfilldata date|month` |

---

## 2. CLI

Subcommands: **`date`**, **`month`** only.

| Flag | Meaning |
|------|---------|
| `--code` | Continuous futures code (default: config `product_code`) |
| `--tick-cache-dir` | Cache root (default: monorepo `tick_cache/`) |
| `--overwrite` | Re-fetch even when file exists |
| `--uat` / `--production` | Mutually exclusive; default **`--uat`** (simulation=True) if neither |
| `--dry-run` | `month` only: list eligible days, no API |

Removed: session-ticks, time-start/end, all-day-ticks, holiday calendar, ticks-only/kbars-only, no-merge-rollover, `--simulation` name.

### Semantics

- **`date`**: every calendar day in range (`date_range`); no holiday filter
- **`month`**: every calendar day in month (`calendar_days_in_month`); no holiday filter
- Always **AllDay** ticks + kbars (`tick_time_start/end=None`)
- Automatic **rollover merge** always on (`backfilldata.tick_rollover`) — patches ticks only; **does not** rebuild kbars from ticks (trust `api.kbars`)
- Empty days (non-trading / no tape): log skip, **do not write** file; **not** a failure
- No tick→kbar repair on active path
- `BackfillResult.ok` is False only when `failed_dates` (hard API exceptions) is non-empty
- Future / today-before-13:45 Taipei skipped via `filter_backfill_eligible_dates`

```bash
cd apps/trading-app/src
python -m backfilldata date 2026-06-20
python -m backfilldata date 2026-07-01 2026-07-06 --code TMFR1
python -m backfilldata month 2026-04 --dry-run
python -m backfilldata month 2026-04 --production
```

---

## 3. Cache layout

| Output | Path | Content |
|--------|------|---------|
| Ticks | `tick_cache/{code}_{D}.csv` | Calendar day **D only** (AllDay D ∪ D+1, filter `date==D`) |
| Kbars | `tick_cache/{code}_kbars_{D}.csv` | Bars with `ts.date()==D` |

Prior-evening ticks from AllDay(D) are **excluded** from file D; same-day night from AllDay(D+1) is **included**.

---

## 4. Shioaji limits (summary)

- Quote queries ~50 / 5s; pace ~0.15s between days
- Tick batch cap 10 days / run; kbar 270
- Do not login while live holds a connection slot for the same `person_id`

---

## 5. Tests

`python -m unittest tests.backfilldata.test_backfilldata -v` from `apps/trading-app` with `PYTHONPATH=src`.
