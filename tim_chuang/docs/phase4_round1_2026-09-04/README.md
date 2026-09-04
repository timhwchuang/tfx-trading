# Phase 4 第一輪正式掃描產物（2026-09-04）

本目錄保存 Setup A 第一輪 **no_go** 的可複核產物與事後 blotter，供 review／省思用。
**不是** Phase 4 驗收通過；**不是**再開第二輪 grid 的許可。
A′ 日盤 elect 這條路不通：[CLOSED.md](../phase4_round2_2026-09-04/CLOSED.md)。
roadmap 進度總覽的 Phase 4 checkbox 仍不勾。

## 跑法摘要

| 項 | 值 |
|---|---|
| 區間 | 2025-03-03 → 2026-03-02 |
| seed | 42 |
| grid | 216 組參數（IS 另 ×2 fill → 432 runs） |
| `--max-combos` | 無（正式） |
| git（跑當下） | `159b651`（incremental FVG/SMC） |
| 牆鐘 | ~39942 s（≈11h 6m） |
| peak RSS | ~292 MB |
| verdict | **no_go**（`elected=null`） |

指令（當時）：

```bash
cd tim_chuang
.venv/bin/python -u -m tfx_trading.backtest.sweep \
  --start 2025-03-03 --end 2026-03-02 \
  --out <out> --seed 42
```

## 產物狀態

CSV／`gates.md`／blotter **已齊**（見 commit `3080d40`）。不是佔位目錄。

## 目錄

- `sweep/` — 正式掃描輸出（`gates.md`、`manifest.json`、`grid.csv`、`walk_forward.csv`…）
- `blotter/` — 事後單組重跑的成交明細與 `report.json`
- `LESSONS.md` — 錯誤經驗／省思（給 reviewer）

未納入 repo：完整 `run.log`／`rss.log`（過大）；僅留 `sweep/run_tail.txt`（完整 log 未入庫）。

## 跨工作區延續

請先讀 [`WHAT_NEXT.md`](WHAT_NEXT.md)。A′ 日盤 elect 已收工，見 [CLOSED.md](../phase4_round2_2026-09-04/CLOSED.md)。

## Review 請看

1. `LESSONS.md`
2. `sweep/gates.md` + `manifest.json`
3. `blotter/trades_hi_freq_cons.csv`（典型虧法）
4. roadmap 內「第一輪正式掃描結果／下一假設」段落
5. `WHAT_NEXT.md`
