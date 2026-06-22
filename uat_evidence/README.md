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

**合約代碼**：目前預設 **微台 `TMFR1`**（`config.yaml`）。`uat_evidence/phase0/` 若為 Phase 0 大台 `TXFR1` 冒煙，屬歷史證據，勿改寫；新 Phase 請以 log 內 `合約: TMFR1` 為準。

## 使用 SOP

1. **Phase 0**：存 `phase0/setup_YYYYMMDD.txt`（`run_tests` 結果、`git branch`）。
2. **Phase 3 起每週**：
   - 複製 `templates/weekly_kpi_snapshot.md` → `phase3_weekly/weekly_YYYYMMDD.md`
   - 執行 `python -m reporting.uat_evidence_export broker reports\day*.json`（累積至 `phase3_weekly/broker_reconciliation.csv`）；券商損益可手填或用 `--broker-data` CSV 匯入
3. **Phase 4**：壓力測試 → `templates/stress_test_record.md` 複製到 `phase4_stress/`；tick 分層 → `python -m reporting.uat_evidence_export tick reports\day*.json`
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

# 券商對帳 + tick 分層 CSV（從 day*.json 自動填入）
python -m reporting.uat_evidence_export both reports\day*.json
python -m reporting.uat_evidence_export broker reports\day*.json --broker-data uat_evidence\phase3_weekly\broker_pnl_input.csv

# Pilot Readiness Gate 預檢（含 CSV / Sharpe per-trade）
python -m sweep.pilot_gate_check reports\day*.json --log-file $env:LOG_FILE

# Determinism hash
python -m sweep.determinism_check --date YYYY-MM-DD --mode hash --output snapshots\determinism_YYYYMMDD.txt
```

## 敏感資料

勿 commit API 金鑰、CA 密碼；截圖可遮罩帳號。

## 什麼可以 commit 到 GitHub、什麼不可以

| ✅ 可以 commit | ❌ 不要 commit |
|----------------|----------------|
| `reports/day*.json`（UAT KPI；無密鑰） | `*.log`、`logs/`（含帳號、委託細節） |
| `snapshots/config_YYYYMMDD.yaml` | `uat-env.sh`、`.env`、任何含 `SJ_*` 的檔案 |
| `snapshots/determinism_*.txt`（hash 或 deferred 說明） | `*.pfx` / `*.p12` / `credentials/` |
| `uat_evidence/phase*/` 內 **已去識別** 的 `.txt` / `.md` / `.csv` | `tick_cache/`（體積大、runtime 資料） |
| `uat_evidence/templates/` | 券商截圖未遮罩帳號 |
| 程式碼、測試、`config/config.yaml`（**無**密鑰） | `~/sinotrade/` 等 repo 外憑證目錄 |

**原則**：只 commit **可重現 UAT 流程與 KPI** 的產物；密鑰、原始 log、tick 原始檔留在本機。

**Phase 0 建議 commit 清單**（範例）：

```bash
git add reports/day20260622.json
git add snapshots/config_20260622.yaml snapshots/determinism_20260622.txt
git add uat_evidence/phase0/
# 勿 git add logs/ tick_cache/ ~/sinotrade/
git commit -m "UAT Phase 0 smoke complete - 20260622"
```

commit 前建議：`git status` 確認沒有 `logs/`、`tick_cache/`、`.env` 被 staged。