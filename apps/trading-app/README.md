# trading-app

> **Reference integrator app** for TXF VWAP momentum on Windows — part of the [**tfx-trading**](https://github.com/timhwchuang/tfx-trading) monorepo.

> **目標執行環境：Windows**（開發、UAT、Pilot 皆以 Windows 為準。）

| 文件 | 用途 |
|------|------|
| [SPEC.md](SPEC.md) | App 層邊界、依賴方向、架構與資料流、公開 wiring API |
| [../../docs/uat/APP.md](../../docs/uat/APP.md) | App 層 UAT→Pilot 執行清單 |
| [../../docs/DOC_MAP.md](../../docs/DOC_MAP.md) | 全 monorepo 文件索引（高階導航） |
| [../../docs/AGENTS.md](../../docs/AGENTS.md) | AI / 開發安全護欄 |
| [../../CHANGELOG.md](../../CHANGELOG.md#trading-app) | 版本變更 |

**Monorepo packages**（從 repo 根 `bash scripts/setup-dev.sh`）：

- `packages/trading-engine` `@ v0.2.2`
- `packages/trading-backtest` `@ v0.1.1`
- `packages/strategies/vwap-momentum` `@ v0.1.2`

---

## 系統需求

- **Windows 10 / 11** 或 Windows Server
- **Python 3.11+**、Git Bash（執行 `setup-dev.sh`）
- 永豐金 [Shioaji](https://sinotrade.github.io/) API 金鑰
- 系統時區 **(UTC+08:00) 台北**

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

## 環境變數（PowerShell）

```powershell
$env:SJ_API_KEY = "your_api_key"
$env:SJ_SEC_KEY = "your_secret_key"
$env:SJ_CA_PATH = "C:\certs\Sinopac.pfx"      # 正式下單
$env:SJ_CA_PASSWD = "your_ca_password"
$env:CONFIG_PATH = "C:\tfx-trading\apps\trading-app\config\config.yaml"
$env:LOG_FILE = "C:\logs\trading-app-uat.log"
$env:LOG_LEVEL = "INFO"
$env:TICK_ARCHIVE = "1"
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
| 回測 | `python -m backtest --code TXFR1 --dates 2026-06-12` | `python -m backtest --help` |
| UAT 日報 JSON | `python -m reporting %LOG_FILE% --json` | `python -m reporting --help` |
| 週 KPI 趨勢 | `python -m reporting ..\..\..\reports\day*.json --trend` | 同上 |
| Episode 回放 | `python -m reporting %LOG_FILE% --episodes` | 同上 |
| 證據 CSV | `python -m reporting.uat_evidence_export both ..\..\..\reports\day*.json` | `python -m reporting.uat_evidence_export --help` |
| Pilot 預檢 | `python -m sweep.pilot_gate_check ..\..\..\reports\day*.json` | `python -m sweep.pilot_gate_check --help` |
| Determinism | `python -m sweep.determinism_check --date YYYY-MM-DD --mode hash` | `python -m sweep.determinism_check --help` |
| 壓縮 tick | `python -m storage` | `python -m storage --help` |

首次請確認 `config/config.yaml` 中 **`simulation: true`**。

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
    ├── tests/                   # 116+ 項整合測試
    └── run_tests.py
```

測試（在 `apps/trading-app/`）：`C:\tfx-trading\.venv\Scripts\python.exe run_tests.py`  
全 monorepo：`bash scripts/run-all-tests.sh`

---

## Disclaimer

個人研究用途。**UAT-ready ≠ Live-ready**。上線前請閱讀 [`docs/ops/LIVE_SAFETY.md`](../../docs/ops/LIVE_SAFETY.md) 與 [`docs/uat/KERNEL.md`](../../docs/uat/KERNEL.md)。