> **Monorepo**：[`tfx-trading`](https://github.com/timhwchuang/tfx-trading) → `apps/trading-app/src/backfilldata/`。安裝：`bash scripts/setup-dev.sh`（repo 根）。

# backfilldata

**Shioaji historical tick / 1m kbar backfill CLI** for the trading-app integrator.

Fetches historical ticks/kbars for past trade days and **today after 13:45 Taipei** (day session close), writes CSV caches under monorepo `tick_cache/` and `kbar_cache/`, with optional mirror so UAT archiver layout and sweep/calibration consumers stay aligned. Tick backfill defaults to the day session `RangeTime` window `08:45:00`–`13:45:00`.

**本模組為作者個人研究與學習用途而公開，部分程式與文件在開發過程中借助 AI 協作撰寫與整理。**

本工具僅協助下載與落地行情快取，**不構成**投資建議。使用永豐 API 須遵守券商條款與流量限制；濫用可能導致暫停服務。

| 文件 | 用途 |
|------|------|
| [**SPEC.md**](SPEC.md) | **權威 spec**：CLI、快取路徑、Shioaji 限制、測試對照 |
| [../SPEC.md](../../SPEC.md) | trading-app 整合層總覽 |
| [../storage/tick_loader.py](../storage/tick_loader.py) | Tick fetch + CSV I/O |
| [../storage/kbar_loader.py](../storage/kbar_loader.py) | Kbar fetch + CSV I/O |
| [docs/DOC_MAP.md](../../../../docs/DOC_MAP.md) | 全 monorepo 文件索引 |

## Status

**Research / UAT tooling** — not a UAT or Pilot gate. Use after market close to fill missing days; daily accumulation should still rely on `TICK_ARCHIVE=1` while live runs.

## Quick start

```bash
# monorepo 根已 setup-dev.sh
export SJ_API_KEY=...
export SJ_SEC_KEY=...

cd apps/trading-app/src
python -m backfilldata date 2026-06-20
python -m backfilldata month 2026-04
python -m backfilldata month 2026-04 --dry-run
python -m backfilldata date 2026-06-18 2026-06-20 --code TMFR1
python -m backfilldata date 2026-06-20 --ticks-only --time-start 08:45 --time-end 13:45
python -m backfilldata date 2026-06-20 --all-day-ticks
python -m backfilldata --help
```

`config.yaml` 的 `simulation` / `product_code` 為預設；可用 `--production` 或 `--code` 覆寫。

## Cache layout (defaults)

| Output | Path | Used by |
|--------|------|---------|
| Ticks | `tick_cache/{code}_{date}.csv` | backtest, replay |
| Kbars (primary) | `kbar_cache/{code}_kbars_{date}.csv` | param_sweep, structure calibration |
| Kbars (mirror) | `tick_cache/{code}_kbars_{date}.csv` | UAT `KBARS_ARCHIVE` layout |

關閉 mirror：`--no-mirror-kbars`。

## Shioaji limits (摘要)

- 行情查詢 **50 次 / 5 秒**；盤中 ticks **10 次/日**、kbars **270 次/日**
- 每日流量 **500MB–10GB**（見 `api.usage()`）
- 同一人最多 **5 連線** — 勿與 `python -m live` 同時 login

詳見 [SPEC.md §6](SPEC.md#6-shioaji-api-mapping)。

## Tests

```bash
cd apps/trading-app
python run_tests.py -v tests/backfilldata/
```

## License

MIT — see [`../../LICENSE`](../../LICENSE) (trading-app).
