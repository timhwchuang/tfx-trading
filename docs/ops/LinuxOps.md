# Linux 運維清單（開發 / 回測 / GCE Live）

> **角色**：Linux 用於 (1) macOS/Linux **地端研究與回測**、(2) **GCP GCE Live 連線**（見 [`HYBRID_DEPLOY.md`](HYBRID_DEPLOY.md)）。  
> **Monorepo 根目錄預設**：`/opt/tfx-trading`（GCE）或 `~/tfx-trading`（地端開發機）。

## GCE Live 節點（已部署，2026-06-23）

> **SSOT**：GCE 規格、目錄、cron 以此節為準。  
> **勿 commit**：`<deploy-user>`、`<gce-instance-id>`、靜態 IP、API/Telegram 金鑰（實際值記 GCP Console 或本機 ops 筆記）。

| 項目 | 值 |
|------|-----|
| **Instance** | `<gce-instance-id>`（GCP Console → VM instances） |
| **區域** | `asia-east1`（台灣） |
| **機型** | `e2-medium`（2 vCPU，4 GB RAM；自 `e2-small` 升級） |
| **Boot 磁碟** | 20 GB |
| **OS** | Debian 13 (trixie) |
| **SSH 部署帳號** | `<deploy-user>`（`sync-from-gce.sh` / rsync；**勿用** `tfx`） |
| **GCP 開關機排程** | **08:30–14:00**（Asia/Taipei，週一至五） |
| **時區** | `Asia/Taipei`（`timedatectl set-timezone Asia/Taipei`） |

### 目錄結構（GCE）

```text
/opt/tfx-trading/                 # monorepo 根（owner: tfx；install-systemd 後）
├── .venv/                        # Python venv（setup-dev.sh）
├── apps/trading-app/
│   ├── config/config.yaml
│   └── src/                      # systemd WorkingDirectory；python -m live
├── packages/ · scripts/ · docs/
├── tick_cache/                   # ticks + kbars（UAT archive / backfill）
├── reports/                      # post-session：dayYYYYMMDD.json
└── snapshots/                    # post-session：determinism_YYYYMMDD.txt

/etc/tfx-trading/env              # SJ_*、LOG_FILE、TICK_ARCHIVE 等（640 root:tfx）
/var/log/tfx-trading/
├── trading-app-uat.log           # UAT log（午夜輪替 *.log.YYYY-MM-DD，保留 14 天）
└── post-session.log              # cron 輸出
```

**盤中 live 直接產出**：`tick_cache/`（tick + kbars）、`LOG_FILE`。  
**收盤後 `post-session.sh`**：`reports/`、`snapshots/`；舊日 tick `.csv` → `.csv.gz`（當日 `.csv` 預設不壓）。

### 交易日時間軸（台北）

```text
08:30  GCP 排程開機 → systemd enable → tfx-trading 自動 start
08:45  config session.start（策略允許交易）
13:45  session.end
13:50  root cron：systemctl stop tfx-trading（flush log、DAILY_SUMMARY）
13:54  tfx cron：post-session.sh
14:00  GCP 排程關機
```

> **順序**：必須 **先 stop live，再 post-session**（否則 `DAILY_SUMMARY` 可能尚未寫入 log）。  
> **關機緩衝**：若 `determinism_check` 常超過 6 分鐘，將 GCP 關機延至 **14:10** 或 cron 提前至 **13:48**。

### Cron（已設定）

```bash
# root（sudo crontab -e）
50 13 * * 1-5 systemctl stop tfx-trading

# tfx（sudo crontab -u tfx -e）
54 13 * * 1-5 /opt/tfx-trading/scripts/linux/post-session.sh >> /var/log/tfx-trading/post-session.log 2>&1
```

### 部署 / 更新 code

| 方式 | 命令 |
|------|------|
| VM 上 git pull | `sudo -u tfx git -C /opt/tfx-trading pull`（repo 屬 `tfx`；`<deploy-user>` 直接 git 會 dubious ownership） |
| 地端 rsync 推版 | 本機 repo → `gcloud compute scp` / rsync（排除 `.venv`、`.git`、`tick_cache`）→ VM 後 `chown -R tfx:tfx` |
| 依賴變更後 | `bash scripts/setup-dev.sh` → `sudo systemctl restart tfx-trading` |

### 地端拉回資料

```bash
GCE_HOST=<deploy-user>@<GCE_STATIC_IP> REMOTE_ROOT=/opt/tfx-trading \
  bash scripts/linux/sync-from-gce.sh
# 含 log：SYNC_LOGS=1 GCE_HOST=<deploy-user>@<GCE_STATIC_IP> ...
```

若本機仍殘留舊版 `kbar_cache/`（已廢棄），遷移 kbars 至 `tick_cache/` 後刪除：

```bash
bash scripts/linux/migrate-legacy-kbar-cache.sh
# 預覽：bash scripts/linux/migrate-legacy-kbar-cache.sh --dry-run
```

### 基礎設施監控（VM 掛了 Telegram 不會響）

應用層 Telegram 僅涵蓋**盤中交易異常**；VM 死活須靠 **GCP Monitoring**（交易時段 instance 非 RUNNING 告警 + email）或外部 heartbeat。Ops Agent 選裝（磁碟 >80% 告警）。見 [`HYBRID_DEPLOY.md`](HYBRID_DEPLOY.md) §3。

## P4-0 上線前檢查（GCE Live 節點）

- [x] Debian 13 (trixie)；時區 **Asia/Taipei**；`timedatectl set-ntp true`
- [x] 已部署至 `/opt/tfx-trading`；`setup-dev.sh` + `install-systemd.sh`；`systemctl enable tfx-trading`
- [ ] `bash scripts/run-all-tests.sh` 於 VM 全綠（選做；冒煙已通過 login）
- [x] 環境變數（`/etc/tfx-trading/env`，`chmod 640` root:tfx）：
  - `SJ_API_KEY` / `SJ_SEC_KEY`（**模擬** Key；`simulation: true`）
  - `LOG_FILE=/var/log/tfx-trading/trading-app-uat.log`
  - `CONFIG_PATH=/opt/tfx-trading/apps/trading-app/config/config.yaml`
  - `TICK_ARCHIVE=1`、`KBARS_ARCHIVE=1`
  - 選配：`TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` 或 `ALERT_WEBHOOK_URL`
- [x] `config.yaml` → `simulation: true`（UAT）
- [ ] **靜態外部 IP**（建議）；ingress SSH；egress 443
- [x] GCP instance schedule **08:30–14:00** + root/tfx cron（§GCE）
- [x] `systemd` 守護 live；登入 smoke：`登入成功 | 合約: TMFR1 | 模擬: True`（2026-06-23）

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

**GCP 14:00 關機**時，用 §GCE 的 **13:50 stop → 13:54 post-session**（勿單獨 15:30，VM 已關）。

若 VM **24/7 常開**，可用：

```bash
# root：先停 live
50 15 * * 1-5 systemctl stop tfx-trading
# tfx：再維護
54 15 * * 1-5 /opt/tfx-trading/scripts/linux/post-session.sh >> /var/log/tfx-trading/post-session.log 2>&1
```

手動驗證：

```bash
sudo systemctl stop tfx-trading
sudo -u tfx /opt/tfx-trading/scripts/linux/post-session.sh
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
GCE_HOST=<deploy-user>@<GCE_STATIC_IP> bash scripts/linux/sync-from-gce.sh

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