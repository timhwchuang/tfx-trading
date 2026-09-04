# blotter/

代表格成交流水（**不是**全 216 格）。產物已在 commit `3080d40` 入庫。

## 本目錄檔案

| 檔 | 說明 |
|---|---|
| `trades_hi_freq_cons.csv` | 高頻格 ext=False, min=15, buf=3, 2R；IS 171 日盤，8 筆 |
| `trades_hi_freq_opt.csv` | 同上 optimistic（與 cons 相同） |
| `trades_best_ev_cons.csv` | 虧最少格（min=30, buf=8） |
| `trades_mid_defaultish_cons.csv` | 中段代表格 |
| `report.json` | 漏斗／彙總 |
| `diag_blotter.py` | 當次診斷腳本（可複核，非正式套件） |

高頻格出口混和：`entry_stopped`×4 / stop×3 / target×1；費用來回約 49 NT。

解讀見 [../LESSONS.md](../LESSONS.md)；延續見 [../WHAT_NEXT.md](../WHAT_NEXT.md)。
