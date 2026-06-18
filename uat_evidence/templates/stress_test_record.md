# 壓力測試紀錄

| 欄位 | 值 |
|------|-----|
| 日期 | YYYY-MM-DD |
| 測試類型 | disconnect_warmup / disconnect_with_position / no_tick / force_flatten / other |
| 執行者 | |
| 開始時間 (UTC+8) | HH:MM:SS |
| 結束時間 (UTC+8) | HH:MM:SS |

## 情境

- 斷網前倉位：flat / long 1 / short 1
- 斷網時長：__ 秒
- 預期行為：（例：暖機期無 entry、有倉 CRITICAL、三次斷線 block_new_entry）

## 實際結果

- [ ] 符合預期
- log 片段路徑：`phase4_stress/log_YYYYMMDD_testname.txt`
- 券商倉位截圖：（若有倉）
- 備註：

## Audit timeline 摘要（Phase 5 審閱用）

```
（貼 SIGNAL_AUDIT / FILL_AUDIT / ALERT 關鍵行，或 episode_id）
```
