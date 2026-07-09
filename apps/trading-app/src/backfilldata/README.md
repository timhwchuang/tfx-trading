> **Monorepo**：[`tfx-trading`](https://github.com/timhwchuang/tfx-trading) → `apps/trading-app/src/backfilldata/`.

# backfilldata

**Shioaji historical tick / 1m kbar backfill CLI** (module name **`backfilldata`**, not `backfilldate`).

Fetches AllDay ticks+kbars for every calendar day in a date range or month. Empty / non-trading days skip writing a file and are not errors. Default API mode is UAT (`--uat`).

| 文件 | 用途 |
|------|------|
| [**SPEC.md**](SPEC.md) | CLI、快取語意、限制 |
| [../storage/tick_loader.py](../storage/tick_loader.py) | Calendar-day tick fetch + CSV |
| [../storage/kbar_loader.py](../storage/kbar_loader.py) | Kbar fetch + CSV |
| [tick_rollover.py](tick_rollover.py) | Settlement afternoon TMFR2→TMFR1 tick merge |

## Quick start

```bash
export SJ_API_KEY=...
export SJ_SEC_KEY=...

cd apps/trading-app/src
python -m backfilldata date 2026-06-20
python -m backfilldata month 2026-04
python -m backfilldata month 2026-04 --dry-run
python -m backfilldata date 2026-07-01 2026-07-06 --code TMFR1 --production
```

Flags: `--code`, `--tick-cache-dir`, `--overwrite`, `--uat` / `--production`.

## Cache layout

| Output | Path |
|--------|------|
| Ticks | `tick_cache/{code}_{date}.csv` — **calendar day only** |
| Kbars | `tick_cache/{code}_kbars_{date}.csv` |

Audit/repair/migrate CLIs and tick→kbar repair live under `legacy/` (not active). Rollover is automatic in backfill.
