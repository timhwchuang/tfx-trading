# strategy-vwap-momentum

**Reference VWAP momentum + higher-timeframe trend filter strategy plugin for `trading-engine`.**

這是 `trading-engine` 架構下第一個公開的 `strategy-<name>` 參考實作（VWAP momentum pullback 進場 + P6-1 trend 濾網 + ATR 動態 trail / vwap-stop 出場）。

**本策略實作為作者個人研究與學習用途而公開，不構成投資建議、交易邀約或獲利保證。** 任何實盤或模擬交易之決策、參數設定、資金配置，以及因此產生的盈虧、漏單或其他損失，**均由使用者自行承擔**。作者與貢獻者不對任何直接或間接損害負責。

> 上實盤（或大規模回測）前請務必：
> 1. 完整閱讀 [trading-engine docs/LIVE_SAFETY.md](https://github.com/timhwchuang/trading-engine/blob/main/docs/LIVE_SAFETY.md) 與 [UAT_CHECKLIST.md](https://github.com/timhwchuang/trading-engine/blob/main/docs/UAT_CHECKLIST.md)
> 2. 在 simulation / paper trade 跑過完整交易日
> 3. 使用 `engine.get_state_snapshot()` 唯讀觀察狀態，**切勿**直接修改 engine 內部屬性

| 文件 | 用途 |
|------|------|
| [SPEC.md](SPEC.md) | 策略定位、完整參數表、決策邏輯細節、trend Level-2 語意、audit reason、遷移說明 |
| [CHANGELOG.md](CHANGELOG.md) | 版本變更紀錄 |
| trading-engine `docs/STRATEGY.md` | Strategy Protocol MUST / MUST NOT（必讀） |

## Status

**0.1.2** — 參考 strategy plugin；搭配 **trading-engine v0.2.2+**（`atr_stale` / reconnect warmup gates）。

## Install（GitHub only，不上 PyPI）

```bash
# 鎖定 tag（建議）
pip install "strategy-vwap-momentum @ git+https://github.com/timhwchuang/strategy-vwap-momentum.git@v0.1.2"

# 搭配 trading-engine（通常一起鎖）
pip install "trading-engine @ git+https://github.com/timhwchuang/trading-engine.git@v0.2.2"
```

在你的 app / backtest repo 的 `pyproject.toml`：

```toml
dependencies = [
  "trading-engine @ git+https://github.com/timhwchuang/trading-engine.git@v0.2.2",
  "strategy-vwap-momentum @ git+https://github.com/timhwchuang/strategy-vwap-momentum.git@v0.1.2",
]
```

### 本地開發（workspace 或單獨 clone）

```bash
git clone https://github.com/timhwchuang/strategy-vwap-momentum.git
cd strategy-vwap-momentum
pip install -e ".[dev]"          # 含 ruff / mypy
# 同時需要 trading-engine（可 sibling pip -e ../trading-engine 或上面 git 安裝）
```

## Usage

### 1. 注入 TradingEngine（live 或 kernel test）

```python
from trading_engine import TradingEngine, RuntimeConfig, Settings
from trading_engine.adapters.shioaji import ShioajiOrderAdapter
from trading_engine.adapters.shioaji_live import ShioajiLiveBootstrap
# ... 其他 ports

from strategy_vwap_momentum import VWAPMomentumStrategy, StrategyParams

settings = Settings(...)          # 你的 app 從 yaml/env 載入
cfg = RuntimeConfig(settings)
strategy = VWAPMomentumStrategy(params=StrategyParams.from_runtime_config(cfg))

engine = TradingEngine(
    api=...,
    strategy=strategy,
    runtime_config=cfg,
    order_adapter=ShioajiOrderAdapter(api=...),
    # telemetry, trend_refresh, alerts, archive ...
)

ShioajiLiveBootstrap(engine).start_live()
```

### 2. 使用 entry point 動態載入（推薦給 CLI / 通用 app）

```python
from importlib.metadata import entry_points

eps = entry_points(group="trading_engine.strategies")
factory = next(ep for ep in eps if ep.name == "vwap_momentum").load()
strategy = factory(params=StrategyParams.from_runtime_config(cfg))
```

trading-engine 也提供 `load_strategy("vwap_momentum", params=...)` 方便函式（見 trading-engine `plugins.py`）。

### 3. Backtest / Replay（與 live 使用完全相同 strategy instance）

由 `trading-backtest` 負責 replay loop 與 MockBroker。你只要把上面建好的 `strategy` 傳給 `BacktestEngine` 即可。

```python
from trading_backtest import BacktestEngine
# ...
bt = BacktestEngine(code="TXFR1", dates=[...], strategy=strategy, runtime_config=cfg, ...)
bt.run()
```

## 參數總覽（StrategyParams）

完整說明與校準建議請見 [SPEC.md](SPEC.md) §4。

關鍵類別（皆來自 RuntimeConfig overlay，可在 sweep 時動態 patch）：
- 進場：`entry_band_points`、`exhaustion_vol`、`momentum_buy_ratio` / `momentum_sell_ratio`、`min_atr_threshold`
- 出場：`hard_stop_points`、`fixed_tp_points`、`vwap_stop_points` + ATR 動態（`atr_vwap_stop_enabled`、`vwap_stop_*_floor` / `*_atr_k`）
- 移動停損：`trail_points` + ATR 動態 + `exit_grace_*`
- 風險控管：`max_consecutive_loss`
- 濾網：`trend_filter_enabled` + trend 相關（`trend_min_strength` 等，建議搭配 ATR normalization）

## 核心行為保證（本策略）

- Momentum 啟動條件：量能門檻 + 買/賣比率 + ATR 足夠 + 無持倉 + 風險 gate 允許。
- Pullback 進場：必須同時「貼近 VWAP」**且**「量能枯竭」，並通過 trend filter（若開啟）。
- Trend veto 會發出完整 `reason="trend_veto"` 的 SIGNAL_AUDIT（含 trend_dir/strength），供後續校準分析。
- 出場優先順序與 grace period：grace 內只認 hard stop；grace 後 VWAP stop 才生效。
- ATR 動態 trail / vwap stop：可獨立開關，floor + k 係數控制下限與敏感度。
- Session force flatten：kernel 主導，plugin 可客製 slippage 與 audit reason。
- 冷卻、pending、block_new_entry、daily loss 等 gate **完全尊重** RiskGate（由 trading-engine 計算並傳入）。

詳見 [SPEC.md](SPEC.md) 的決策流程與 trend 語意警告。

## Testing

```bash
python run_tests.py
```

目前約 **27** 個測試（workspace 統計），重點涵蓋：
- trend 數學（EMA warmup、resample 保證最新 bar、slope、ATR normalization、Level-2 min_strength gate）
- 行為邊界：exit grace、cooldown 使用 exchange timestamp、session force flatten、trend veto 正確產生 audit
- 整合風格測試透過 `trading_engine.testing` helpers

CI（見 `.github/workflows/tests.yml`）會安裝指定版本的 trading-engine 後執行，並跑 ruff + mypy。

## Architecture

```
strategy_vwap_momentum/
├── __init__.py                 # 公開 surface + __version__
├── strategy.py                 # VWAPMomentumStrategy（evaluate / manage_exit / audit）
├── params.py                   # StrategyParams + sweep / patch 工具
└── trend.py                    # compute_trend + dynamic ATR helpers + trend_allows_entry（純函式）
```

- 決策完全不依賴全域狀態或 broker。
- 所有可調參數走 `RuntimeConfig` overlay，方便參數 sweep 與 A/B 校準。
- Momentum 狀態（`active`、`direction`、`trigger_time`）**嚴格留在 plugin 內**（`peak` 為歷史死碼，已移除），不洩漏到 Protocol。

## 版本

```python
import strategy_vwap_momentum
print(strategy_vwap_momentum.__version__)  # 0.1.0
```

與 trading-engine 版本策略對齊（0.x 期間 API 仍可能微調）。

## 延伸與貢獻

本 package 同時作為未來 `strategy-starter` 模板的參考來源。如果你想開發自己的策略：

1. 實作 `trading_engine.core.strategy.BaseStrategy`（或直接 `Strategy` Protocol）
2. 只 import trading-engine 公開的 core types / Strategy / SignalAudit
3. 提供自己的 entry point
4. 寫純單元測試（mock MarketSnapshot 等）

歡迎在 trading-engine / 本 repo 提出 issue 討論 Protocol 演進或參數校準經驗。

## License

MIT — see [LICENSE](LICENSE).

---

**再次提醒**：這是研究參考實作。請在 simulation / paper 階段充分驗證，並嚴格遵守 trading-engine 的安全守則與 UAT 流程。作者不承擔任何交易損失責任。
