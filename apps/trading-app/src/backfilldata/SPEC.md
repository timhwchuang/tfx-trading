# backfilldata — Authoritative Spec

> **Module**: `backfilldata` · **Entry**: `python -m backfilldata` · **Parent**: `apps/trading-app`  
> **Depends on**: `storage.tick_loader`, `storage.kbar_loader`, Shioaji (`import shioaji as sj`)

This document is the **single source of truth** for the historical market-data backfill CLI. README and app-level SPEC should point here for cache layout and API limits.

---

## 1. Purpose & positioning

`backfilldata` fills gaps in local tick/kbar CSV caches by calling Shioaji historical APIs. It complements — does not replace — live UAT archiving (`TICK_ARCHIVE=1`, `KBARS_ARCHIVE=1`).

| Scenario | Tool |
|----------|------|
| Daily accumulation while live runs | `python -m live` + archive ports |
| Backfill missing past trade days (post-close) | `python -m backfilldata date YYYY-MM-DD` |
| Bulk multi-year download | **Avoid** (bandwidth + rate limits) |

### Intended audience

| Use case | Suitable? |
|----------|-----------|
| Fill 1–30 missing UAT days before calibration / sweep | **Yes** |
| Replace `tick_cache/` without backup | **No** |
| Run during live session on same `person_id` | **No** (5 connection cap) |

---

## 2. In scope

- CLI `python -m backfilldata date <YYYY-MM-DD> [end]`
- CLI `python -m backfilldata month <YYYY-MM>` — trading weekdays (skip weekends + [pin-yi Taiwan calendar](https://api.pin-yi.me/taiwan-calendar/{year}); `isHoliday`); reads `trade_days/{year}.json` first, fetches API on cache miss; batched for tick API day limits
- Login via `SJ_API_KEY` / `SJ_SEC_KEY` only (no CA; market data only)
- Contract resolve for continuous futures (`TMFR1`, `TXFR1`, …) — same rule as `TradingEngine._resolve_contract`
- Tick CSV → `tick_cache/{code}_{date}.csv` via `storage.tick_loader.download_and_cache`
- Tick API defaults to `TicksQueryType.RangeTime` for day session (`08:45:00`–`13:45:00`); `--all-day-ticks` opt-out for full-day fetch
- Partial cache (e.g. live `*.csv.gz` missing morning) is **merged** into plain CSV; when both plain and gzip exist, rows are unioned before gap detection
- Stale gzip is removed only after a successful plain CSV write (atomic temp → rename)
- Kbar CSV → primary `kbar_cache/{code}_kbars_{date}.csv` for sweep / B-class calibration
- Optional mirror of kbars → `tick_cache/` (default **on**) to match `kbar_archiver` UAT layout
- `api.usage()` logging before/after batches; pace ~0.15s between kbar day fetches
- Past trade days and **today after 13:45 Taipei** (day session close)
- Recognize compressed tick cache (`*.csv.gz` from `python -m storage`) as satisfied — no redundant `api.ticks`

## 3. Out of scope

- Live streaming subscribe / order placement
- Tick data cleaning, rollover, or `simtrade` filtering on historical ticks
- Automatic scheduling (human or external cron)
- Writing secrets to `config.yaml` or repo files

---

## 4. Public API

### Package exports (`backfilldata`)

```python
from backfilldata import (
    BackfillError,
    backfill_dates,
    parse_date_args,
    resolve_contract,
)
```

### CLI

```bash
cd apps/trading-app/src
python -m backfilldata date 2026-06-20
python -m backfilldata month 2026-04
python -m backfilldata month 2026-04 --dry-run
python -m backfilldata date 2026-06-18 2026-06-20 --code TMFR1
python -m backfilldata date 2026-06-20 --ticks-only
python -m backfilldata date 2026-06-20 --ticks-only --time-start 08:45 --time-end 13:45
python -m backfilldata date 2026-06-20 --kbars-only --no-mirror-kbars
python -m backfilldata date 2026-06-20 --all-day-ticks
python -m backfilldata date 2026-06-20 --overwrite
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--code` | `config.product_code` | Continuous futures code |
| `--tick-cache-dir` | `<monorepo>/tick_cache` | Tick output |
| `--kbar-cache-dir` | `<monorepo>/kbar_cache` | Primary kbar output |
| `--mirror-kbars` / `--no-mirror-kbars` | mirror **on** | Copy kbars to `tick_cache` |
| `--ticks-only` / `--kbars-only` | both | Fetch subset |
| `--time-start` / `--time-end` | `08:45:00` / `13:45:00` | Tick `RangeTime` window **and** kbar post-fetch filter |
| `--all-day-ticks` | off | Use `TicksQueryType.AllDay` instead of `RangeTime` |
| `--overwrite` | off | Re-download existing files |
| `--simulation` / `--production` | `config.simulation` | API environment |

### `backfill_dates(...) -> BackfillResult`

Injectable `api=` for tests. Returns paths plus `missing_*_dates`; `ok` is false when any requested day lacks cache files.

Kbar fetch delegates to `storage.kbar_loader.download_and_cache_kbars` with `simulation=`, `mirror_cache_dir=`, and `pace_sec`.

---

## 5. Cache path contract

Canonical roots: `storage.cache_paths`.

| Kind | Primary path | Consumers |
|------|--------------|-----------|
| Ticks | `tick_cache/{code}_{date}.csv` | `backtest`, `param_sweep`, replay |
| Kbars | `kbar_cache/{code}_kbars_{date}.csv` | `param_sweep`, `structure_calibration` |
| Kbars (mirror) | `tick_cache/{code}_kbars_{date}.csv` | UAT `kbar_archiver`, human inspection |

**Path discipline**: backfill is the bridge that writes **both** trees so sweep and UAT layouts stay aligned without manual copy.

---

## 6. Shioaji API mapping

| Data | API | Parameters |
|------|-----|------------|
| Ticks | `api.ticks` | default `query_type=TicksQueryType.RangeTime`, `date=YYYY-MM-DD`, `time_start=08:45:00`, `time_end=13:45:00`, `timeout=30000` (ms); up to 3 retries on timeout (2s backoff) via `storage.tick_loader` |
| Kbars | `api.kbars` | `start=date`, `end=date` (1-minute bars), `timeout=30000` (ms); backfill 落地前依 `--time-start`/`--time-end` 裁切（API 本身無 intraday 參數） |

Use **continuous** contracts (`TMFR1`, not expired month codes). Futures history from **2020-03-22**.

Official docs: [Historical Market Data](https://sinotrade.github.io/tutor/market_data/historical/) · [Use Restrictions](https://sinotrade.github.io/tutor/limit/)

### Rate / quota limits (must respect)

| Limit | Value |
|-------|-------|
| Quote queries (ticks+kbars+snapshots) | 50 / 5 sec |
| Intraday ticks queries | 10 / day |
| Intraday kbars queries | 270 / day |
| Tick days per CLI run | max 10 (`validate_tick_day_count`) |
| Kbar days per CLI run | max 270 (`validate_kbar_day_count`) |
| Daily bandwidth | 500 MB – 10 GB (by 30-day volume) |
| Connections per `person_id` | 5 (`Login()` counts) |

**Operational guidance**: run after close; call `api.logout()` when done; do not overlap with `python -m live` on the same credentials.

---

## 7. Fidelity caveats

Inherited from `storage.tick_loader` / `storage.kbar_loader`:

- Historical ticks: best bid/ask only (no depth); no `simtrade` flag
- Kbar `ts` encoding differs simulation vs production — `kbar_loader.kbar_ts_from_ns` / `tick_loader.shioaji_ts_from_ns` apply `simulation` from config/backfill
- Historical backfill ticks on **simulation** API must not use `_ns_to_taipei_naive` (+8) — same wall-clock-as-UTC rule as kbars
- Strategy hot path uses `tick.close` only; bid/ask in CSV are optional reference
- **Coverage heuristic**: skip/refetch uses session edge tolerance (±1 min) and max gap (ticks 30 min, kbars 10 min). Sparse but valid caches may trigger an extra API fetch; prefer `--overwrite` if you know the cache is complete

---

## 8. Validation

Tests: `apps/trading-app/tests/backfilldata/test_backfilldata.py`

| Test | Contract |
|------|----------|
| `parse_date_args` single / range / invalid | Date parsing |
| `validate_past_dates` rejects today before 13:45 Taipei / future | API precondition |
| `resolve_contract` category path | TMFR1 → Futures.TMF.TMFR1 |
| `backfill_dates` mocked API | Writes tick + kbar + mirror |
| `backfill_dates` skip existing | No overwrite by default |
| CLI `--help` | No Shioaji import at help time |
| `cli_help` catalog | Module listed; matches app SPEC CLI table |

---

## 9. Safety

- Agent / automation must **not** commit API keys or run backfill with production credentials unless a human explicitly requests it
- Backfill does not place orders; still uses real Shioaji login — treat as sensitive ops
- Prefer `simulation: true` UAT keys for research backfill
