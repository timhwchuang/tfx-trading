# Phase 4 第一輪正式掃描 — 產物目錄（2026-09-04）

事實紀錄,不是慶祝。本輪證偽的是「現行 Setup A 猜測／這張 grid」,
**不是** Phase 4 通過、也不是「程式交易沒救」。
進度總覽的 Phase 4 **維持未勾**(`[ ]`),直到未來某一輪 `go`。

人類 reviewer 請先讀:[LESSONS.md](LESSONS.md)、本目錄 `sweep/gates.md`(後續 commit 補上)、
以及 [ROADMAP_SMC_BACKTEST.md](../ROADMAP_SMC_BACKTEST.md) 的
「第一輪正式掃描結果」與「下一假設」。

## 跑次摘要

| 項 | 值 |
|---|---|
| 區間 | `2025-03-03` → `2026-03-02` |
| seed | `42` |
| grid | **216** 組(`entry` top/ce × `min_points` 15/20/30 × `stop_buffer` 3/5/8 × tp 2R/`opposite_liquidity` × `require_external` T/F × `max_hold` 12/24/10000) |
| IS 進度 | 另跑 conservative+optimistic → 432;無 `--max-combos` |
| git(跑當下) | `159b651`(incremental FVG/SMC harness) |
| wall | ~39942 s |
| RSS | ~292 MB |
| 本機產物 | `/tmp/phase4_go` |
| **verdict** | **`no_go`** |
| `elected` | `null` |
| 硬閘 | 五條全未過(無 plateau) |

## 目錄配置

```text
phase4_round1_2026-09-04/
  README.md          ← 本檔
  LESSONS.md         ← 錯誤日記(給人類)
  sweep/             ← harness 掃描輸出(後續 commit 補 CSV / gates.md)
  blotter/           ← 代表格成交流水(後續 commit 補 CSV)
```

- `sweep/`:預期含 `gates.md`、`manifest.json`、`grid.csv`、`is_oos.csv`、
  `walk_forward.csv`、`slippage.csv`、`mc_mdd.csv` 等(與 `backtest/sweep.py` 寫檔一致)。
  本輪 `elected = null`,不會有 `trades_elected_*.csv`。
- `blotter/`:代表格(高頻格 ext=False / min=15 / buf=3 / 2R 等)的 trade log,
  用來對 `entry_stopped` / stop / target 與費用,不是全 grid 流水。

**佔位**:此 commit 只放目錄 stub。完整 sweep / blotter CSV 由本機 box 後續 commit
推到**同一條 PR branch**。若目錄仍空,以本 README 與 `LESSONS.md` 的數字為準。

## 刻意不收進 git

- 完整 `run.log` / `rss.log`(root `.gitignore` 已忽略 `*.log`;體積大、對審查無增量)
- `/tmp/phase4_go` 本機工作目錄本身

## 與 roadmap 的關係

規則仍以 [ROADMAP_SMC_BACKTEST.md](../ROADMAP_SMC_BACKTEST.md) 為準。
Phase 3 Setup A 區塊是歷史 v1;改規則先改該文,再改 code。
本目錄只存第一輪實證與解讀,不改 `setup_a.py`、不改閘門門檻。
