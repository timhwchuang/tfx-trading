# tfx-trading

Monorepo for Taiwan TXF futures research: **trading-engine** kernel, **trading-backtest** replay, pluggable **strategies**, and **trading-app** Windows UAT integrator.

> Personal research / simulation — not investment advice. UAT-ready ≠ live-ready.

| 文件 | 用途 |
|------|------|
| [docs/DOC_MAP.md](docs/DOC_MAP.md) | **全文件索引（入口）** |
| [docs/TODO.md](docs/TODO.md) | 路線圖、未完成項 |
| [CHANGELOG.md](CHANGELOG.md) | 版本變更（全 monorepo） |
| [LICENSE](LICENSE) | MIT |
| [SPEC.md](SPEC.md) | Monorepo 整合規格（高階；含 §7 架構與資料流） |
| [docs/AGENTS.md](docs/AGENTS.md) | AI / 開發安全護欄 |
| [prompts/roles/senior-trading-professional.md](prompts/roles/senior-trading-professional.md) | 資深交易人員 role（Grok **`/senior-trading-professional`**） |
| [apps/trading-app/README.md](apps/trading-app/README.md) | Windows 安裝、執行、UAT |

## Quick start

```bash
git clone git@github.com:timhwchuang/tfx-trading.git
cd tfx-trading
python3 -m venv .venv
source .venv/bin/activate   # Windows: .\.venv\Scripts\activate
bash scripts/setup-dev.sh
bash scripts/run-all-tests.sh
```

## Layout

```text
.grok/skills/                     # Grok project skills
prompts/roles/                    # AI role definitions + gate references
packages/trading-engine/          # kernel
packages/trading-backtest/        # tick replay
packages/strategies/vwap-momentum/  # VWAP strategy plugin
apps/trading-app/                 # config, storage, reporting, live entry
```

## Run (after setup)

```bash
cd apps/trading-app/src
python -m live          # simulation default — see config/config.yaml
python -m backtest --code TXFR1 --dates 2026-06-12
```

## CLI 指令（trading-app）

> **原則**：每個模組用 `python -m <module> --help` 查完整參數；下列為索引。  
> Windows UAT 從 monorepo 根執行時請設 `$env:PYTHONPATH="apps\trading-app\src"`。

| 模組 | 用途 | 說明 |
|------|------|------|
| `cli_help` | **指令總覽** | `python -m cli_help` 或 `python -m cli_help reporting` |
| `live` | 模擬 / 連線交易 | `python -m live --help` |
| `backtest` | Tick 回放回測 | `python -m backtest --help` |
| `reporting` | UAT log / JSON KPI | `python -m reporting --help` |
| `reporting.uat_evidence_export` | 券商對帳 + tick CSV | `python -m reporting.uat_evidence_export --help` |
| `sweep.pilot_gate_check` | Phase 5 Pilot 預檢 | `python -m sweep.pilot_gate_check --help` |
| `sweep.determinism_check` | 可重現性 hash | `python -m sweep.determinism_check --help` |
| `reporting.calibration_cli` | Trend filter 校準（CAL-8） | `python -m reporting.calibration_cli --help` |
| `storage` | 壓縮 tick_cache | `python -m storage --help` |

UAT 流程逐步 SOP：[`docs/uat/APP.md`](docs/uat/APP.md) · Windows 細節：[`apps/trading-app/README.md`](apps/trading-app/README.md)

## Migrated from

Former sibling repos (`trading-engine`, `trading-backtest`, `strategy-vwap-momentum`, `trading-app`) are **archived** on GitHub. Development continues here only.