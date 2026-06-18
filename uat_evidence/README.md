# UAT Evidence — 證據歸檔

> 對照 [`docs/uat/APP.md`](../docs/uat/APP.md) 強制規範。路徑預設在 monorepo 根（Windows：`C:\tfx-trading\uat_evidence\`）。

## 目錄結構

```
uat_evidence/
├── README.md
├── templates/                # 空白範本（複製後填寫，勿直接改壞範本）
├── phase0/                   # 環境就緒、run_tests 輸出
├── phase3_weekly/            # 週 KPI 快照、券商對帳 CSV
├── phase4_stress/            # 斷網演練、tick 分層 CSV
├── phase5_review/            # 壓力情境 audit、前 5 大虧損日、Pilot 審核
└── phase6_alerts/            # Telegram CRITICAL 截圖 + 時間戳
```

`reports/`、`snapshots/`、`tick_cache/` 在 monorepo 根（`cache_paths.py` 為 SSOT）。Phase 結束時 commit `reports/`、`snapshots/`、`uat_evidence/`（**不含** `tick_cache/`）。

## 使用 SOP

1. **Phase 0**：存 `phase0/setup_YYYYMMDD.txt`（`run_tests` 結果、`git branch`）。
2. **Phase 3 起每週**：
   - 複製 `templates/weekly_kpi_snapshot.md` → `phase3_weekly/weekly_YYYYMMDD.md`
   - 複製 `templates/broker_reconciliation.csv` → `phase3_weekly/broker_reconciliation.csv`（累積列；勿改 `templates/` 原件）
3. **Phase 4**：壓力測試 → `templates/stress_test_record.md` 複製到 `phase4_stress/`；tick 分層 → `phase4_stress/tick_quality_stratification.csv`
4. **Phase 5**：`phase5_review/top5_loss_days.md` + ≥3 壓力情境 audit timeline
5. **Phase 6**：`phase6_alerts/alert_CRITICAL_YYYYMMDD_HHMMSS.png` + `log_snippet.txt`（**用 `.txt`，勿用 `.log`** — 根 `.gitignore` 會忽略 `*.log`）

## 相關指令（monorepo 根）

```powershell
cd C:\tfx-trading
$env:PYTHONPATH="apps\trading-app\src"

# 日報 JSON
python -m reporting $env:LOG_FILE --json > reports\dayYYYYMMDD.json

# 週 KPI 趨勢（須為 --json 產出的報告檔）
python -m reporting reports\day*.json --trend

# Determinism hash
python -m sweep.determinism_check --date YYYY-MM-DD --mode hash --output snapshots\determinism_YYYYMMDD.txt
```

## 敏感資料

勿 commit API 金鑰、CA 密碼；截圖可遮罩帳號。