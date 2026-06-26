> **Monorepo**：[`tfx-trading`](https://github.com/timhwchuang/tfx-trading) → `apps/trading-app/src/backfilldata/`。安裝：`bash scripts/setup-dev.sh`（repo 根）。

# backfilldata

**Shioaji historical tick / 1m kbar backfill CLI** for the trading-app integrator.

Fetches historical ticks/kbars for past trade days and **today after 13:45 Taipei** (day session close), writes CSV caches under monorepo `tick_cache/` (ticks and kbars in one directory). Tick backfill defaults to the day session `RangeTime` window `08:45:00`–`13:45:00`.

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

## Cache quality (audit / repair)

回測前建議掃描整個 `tick_cache/`：

```bash
cd apps/trading-app/src
python -m storage.cache_audit --code TMFR1          # 逐日一行：差異vols / ohlc差 / kbars 根數
python -m storage.cache_repair --code TMFR1 --fix   # API 補跨月尾盤 + 從 ticks 補 kbar 缺口 + 重稽核
python -m storage.cache_repair --code TMFR1 --fix-kbars-only   # 僅本地 ticks 修 kbar（不呼叫 API）
```

| 模組 | 職責 |
|------|------|
| `storage.cache_audit` | 比對 tick 聚合 1m OHLCV vs `*_kbars_*.csv` |
| `storage.cache_repair` | 批次修復 + 輸出與 audit 相同格式 |
| `storage.tick_rollover` | TMFR1+TMFR2 13:30–13:45 合併（backfill 預設呼叫） |
| `storage.kbar_repair` | 缺 kbar 列從 ticks 補；跨月日整檔從 ticks 重建 |

## Cache layout (defaults)

| Output | Path | Used by |
|--------|------|---------|
| Ticks | `tick_cache/{code}_{date}.csv` | backtest, replay |
| Kbars | `tick_cache/{code}_kbars_{date}.csv` | ATR warmup, param_sweep, structure calibration, UAT `KBARS_ARCHIVE` |

若本機仍有舊版 `kbar_cache/`：`bash scripts/linux/migrate-legacy-kbar-cache.sh`（見 [`docs/ops/LinuxOps.md`](../../../../docs/ops/LinuxOps.md)）。

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
