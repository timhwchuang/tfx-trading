# trading-app

永豐 Shioaji 台指期產品：Host（`trading_engine`）+ storage + live + `strategy_simple`。

| Doc | Purpose |
|-----|---------|
| [SPEC.md](SPEC.md) | Product boundary |
| [../../docs/AGENTS.md](../../docs/AGENTS.md) | Safety + architecture |
| [../../docs/DOC_MAP.md](../../docs/DOC_MAP.md) | Doc index |
| [../../legacy/README.md](../../legacy/README.md) | Archived research |

## Install

```powershell
cd C:\tfx-trading
bash scripts/setup-dev.sh
```

## Environment

```powershell
$env:SJ_API_KEY = "your_api_key"
$env:SJ_SEC_KEY = "your_secret_key"
$env:CONFIG_PATH = "C:\tfx-trading\apps\trading-app\config\config.yaml"
$env:LOG_FILE = "C:\logs\trading-app-uat.log"
$env:TICK_ARCHIVE = "1"
$env:PYTHONPATH = "C:\tfx-trading\apps\trading-app\src"
```

## Run

```powershell
cd C:\tfx-trading\apps\trading-app\src
python -m live
python run_tests.py   # from apps/trading-app
```

Default strategy: **simple** — after each fill wait `flip_interval_sec` (default 300s), then flat→Buy / long→Sell. Session flatten is Host-owned. Host owns **no** strategy indicators (ATR/VWAP/trend/etc.). Day + night enabled in `config/config.yaml`.
