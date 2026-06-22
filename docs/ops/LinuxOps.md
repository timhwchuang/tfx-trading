# Linux 運維清單（開發 / 回測 / GCE Live）

> **角色**：Linux 用於 (1) macOS/Linux **地端研究與回測**、(2) **GCP GCE Live 連線**（見 [`HYBRID_DEPLOY.md`](HYBRID_DEPLOY.md)）。  
> **Monorepo 根目錄預設**：`/opt/tfx-trading`（GCE）或 `~/tfx-trading`（地端開發機）。

## P4-0 上線前檢查（GCE Live 節點）

- [ ] Ubuntu 24.04 LTS（或 Debian 12+）；時區 **Asia/Taipei**；`timedatectl set-ntp true`
- [ ] 已 clone `git@github.com:timhwchuang/tfx-trading.git` 至 `/opt/tfx-trading`
- [ ] `bash scripts/setup-dev.sh` 全綠；`bash scripts/run-all-tests.sh` 通過（以 `Ran N tests` 為準）
- [ ] 環境變數（`/etc/tfx-trading/env`，`chmod 600`）：
  - `SJ_API_KEY` / `SJ_SEC_KEY`
  - `LOG_FILE=/var/log/tfx-trading/trading-app-uat.log`
  - `CONFIG_PATH=/opt/tfx-trading/apps/trading-app/config/config.yaml`
  - `TICK_ARCHIVE=1`、`KBARS_ARCHIVE=1`
  - 選配：`TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` 或 `ALERT_WEBHOOK_URL`
- [ ] `apps/trading-app/config/config.yaml` → `simulation: true`（UAT）或 `false`（Pilot + CA）
- [ ] **靜態外部 IP**（GCP regional）；ingress **SSH 22**（或 IAP）；egress 443（Shioaji API）
- [ ] 開機不自動 suspend；`systemd` 守護 live 進程

## P4-3 告警通道

與 Windows 相同，透過 `src/alerts.py`（best-effort）：

| 環境變數 | 用途 |
| -------- | ---- |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot token |
| `TELEGRAM_CHAT_ID` | 目標 chat id |
| `ALERT_WEBHOOK_URL` | JSON webhook（`{text, level}`） |

驗收（在 `apps/trading-app/src`）：

```bash
cd /opt/tfx-trading/apps/trading-app/src
/opt/tfx-trading/.venv/bin/python -c "from alerts import send_alert; send_alert('linux ops test')"
```

## P4-4 進程守護（systemd，建議 GCE Live）

```bash
sudo MONOREPO_ROOT=/opt/tfx-trading bash /opt/tfx-trading/scripts/linux/install-systemd.sh
# 編輯 /etc/tfx-trading/env 填入金鑰
sudo systemctl start tfx-trading
sudo systemctl status tfx-trading
```

- 開機自啟：`systemctl enable tfx-trading`
- 失敗重啟：`Restart=on-failure`，`RestartSec=60`
- 日誌：`journalctl -u tfx-trading -f`

### 手動啟動（開發 / 除錯）

```bash
MONOREPO_ROOT=~/tfx-trading bash scripts/linux/start-trading-app.sh
```

## 收盤後維護

```bash
# cron 範例（15:30 Asia/Taipei，GCE 上執行）
30 15 * * 1-5 tfx /opt/tfx-trading/scripts/linux/post-session.sh >> /var/log/tfx-trading/post-session.log 2>&1
```

`post-session.sh` 會 source `/etc/tfx-trading/env`，並執行：

- `python -m storage`（`storage.compress` 為相容 alias）
- `python -m reporting $LOG_FILE --json` → `reports/dayYYYYMMDD.json`（log 不存在則略過）
- `python -m sweep.determinism_check --date … --output snapshots/determinism_YYYYMMDD.txt`

## 地端研究機（回測 / CAL / 分析）

地端**不跑 live**（除非刻意單機部署）。典型流程：

```bash
cd ~/tfx-trading
source .venv/bin/activate
bash scripts/run-all-tests.sh

# 從 GCE 拉 tick / kbars / reports / snapshots（deploy 帳號，勿用 tfx）
GCE_HOST=ubuntu@<GCE_STATIC_IP> bash scripts/linux/sync-from-gce.sh

cd apps/trading-app/src
python -m backtest --code TMFR1 --dates 2026-06-12
python -m reporting.calibration_cli ~/logs-from-gce/trading-app-uat.log --dates 2026-06-12
python -m sweep.determinism_check --date 2026-06-12 --mode hash
```

## 相關文件

- [`HYBRID_DEPLOY.md`](HYBRID_DEPLOY.md) — 地雲雙管架構、GCE 規格、資料同步
- [`WindowsOps.md`](WindowsOps.md) — Windows 單機部署（仍支援）
- [`docs/uat/APP.md`](../uat/APP.md)
- [`TODO.md`](../TODO.md)