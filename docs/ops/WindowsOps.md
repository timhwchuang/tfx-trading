# Windows 運維清單（P4-0 / P4-3 / P4-4）

> 目標執行環境：**Windows 10/11 或 Windows Server**。UAT / Pilot 皆以本清單驗收。  
> **Monorepo 根目錄預設**：`C:\tfx-trading`（可自訂，但腳本參數需一致）。

## P4-0 上線前檢查

- [ ] Python 3.11+ 已安裝
- [ ] 已 clone `git@github.com:timhwchuang/tfx-trading.git` 至 `C:\tfx-trading`
- [ ] 在 **monorepo 根** 執行 `bash scripts/setup-dev.sh`（或 Git Bash）建立 `C:\tfx-trading\.venv`
- [ ] `C:\tfx-trading\.venv\Scripts\python.exe apps\trading-app\run_tests.py` 全綠（81 項）
- [ ] 系統時區 **台北 (UTC+8)**；自動對時已開啟（`w32tm /query /status`）
- [ ] 環境變數已設定（User 或 System）：
  - `SJ_API_KEY` / `SJ_SEC_KEY`
  - `LOG_FILE=C:\logs\trading-app-uat.log`
  - `CONFIG_PATH=C:\tfx-trading\apps\trading-app\config\config.yaml`（選配，預設會找 app 內 config）
  - `TICK_ARCHIVE=1`（UAT 累積 tick → monorepo 根 `C:\tfx-trading\tick_cache\`，見 `cache_paths.py`）
  - `KBARS_ARCHIVE=1`
  - 選配：`TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` 或 `ALERT_WEBHOOK_URL`
- [ ] `C:\logs\` 目錄存在且執行帳號可寫入
- [ ] 交易時段電腦不睡眠；Windows Update 主動時段延後
- [ ] `apps\trading-app\config\config.yaml` 中 `simulation: true`（UAT）或 `false`（Pilot + CA）

## P4-3 告警通道

程式透過 `src/alerts.py` 發送 **best-effort** 告警（不阻塞 callback）：

| 環境變數 | 用途 |
| -------- | ---- |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot token |
| `TELEGRAM_CHAT_ID` | 目標 chat id |
| `ALERT_WEBHOOK_URL` | 通用 JSON webhook（body: `{text, level}`） |

驗收：設定 Telegram 後，以 `tests/test_alerts.py` 或（在 `apps\trading-app` 目錄）`python -c "from alerts import send_alert; send_alert('test')"` 確認收到訊息。

**Phase 6 證據**（[`uat/APP.md`](../uat/APP.md)）：CRITICAL 實機觸發後，將訊息截圖 + UTC+8 時間戳 + log 片段存入 `uat_evidence/`。

## P4-4 進程守護

### 方案 A：工作排程器（建議 UAT）

```powershell
# 以系統管理員 PowerShell 執行
cd C:\tfx-trading\apps\trading-app
.\scripts\windows\register-task.ps1 -MonorepoRoot C:\tfx-trading
```

- 開機觸發；失敗每 1 分鐘重試最多 3 次
- 任務名預設：`tfx-trading-vwap`
- crash 後重啟走 P0-3 `sync_positions` 對帳

### 方案 B：NSSM 服務（Pilot 可選）

1. 下載 [NSSM](https://nssm.cc/) 並加入 PATH
2. `nssm install tfx-trading-vwap "C:\tfx-trading\.venv\Scripts\python.exe" "-m" "live"`
3. 設定 `AppDirectory=C:\tfx-trading\apps\trading-app\src`；Environment 加入 API keys

### 手動啟動（開發 / 除錯）

```powershell
.\apps\trading-app\scripts\windows\start-trading-app.ps1 -MonorepoRoot C:\tfx-trading
```

## 收盤後維護

```powershell
cd C:\tfx-trading\apps\trading-app\src
C:\tfx-trading\.venv\Scripts\python.exe -m storage.compress
```

建議工作排程器每日 **15:30** 執行。

## 相關文件

- [`docs/uat/APP.md`](../uat/APP.md)
- [`TODO.md`](../TODO.md) Phase 4
- 根 [`SPEC.md`](../../SPEC.md) §7