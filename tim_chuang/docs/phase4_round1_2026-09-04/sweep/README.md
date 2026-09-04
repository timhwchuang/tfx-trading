# sweep/

Phase 4 harness（`tfx_trading/backtest.sweep`）第一輪正式掃描輸出。
產物已在 commit `3080d40` 入庫（同源 `/tmp/phase4_go`）。
**不要**用本目錄當第二輪 A′ grid 的起點。這條路不通：[CLOSED.md](../../phase4_round2_2026-09-04/CLOSED.md)。

## 本目錄檔案

| 檔 | 說明 |
|---|---|
| `gates.md` | 硬閘清單；本輪 **no_go** |
| `manifest.json` | git hash、區間、grid、`elected=null`、verdict |
| `grid.csv` | 432 列 IS（216 combo × 2 fill） |
| `walk_forward.csv` | 10 折；皆 `insufficient_sample` |
| `is_oos.csv` / `slippage.csv` | 無 elect → 幾乎只有表頭 |
| `mc_mdd.csv` | 無 elect → 零樣本列 |
| `run_meta.txt` | exit / wall / peak RSS |
| `run_tail.txt` | 完整 `run.log` 尾段（完整 log／`rss.log` 未入庫，過大） |

本輪 `elected = null`，沒有 `trades_elected_*.csv`。

數字解讀見 [../LESSONS.md](../LESSONS.md)；跑次摘要見 [../README.md](../README.md)；延續見 [../WHAT_NEXT.md](../WHAT_NEXT.md)。
