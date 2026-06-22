# trading-app

> **Reference integrator app** for TAIFEX index-futures VWAP momentum — part of the [**tfx-trading**](https://github.com/timhwchuang/tfx-trading) monorepo.

> **建議部署：地雲雙管** — Live 放 **GCP GCE asia-east1** 或 **Windows**；回測 / CAL 放地端 Linux/macOS。見 [`docs/ops/HYBRID_DEPLOY.md`](../../docs/ops/HYBRID_DEPLOY.md)。

| 文件 | 用途 |
|------|------|
| [SPEC.md](SPEC.md) | App 層邊界、依賴方向、架構與資料流、公開 wiring API |
| [../../docs/uat/APP.md](../../docs/uat/APP.md) | App 層 UAT→Pilot 執行清單 |
| [../../docs/DOC_MAP.md](../../docs/DOC_MAP.md) | 全 monorepo 文件索引（高階導航） |
| [../../docs/ops/HYBRID_DEPLOY.md](../../docs/ops/HYBRID_DEPLOY.md) | GCE Live + 地端回測 |
| [../../docs/ops/LinuxOps.md](../../docs/ops/LinuxOps.md) | Linux / GCE systemd |
| [../../docs/ops/WindowsOps.md](../../docs/ops/WindowsOps.md) | Windows 排程 |
| [../../docs/AGENTS.md](../../docs/AGENTS.md) | AI / 開發安全護欄 |
| [../../CHANGELOG.md](../../CHANGELOG.md#trading-app) | 版本變更 |

**Monorepo packages**（從 repo 根 `bash scripts/setup-dev.sh`）：

- `packages/trading-engine` `@ v0.2.2`
- `packages/trading-backtest` `@ v0.1.1`
- `packages/strategies/vwap-momentum` `@ v0.1.2`

---

## 系統需求

| 角色 | 環境 |
|------|------|
| **Live（連線）** | Windows 10/11 **或** GCP GCE Ubuntu 24.04（[`HYBRID_DEPLOY.md`](../../docs/ops/HYBRID_DEPLOY.md)） |
| **回測 / 研究** | Linux / macOS 地端機 |
| 共通 | Python 3.11+、永豐 [Shioaji](https://sinotrade.github.io/) API 金鑰、時區 **Asia/Taipei** |

---

## 安裝（Windows 範例 `C:\tfx-trading`）

```powershell
git clone git@github.com:timhwchuang/tfx-trading.git C:\tfx-trading
cd C:\tfx-trading
# Git Bash：
bash scripts/setup-dev.sh
```

`.venv` 在 **monorepo 根** `C:\tfx-trading\.venv`，非 app 子目錄。

---

## 環境變數

密鑰**只**用環境變數，不寫入 `config.yaml`。建議放在 repo 外的 `uat-env.sh`（`chmod 600`），每次用 **`source`** 載入（不要用 `./`，否則 `export` 不會留在目前 shell）。

**UAT 模擬**（`simulation: true`）只需 `SJ_API_KEY` / `SJ_SEC_KEY`；須為永豐後台的**模擬** API Key（與正式 Key 不同）。`SJ_CA_*` 僅 Pilot（`simulation: false`）需要。

`LOG_FILE` 可放在 repo 內（例：`logs/trading-app-uat.log`）或 repo 外；`uat_report` 讀的是**同一個檔案路徑**，與 `LOG_FILE` 無魔法綁定。請先 `mkdir -p "$(dirname "$LOG_FILE")"`。

### PowerShell（Windows）

```powershell
$env:SJ_API_KEY = "your_api_key"
$env:SJ_SEC_KEY = "your_secret_key"
$env:SJ_CA_PATH = "C:\certs\Sinopac.pfx"      # Pilot 正式下單才需要
$env:SJ_CA_PASSWD = "your_ca_password"
$env:CONFIG_PATH = "C:\tfx-trading\apps\trading-app\config\config.yaml"
$env:LOG_FILE = "C:\logs\trading-app-uat.log"
$env:LOG_LEVEL = "INFO"
$env:TICK_ARCHIVE = "1"
$env:KBARS_ARCHIVE = "1"
```

### bash / zsh（macOS 冒煙測試或地端研究）

```bash
# 例：~/sinotrade/uat-env.sh（勿 commit）
export SJ_API_KEY="your_simulation_api_key"
export SJ_SEC_KEY="your_simulation_secret"
export LOG_FILE="/path/to/tfx-trading/logs/trading-app-uat.log"
export TICK_ARCHIVE=1
export KBARS_ARCHIVE=1
mkdir -p "$(dirname "$LOG_FILE")"

source ~/sinotrade/uat-env.sh   # 每次開 terminal 後、跑 live 前
source /path/to/tfx-trading/.venv/bin/activate
```

---

## 執行

```powershell
cd C:\tfx-trading\apps\trading-app\src
C:\tfx-trading\.venv\Scripts\python.exe -m live
```

或使用腳本：

```powershell
C:\tfx-trading\apps\trading-app\scripts\windows\start-trading-app.ps1 -MonorepoRoot C:\tfx-trading
```

| 用途 | 指令 | 完整參數 |
|------|------|----------|
| **指令總覽** | `python -m cli_help` | `python -m cli_help <module>` → 轉該模組 `--help` |
| Live / 模擬 | `python -m live` | `python -m live --help` |
| 回測 | `python -m backtest --code TMFR1 --dates 2026-06-12` | `python -m backtest --help` |
| UAT 日報 JSON | 見下方「收盤後指令」 | `python -m reporting --help` |
| 週 KPI 趨勢 | `python -m reporting reports/day*.json --trend`（**monorepo 根**） | 同上 |
| Episode 回放 | `python -m reporting "$LOG_FILE" --episodes` | 同上 |
| 證據 CSV | `python -m reporting.uat_evidence_export both reports/day*.json` | `python -m reporting.uat_evidence_export --help` |
| Pilot 預檢 | `python -m sweep.pilot_gate_check reports/day*.json` | `python -m sweep.pilot_gate_check --help` |
| Determinism | `python -m sweep.determinism_check --date YYYY-MM-DD --mode hash` | `python -m sweep.determinism_check --help` |
| Trend 校準 | `python -m reporting.calibration_cli "$LOG_FILE" --dates 2026-06-12` | `python -m reporting.calibration_cli --help` |
| 壓縮 tick | `python -m storage` | `python -m storage --help` |

首次請確認 `config/config.yaml` 中 **`simulation: true`**。

### 工作目錄（常踩坑）

| 指令 | 工作目錄 |
|------|----------|
| `python -m live` | `apps/trading-app/src` |
| `python -m reporting` / `storage` / `sweep.*` | **monorepo 根** + `export PYTHONPATH=apps/trading-app/src` |

在 `src/` 下執行 `> reports/day*.json` 會因路徑不存在而失敗；`reports/`、`tick_cache/` 都在 repo 根。

### 收盤後指令（monorepo 根）

```bash
cd /path/to/tfx-trading
source .venv/bin/activate
source ~/sinotrade/uat-env.sh    # 或你的 uat-env.sh
export PYTHONPATH=apps/trading-app/src
python -m storage                # 僅壓縮 tick_cache/*.csv；無 tick csv 時顯示 0 file(s) 為正常
python -m reporting "$LOG_FILE" --json > reports/day$(date +%Y%m%d).json
```

### 常見錯誤

| 現象 | 原因 | 處理 |
|------|------|------|
| `key not exist`（400） | 正式 Key 搭配 `simulation: true`，或變數未 `source` | 確認後台為**模擬** Key；`source uat-env.sh` 後再跑 |
| `reports/...` no such file | 在 `src/` 重導向輸出 | 改到 monorepo 根執行 `reporting` |
| `storage` 壓縮 0 檔 | 尚無 `tick_cache/{product_code}_YYYY-MM-DD.csv`（預設 `TMFR1`） | Phase 0 短跑正常；Phase 1 須跑滿交易日 |
| `Tick 落盤結束 \| written=0` | 執行時間太短或 tick 極少；或 live 用 `TickSnapshot` 未相容（已修） | Phase 0 冒煙可接受；以 log 內 `登入成功` + `DECISION_AUDIT` 為準 |
| kbars `ts` 比 tick 快 **8 小時** | 模擬 API 的 `kbars.ts` 與 tick 轉換方式不同（已依 `simulation` 修正） | 刪除舊 `*_kbars_*.csv` 讓 live 重寫；Pilot 前再驗正式 API |

---

## 專案結構（monorepo 內）

```text
tfx-trading/
├── packages/trading-engine/
├── packages/trading-backtest/
├── packages/strategies/vwap-momentum/
└── apps/trading-app/          ← 本目錄
    ├── config/config.yaml
    ├── src/                   # live, backtest, integrations, storage, reporting, sweep
    ├── scripts/windows/       # -MonorepoRoot C:\tfx-trading
    ├── tests/                   # 122 項整合測試（`run_tests.py`）
    └── run_tests.py
```

測試（在 `apps/trading-app/`）：`C:\tfx-trading\.venv\Scripts\python.exe run_tests.py`  
全 monorepo：`bash scripts/run-all-tests.sh`

---

## Disclaimer

個人研究用途。**UAT-ready ≠ Live-ready**。上線前請閱讀 [`docs/ops/LIVE_SAFETY.md`](../../docs/ops/LIVE_SAFETY.md) 與 [`docs/uat/KERNEL.md`](../../docs/uat/KERNEL.md)。