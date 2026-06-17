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

## Migrated from

Former sibling repos (`trading-engine`, `trading-backtest`, `strategy-vwap-momentum`, `trading-app`) are **archived** on GitHub. Development continues here only.