# tfx-trading — Monorepo Spec (整合入口)

> **Repo**: [`timhwchuang/tfx-trading`](https://github.com/timhwchuang/tfx-trading)  
> **架構**: [`docs/Architecture.md`](docs/Architecture.md) · **文件地圖**: [`docs/DOC_MAP.md`](docs/DOC_MAP.md)  
> **遷移細節**: [`monorepo/SPEC.md`](monorepo/SPEC.md) · [`monorepo/Plan.md`](monorepo/Plan.md)

---

## 1. 定位

台指期（TXF）個人研究用 **monorepo**：kernel、回測、可插拔策略、Windows UAT 整合，單一 `git clone` 即可開發。

| 路徑 | pip 名稱 | import | 職責 |
|------|----------|--------|------|
| [`packages/trading-engine`](packages/trading-engine/SPEC.md) | `trading-engine` | `trading_engine` | 狀態機、risk、broker adapters、Strategy Protocol |
| [`packages/trading-backtest`](packages/trading-backtest/SPEC.md) | `trading-backtest` | `trading_backtest` | Tick replay、MockBroker |
| [`packages/strategies/vwap-momentum`](packages/strategies/vwap-momentum/SPEC.md) | `strategy-vwap-momentum` | `strategy_vwap_momentum` | VWAP momentum plugin（entry point `vwap_momentum`） |
| [`apps/trading-app`](apps/trading-app/SPEC.md) | — | `src/` on path | Config、落盤、reporting、sweep、Windows 執行 |

**依賴方向**（不可逆向）：

```text
apps/trading-app → trading-engine, trading-backtest, strategy-*
trading-backtest → trading-engine
packages/strategies/* → trading-engine
```

---

## 2. 安裝與測試

```bash
git clone git@github.com:timhwchuang/tfx-trading.git
cd tfx-trading
python3 -m venv .venv && source .venv/bin/activate
bash scripts/setup-dev.sh
bash scripts/run-all-tests.sh
```

Windows 執行與 UAT：[`apps/trading-app/README.md`](apps/trading-app/README.md)

---

## 3. 模組 SPEC（各 package 為真相來源）

| 主題 | 文件 |
|------|------|
| Engine 狀態機 / Protocol | [`packages/trading-engine/SPEC.md`](packages/trading-engine/SPEC.md) |
| 回測宿主契約 | [`packages/trading-engine/docs/BACKTEST_HOST_CONTRACT.md`](packages/trading-engine/docs/BACKTEST_HOST_CONTRACT.md) |
| MockBroker / 回放 | [`packages/trading-backtest/docs/BACKTEST_IMPLEMENTATION.md`](packages/trading-backtest/docs/BACKTEST_IMPLEMENTATION.md) |
| VWAP 策略參數與 audit | [`packages/strategies/vwap-momentum/SPEC.md`](packages/strategies/vwap-momentum/SPEC.md) |
| App 整合邊界 | [`apps/trading-app/SPEC.md`](apps/trading-app/SPEC.md) |
| Param sweep | [`apps/trading-app/docs/SWEEP_SPEC.md`](apps/trading-app/docs/SWEEP_SPEC.md) |

---

## 4. 新策略（研究驗證）

1. 複製 `packages/strategies/vwap-momentum/` → `packages/strategies/<name>/`
2. 註冊 `pyproject.toml` entry point `trading_engine.strategies`
3. 加入 `scripts/setup-dev.sh` 與 `run-all-tests.sh`
4. App 載入：[`load_named_strategy()`](apps/trading-app/src/integrations/engine_wiring.py)（可選 `config.yaml` `strategy.name`）

詳見 [`monorepo/SPEC.md` §6](monorepo/SPEC.md).

---

## 5. 版本與發布

各 package 保留獨立 `version` + `CHANGELOG.md`（主要歷史來源）。Monorepo 發布 SOP：

1. 改動 → `bash scripts/run-all-tests.sh` 全綠  
2. 更新相關 `CHANGELOG.md`  
3. commit；可選 monorepo tag  

**注意**：不再建立新的 `docs/releases/vX.Y.Z.md`。歷史釋出記錄已移至各 `docs/ARCHIVE/releases/`。舊 standalone git+ 安裝範例僅供考古。

舊四 repo 已封存；歷史 tag 仍指向舊 GitHub，**現行開發僅此 repo**。

---

## 6. 安全與 UAT

- AI / 開發紀律：[`apps/trading-app/AGENTS.md`](apps/trading-app/AGENTS.md)
- Kernel UAT：[`packages/trading-engine/docs/UAT_CHECKLIST.md`](packages/trading-engine/docs/UAT_CHECKLIST.md)
- App UAT：[`apps/trading-app/docs/UAT_CHECKLIST.md`](apps/trading-app/docs/UAT_CHECKLIST.md)
- Pilot 前：[`packages/trading-engine/docs/LIVE_SAFETY.md`](packages/trading-engine/docs/LIVE_SAFETY.md)、[`apps/trading-app/docs/BeforePilot.md`](apps/trading-app/docs/BeforePilot.md)