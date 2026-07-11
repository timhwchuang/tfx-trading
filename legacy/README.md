# legacy/

Historical research artifacts kept for reference only.

**Not part of the active build or CI.**

## Contents

| Path | What it was |
|------|-------------|
| `packages/strategies/` | VWAP / GUDT / ORB / stretch-fade |
| `packages/trading-backtest/` | Replay / backtest host |
| `packages/trading-engine/` | Pre-merge package metadata / SPEC |
| `apps/trading-app/reporting/` | Counterfactuals, Entry Lab, UAT reports |
| `apps/trading-app/sweep/` | Param sweep / holdout |
| `apps/trading-app/backtest/` | App-layer backtest CLI |
| `apps/trading-app/scripts/` | FT-00x research scripts |
| `apps/trading-app/src/integrations/` | GUDT bootstrap / VWAP refresh / **telemetry_port** |
| `apps/trading-app/src/observability.py` | VWAP/near-miss DailyObservability（曾誤留 active tree） |
| `apps/trading-app/src/metrics.py` | offline expectancy / MDD / friction KPI |
| `apps/trading-app/tests/test_observability.py` | legacy obs unit tests |
| `apps/trading-app/tests/test_performance_metrics.py` | legacy metrics unit tests |
| `apps/trading-app/src/storage/` | cache_audit / cache_repair / legacy_cache_migrate / taiwan_calendar |
| `apps/trading-app/src/backfilldata/taiwan_calendar.py` | pin-yi holiday re-export (active CLI no longer uses it) |
| `docs/` | Old features, UAT, TODO, WeeklyStatus |
| `workspaces` | old ai traders |

**Active product**: `apps/trading-app`（含 in-tree `src/trading_engine` + `strategy_simple` + storage + live）。
