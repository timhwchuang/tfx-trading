# trading-app UAT Checklist

> **執行環境：Windows**。驗的是**狀態機與對帳**，不是獲利。  
> **Monorepo 根目錄**：`C:\tfx-trading`（範例）。  
> **Kernel 場景** → [`packages/trading-engine/docs/UAT_CHECKLIST.md`](../../../packages/trading-engine/docs/UAT_CHECKLIST.md) Phase B/C。  
> **本檔**只涵蓋 app 部署、落盤、報表與銜接。

---

## Phase A — 部署與設定

| # | 項目 | Pass | 備註 |
|---|------|:----:|------|
| A1 | `bash scripts/setup-dev.sh`（monorepo 根）成功 | ☐ | 或 `pip install -r apps/trading-app/requirements.txt` |
| A2 | `python run_tests.py` 全綠（81 項） | ☐ | 在 `apps/trading-app/` |
| A3 | `config/config.yaml` → `simulation: true` | ☐ | Agent 不得改 false |
| A4 | `SJ_API_KEY` / `SJ_SEC_KEY` 已設（模擬帳戶） | ☐ | 不 commit |
| A5 | 系統時區台北 UTC+8 | ☐ | |
| A6 | `LOG_FILE=C:\logs\trading-app-uat.log` | ☐ | 建議開啟 |

### 啟動指令

```powershell
cd C:\tfx-trading
# 首次：bash scripts/setup-dev.sh
$env:SJ_API_KEY = "your_api_key"
$env:SJ_SEC_KEY = "your_secret_key"
$env:LOG_FILE = "C:\logs\trading-app-uat.log"
$env:TICK_ARCHIVE = "1"
$env:KBARS_ARCHIVE = "1"
$env:DUMP_ORDER_EVENTS = "1"
cd apps\trading-app\src
C:\tfx-trading\.venv\Scripts\python.exe -m live
```

| # | 啟動後確認 | Pass |
|---|------------|:----:|
| A7 | log：`VWAP Momentum 策略已啟動` | ☐ |
| A8 | log：`ATR(...) 更新` | ☐ |
| A9 | log：`Tick 落盤已啟用`（`TICK_ARCHIVE=1`） | ☐ |
| A10 | 無 `無期貨帳號` 錯誤 | ☐ |

---

## Phase B — 第一個交易日（App 層必做）

| # | 項目 | Pass | 備註 |
|---|------|:----:|------|
| B1 | 盤中 `tick_cache/{code}_{date}.csv` 持續增長 | ☐ | repo 根 `C:\tfx-trading\tick_cache\` |
| B2 | `DUMP_ORDER_EVENTS=1` 有一筆 `RAW_ORDER_EVT` | ☐ | |
| B3 | 收盤後 `python -m storage.compress` → `*.csv.gz` 可重放 | ☐ | |
| B3b | 手動斷網 30–60s → 暖機無 entry、有倉 CRITICAL | ☐ | 見 engine `LIVE_SAFETY.md` |
| B4 | `python -m reporting C:\logs\trading-app-uat.log` 有輸出 | ☐ | 秒停損率觀測 |
| B5 | `register-task.ps1 -MonorepoRoot C:\tfx-trading` 成功 | ☐ | 見 `WindowsOps.md` |

收盤壓縮（建議 15:30）：

```powershell
cd C:\tfx-trading\apps\trading-app\src
C:\tfx-trading\.venv\Scripts\python.exe -m storage.compress
```

---

## Phase C — Kernel 整合驗收

在 Phase A/B 完成後，逐項執行 [`packages/trading-engine/docs/UAT_CHECKLIST.md`](../../../packages/trading-engine/docs/UAT_CHECKLIST.md)。

Log 契約：[`docs/AuditContract.md`](AuditContract.md)。

---

## Phase D — 連續模擬（≥3 日）

| # | 項目 | Pass |
|---|------|:----:|
| D1 | 每日 log vs 券商成交明細一致 | ☐ |
| D2 | 無雙 entry（`is_pending` 有效） | ☐ |
| D3 | 收盤前持倉清空（session flatten） | ☐ |
| D4 | 跨日 `daily_pnl` / `block_new_entry` 重置 | ☐ |
| D5 | `tick_cache/` 累積可用於回測 | ☐ |

---

## Phase E — Sign-off

| 欄位 | 值 |
|------|-----|
| monorepo tag | v0.3.0-monorepo |
| engine package | v0.2.2 |
| app package | v0.1.2 |
| UAT 負責人 | |
| 模擬交易日數 | |
| **結果** | ☐ Pass → Pilot &nbsp; ☐ Fail → 修復 |

Pilot：[`BeforePilot.md`](BeforePilot.md) + [`packages/trading-engine/docs/LIVE_SAFETY.md`](../../../packages/trading-engine/docs/LIVE_SAFETY.md)。