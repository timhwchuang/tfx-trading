# tfx-trading

永豐 Shioaji 台指期：**單一 app**（Host 狀態機 + storage + live + `strategy_simple`）。

> Personal research / simulation — not investment advice.

| Doc | Purpose |
|-----|---------|
| [docs/DOC_MAP.md](docs/DOC_MAP.md) | Document index |
| [docs/AGENTS.md](docs/AGENTS.md) | AI safety + architecture |
| [CHANGELOG.md](CHANGELOG.md) | Version history |
| [SPEC.md](SPEC.md) | Integration SPEC |
| [apps/trading-app/README.md](apps/trading-app/README.md) | Install / live UAT |
| [legacy/README.md](legacy/README.md) | Archived research |

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
apps/trading-app/            # product (includes src/trading_engine)
legacy/                      # prior strategies / reporting / backtest
tick_cache/                  # SSOT landed ticks
```

## Run

```bash
cd apps/trading-app/src
python -m live
python -m storage --help
python -m backfilldata --help
```
