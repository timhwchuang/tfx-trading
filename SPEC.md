# tfx-trading — Monorepo Spec

> **Repo**: [`timhwchuang/tfx-trading`](https://github.com/timhwchuang/tfx-trading)  
> **文件地圖**: [`docs/DOC_MAP.md`](docs/DOC_MAP.md) · **Agent**: [`docs/AGENTS.md`](docs/AGENTS.md)  
> **歷史**: [`legacy/README.md`](legacy/README.md)

## 1. 定位

永豐 Shioaji 台指期（預設 `TMFR1`）**單一產品**：Host 狀態機 + storage + live + 極簡策略。

| 路徑 | 職責 |
|------|------|
| [`apps/trading-app`](apps/trading-app/SPEC.md) | 全部：`src/trading_engine`、storage、live、`strategy_simple` |
| [`legacy/`](legacy/README.md) | 舊 strategies / backtest / reporting（參考，不進 build） |

**依賴**：

```text
live / integrations → trading_engine (in-app) + Strategy Protocol
strategy_simple → trading_engine.core.strategy
```

不維護獨立 `packages/trading-engine` PyPI 發布。

## 2. 安裝與測試

```bash
python3 -m venv .venv && source .venv/bin/activate
bash scripts/setup-dev.sh
bash scripts/run-all-tests.sh
```

Live：`cd apps/trading-app/src && python -m live`（`simulation: true`）。

## 3. Host vs Strategy

- Host：session、風控（日損 / 連虧 → `block_new_entry`）、委託、tick archive。
- Strategy：`evaluate` / `manage_exit`；參數在策略自己的 dataclass。
- TAIFEX 交易日於 **15:00** 切換；夜盤+次日日盤共用風控預算。

## 4. Storage SSOT

`tick_cache/{code}_{date}.csv` = 交易日真相。見 [`apps/trading-app/src/storage/SPEC.md`](apps/trading-app/src/storage/SPEC.md)。

## 5. 安全

[`docs/AGENTS.md`](docs/AGENTS.md) §2 · [`docs/ops/LIVE_SAFETY.md`](docs/ops/LIVE_SAFETY.md)。
