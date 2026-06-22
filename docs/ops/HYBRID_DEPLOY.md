# 地雲雙管部署（Hybrid: On-Prem Research + GCE Live）

> **目標**：Live 連線放 **GCP GCE（台灣區）** 維持穩定；回測、CAL-8、determinism、週報分析放 **地端 Linux/macOS**，以同步的 `tick_cache` 為 SSOT。

## 1. 架構總覽

```text
┌─────────────────────────────┐         rsync (收盤後)        ┌──────────────────────────────┐
│  地端（Linux / macOS）       │  ◄──── tick_cache, reports ─── │  GCP GCE asia-east1（台灣）   │
│  • backtest / sweep          │                               │  • python -m live（雙管模式單一 live 節點） │
│  • calibration_cli (CAL-8)   │  ───► config.yaml (git) ───►  │  • TICK_ARCHIVE / KBARS       │
│  • determinism_check         │                               │  • systemd 守護 + 靜態 IP     │
│  • reporting / pilot_gate    │                               │  • post-session.sh            │
└─────────────────────────────┘                               └──────────────────────────────┘
         tick_cache/  ← SSOT for replay ───────────────────────────────►  同目錄結構
```

| 層 | 地端 | GCE |
|----|------|-----|
| **Live 連線** | 不建議（雙管模式） | **是**（Shioaji 長連線）；或 Windows 單機（§5） |
| **tick_cache / kbar_cache 寫入** | 從 GCE sync 讀 | **是**（盤中 archive） |
| **回測 / CAL** | **是** | 僅 smoke test |
| **UAT 證據 git** | commit 分析結果 | commit 當日 `reports/`、`snapshots/` |
| **config SSOT** | git `apps/trading-app/config/config.yaml` | 部署時 pull 同 commit |

## 2. 為何 GCE Live + 地端回測

| 痛點 | 作法 |
|------|------|
| 家裡/公司網路不穩、VPN、睡眠 | GCE 24/7 穩定 egress、無睡眠 |
| 回測吃 RAM/CPU、不想與 live 搶資源 | 地端或大規格工作站跑 `backtest` / `calibration_cli` |
| 資料要可重現 | 收盤後 `rsync` 拉回 `tick_cache/*.csv.gz`，地端 hash 比對 |
| 台灣券商 API 延遲 | **asia-east1**（彰化）區域 |

## 3. GCP GCE 建議規格

### UAT / Pilot（單策略、單口、微台 `TMFR1`）

預設商品見 `apps/trading-app/config/config.yaml`（`product_code`）。大台 `TXFR1`、小台 `MXFR1` 亦可，但點數參數相同、每點金額與流動性不同，需分開累積 `tick_cache` 並重跑校準。

| 項目 | 建議 |
|------|------|
| **區域** | `asia-east1`（Taiwan） |
| **機型** | `e2-standard-2`（2 vCPU，8 GB RAM） |
| **磁碟** | 50 GB `pd-balanced`（boot）；`tick_cache` 成長後可獨立掛 100 GB data disk |
| **IP** | **Regional static external IP**（Shioaji 連線穩定、防火牆白名單若需要） |
| **OS** | Ubuntu 24.04 LTS |
| **網路** | 預設 VPC egress 即可；**勿用 Preemptible/Spot** 跑 live |

### 升級時機

| 情境 | 升級 |
|------|------|
| `TICK_ARCHIVE` + 高頻 tick、CPU 常 >70% | `e2-standard-4`（4 vCPU，16 GB） |
| 磁碟 >70% | 加掛 data disk 或擴容；排程 `python -m storage` |
| 要同機跑輕量 reporting | 維持 live 專用；reporting 放地端 |

### 每月成本粗估（2026，僅供規劃）

- `e2-standard-2` + 50GB + 靜態 IP：約 USD 50–70/月（以 GCP 計價器為準）
- 地端機器已有則 **不加 live 負載**，只付 GCE

## 4. 部署步驟（摘要）

### 4.1 GCE Live 節點

1. 建立 VM（規格見 §3），綁定靜態 IP，SSH 登入
2. `git clone` → `bash scripts/setup-dev.sh`
3. `sudo MONOREPO_ROOT=/opt/tfx-trading bash scripts/linux/install-systemd.sh`（`chown tfx:tfx` 整個 repo）
4. 編輯 `/etc/tfx-trading/env`（API keys；`TICK_ARCHIVE=1`、`KBARS_ARCHIVE=1` 已預設）
5. `sudo systemctl start tfx-trading`；盤中確認 `tick_cache/TMFR1_*.csv`（或你的 `product_code`）成長
6. cron：`scripts/linux/post-session.sh`（15:30）— `storage` + `reporting` + `determinism_check` → `snapshots/`
7. **git pull** 用 `sudo -u tfx git -C /opt/tfx-trading pull`（repo 屬 `tfx`）

詳見 [`LinuxOps.md`](LinuxOps.md)。

### 4.2 地端研究機

1. 同 repo clone + `setup-dev.sh`（不必裝 Shioaji 憑證若只回測）
2. 收盤後：

```bash
# 用 deploy 帳號（如 ubuntu@），勿用 tfx（nologin 無法 SSH）
GCE_HOST=ubuntu@<GCE_STATIC_IP> REMOTE_ROOT=/opt/tfx-trading \
  bash scripts/linux/sync-from-gce.sh
# 要拉 log 做 calibration_cli：SYNC_LOGS=1 GCE_HOST=ubuntu@... bash scripts/linux/sync-from-gce.sh
```

3. 地端跑：

```bash
cd apps/trading-app/src
python -m backtest --code TMFR1 --dates 2026-06-12
python -m reporting ../../../reports/day*.json --trend
python -m sweep.determinism_check --date 2026-06-12 --mode hash
```

### 4.3 資料與 git 紀律

| 路徑 | 誰寫 | 同步 |
|------|------|------|
| `tick_cache/` | GCE live | rsync → 地端 |
| `kbar_cache/` | GCE live（`KBARS_ARCHIVE=1`） | rsync → 地端 |
| `reports/day*.json` | GCE `post-session.sh` | rsync → 地端 |
| `snapshots/determinism_*.txt` | GCE `post-session.sh` | rsync → 地端 |
| `uat_evidence/` | 人類 | git |
| `config/config.yaml` | git | GCE `git pull` 部署 |

**勿**把 API 金鑰 commit 進 git；GCE 用 `/etc/tfx-trading/env`。

## 5. Windows 單機方案（仍支援）

若只有 Windows UAT 機、暫不開 GCE，沿用 [`WindowsOps.md`](WindowsOps.md) 即可。  
雙管是**建議架構**，不是 UAT gate 硬性要求；Pilot 前需證明連線穩定（Windows 或 GCE 擇一）。

## 6. 驗收檢查

- [ ] GCE `systemctl status tfx-trading` active（交易時段）
- [ ] 地端 `sync-from-gce.sh` 後 `tick_cache` 與 GCE 一致
- [ ] 地端 `determinism_check` hash 與 GCE `snapshots/` 一致
- [ ] 地端 `run-all-tests.sh` 全綠（269 tests，以實際 `Ran` 為準）
- [ ] [`uat/APP.md`](../uat/APP.md) Phase 0–1 證據路徑填寫（GCE 或 Windows）

## 相關文件

- [`LinuxOps.md`](LinuxOps.md) · [`WindowsOps.md`](WindowsOps.md)
- [`uat/APP.md`](../uat/APP.md) · [`TODO.md`](../TODO.md)
- 根 [`SPEC.md`](../../SPEC.md) §2、§7