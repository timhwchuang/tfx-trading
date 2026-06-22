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
- Login via `SJ_API_KEY` / `SJ_SEC_KEY` only (no CA; market data only)
- Contract resolve for continuous futures (`TMFR1`, `TXFR1`, …) — same rule as `TradingEngine._resolve_contract`
- Tick CSV → `tick_cache/{code}_{date}.csv` via `storage.tick_loader.download_and_cache`
- Kbar CSV → primary `kbar_cache/{code}_kbars_{date}.csv` for sweep / B-class calibration
- Optional mirror of kbars → `tick_cache/` (default **on**) to match `kbar_archiver` UAT layout
- `api.usage()` logging before/after batches; pace ~0.15s between kbar day fetches
- Past trade days only (reject today/future in Asia/Taipei)
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
python -m backfilldata date 2026-06-18 2026-06-20 --code TMFR1
python -m backfilldata date 2026-06-20 --ticks-only
python -m backfilldata date 2026-06-20 --kbars-only --no-mirror-kbars
python -m backfilldata date 2026-06-20 --overwrite
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--code` | `config.product_code` | Continuous futures code |
| `--tick-cache-dir` | `<monorepo>/tick_cache` | Tick output |
| `--kbar-cache-dir` | `<monorepo>/kbar_cache` | Primary kbar output |
| `--mirror-kbars` / `--no-mirror-kbars` | mirror **on** | Copy kbars to `tick_cache` |
| `--ticks-only` / `--kbars-only` | both | Fetch subset |
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
| Ticks | `api.ticks` | `query_type=TicksQueryType.AllDay`, `date=YYYY-MM-DD`, `timeout=30000` (ms); up to 3 retries on timeout (2s backoff) via `storage.tick_loader` |
| Kbars | `api.kbars` | `start=date`, `end=date` (1-minute bars), `timeout=30000` (ms) |

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
- Kbar `ts` encoding differs simulation vs production — `kbar_loader.kbar_ts_from_ns` applies `simulation` from config
- Strategy hot path uses `tick.close` only; bid/ask in CSV are optional reference

---

## 8. Validation

Tests: `apps/trading-app/tests/backfilldata/test_backfilldata.py`

| Test | Contract |
|------|----------|
| `parse_date_args` single / range / invalid | Date parsing |
| `validate_past_dates` rejects today | API precondition |
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
