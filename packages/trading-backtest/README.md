# trading-backtest

**Deterministic tick replay driver for `trading-engine`.**

Replays historical tick data through the **exact same `TradingEngine`** used for live trading (single-threaded, sync order mode, VirtualClock). Provides `MockBroker` (IOC matching with heuristic slippage/latency) and loader helpers so any `Strategy` plugin (e.g. the public `strategy-vwap-momentum`) can be validated under identical state-machine semantics as live.

**本專案為作者個人研究與學習用途而公開，部分程式與文件在開發過程中借助 AI 協作撰寫與整理。**

本 repo 僅提供期貨回測 replay 框架的技術實作參考，**不構成**投資建議、交易邀約或獲利保證，作者亦無意提供商業級交易服務。

若你將本專案用於模擬交易以外的**實盤操作**（或依賴其結果做實盤決策），所有決策、參數設定、資金配置，以及因此產生的盈虧、漏單、斷線或其他損失，**均由使用者自行承擔**。作者與貢獻者不對任何直接或間接損害負責。

使用前請自行評估風險，並遵守當地法規與券商條款。

| 文件 | 用途 |
|------|------|
| [**SPEC.md**](SPEC.md) | **權威 spec**：定位、公開 API、確定性契約、tick cache、matching 模型、限制與驗證流程 |
| [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md) | v0.1.0 發布前檢查清單 |
| [CHANGELOG.md](CHANGELOG.md) | 版本變更紀錄 |
| [docs/releases/v0.1.0.md](docs/releases/v0.1.0.md) | v0.1.0 發布說明 |
| [trading-engine/docs/STRATEGY.md](https://github.com/timhwchuang/trading-engine/blob/main/docs/STRATEGY.md) | Strategy Protocol（plugin 注入方式） |
| [trading-engine/docs/DESIGN.md](https://github.com/timhwchuang/trading-engine/blob/main/docs/DESIGN.md) | Kernel invariants（與 live 相同） |

## Status

**0.1.0 研究用 alpha** — API 可能調整。適合驗證策略狀態機與確定性 regression；**不適合**直接作為 go-live 或廣義 UAT 的唯一依據。詳見 [SPEC.md §9](SPEC.md#9-backtest-fidelity--limitations)。

## ⚠️ Backtest Fidelity & Limitations

> **不要直接用回測 equity curve / Sharpe / 最大回撤做倉位或實盤決策。**

| 適合用途 | 不適合用途 |
|----------|------------|
| 驗證策略在與 live 相同 `TradingEngine` 下的狀態機、pending、force-flatten、risk gates | 以回測 PnL 直接做 position sizing 或 go-live 決策 |
| 確定性 regression、param sweep、audit log 比對 | 假設回測成交率 / 滑價等同 TAIFEX 實盤 |
| 合作者內部研究（理解限制的前提下） | 未經 paper trade + 真實 fill 比對就對外宣稱績效 |

**Execution realism 嚴重不足**（詳見 [SPEC.md §8–9](SPEC.md)）：

- Fill 模型：latency 後**下一根 tick 的 close** + 固定點數 slippage（0.5 / 2.5 / 8.0），**無** order book、queue、partial fill。
- Slippage 參數為作者 heuristics，**未**內建真實成交紀錄校正流程。
- **無** commission / fee / tax；expectancy 計算須在外部補上。
- Tick cache 品質（時間戳、換月、壞 tick）完全由 caller 負責；缺檔只 warning 略過，長 sweep 可能靜默少日期。
- **無內建** backtest vs paper fill 統計比對工具。

**建議驗證流程**：單元測試 → 確定性重跑 → paper trade → 比對 fill 統計 → 保守調高 slippage → 再考慮 live。完整說明見 [SPEC.md §9](SPEC.md#9-backtest-fidelity--limitations)。

## Install（GitHub only，不上 PyPI）

```bash
# 鎖定 tag（建議）
pip install "trading-backtest @ git+https://github.com/timhwchuang/trading-backtest.git@v0.1.0"

# 搭配 trading-engine（通常一起鎖）
pip install "trading-engine @ git+https://github.com/timhwchuang/trading-engine.git@v0.2.2"
```

在你的 app / research script 的 `pyproject.toml`：

```toml
dependencies = [
  "trading-engine @ git+https://github.com/timhwchuang/trading-engine.git@v0.2.2",
  "trading-backtest @ git+https://github.com/timhwchuang/trading-backtest.git@v0.1.0",
]
```

### 本地開發（workspace 或單獨 clone）

```bash
git clone https://github.com/timhwchuang/trading-backtest.git
cd trading-backtest
pip install -e ".[dev]"          # 含 ruff / mypy
# 同時需要 trading-engine（可 sibling pip -e ../trading-engine 或上面 git 安裝）
```

## Usage

### 直接使用 BacktestEngine（推薦給獨立研究 / 策略驗證）

```python
from trading_engine.testing.defaults import default_runtime_config
from trading_backtest import BacktestEngine
from strategy_vwap_momentum import VWAPMomentumStrategy, StrategyParams  # 任何公開 strategy plugin

cfg = default_runtime_config()
strategy = VWAPMomentumStrategy(params=StrategyParams.from_runtime_config(cfg))

engine = BacktestEngine(
    code="TXFR1",
    dates=[datetime.date(2026, 6, 10)],  # 你的回測日期（交易日由 caller 提供）
    strategy=strategy,
    runtime_config=cfg,
    # cache_dir=Path("tick_cache"),  # 預設 cwd/tick_cache
    # ports=...  # 可注入 telemetry / trend_refresh 等（預設 Null）
)
engine.run()

# 觀察結果：engine.host 就是完整的 TradingEngine（get_state_snapshot、audit logs 等）
snap = engine.host.get_state_snapshot()
print("final position:", snap.position_qty)
```

### Tick cache

將 tick CSV 放在 `tick_cache/{code}_{YYYY-MM-DD}.csv`（或 `.csv.gz`）。欄位與產生方式見 [SPEC.md §7](SPEC.md#7-tick-cache-format)。本 repo **不提供** 下載器；資料品質由你負責。

產生測試用模板：

```bash
python examples/tick_cache_template.py --code TXFR1 --date 2026-06-12
```

### Fill 比對（backtest vs paper/live）

```bash
python examples/compare_fill_audits.py backtest.log paper.log
```

或以 API 使用 `trading_backtest.validation.compare_fill_audits`。見 [SPEC.md §9](SPEC.md#9-backtest-fidelity--limitations)。

### 低階使用（進階）

- `from trading_backtest import MockBroker, VirtualClock`
- `from trading_backtest.loader import iter_replay_ticks, ReplayTick, iter_kbars_in_range`

MockBroker 可單獨用來測試 matching 邏輯（IOC、slippage、latency、blowout、session flatten slip、spread calibration）。

## Key Guarantees（確定性契約）

見 [SPEC.md §5–6](SPEC.md#5-architecture--replay-loop)。

- **同一 `TradingEngine`**：live 與 backtest 行為完全一致（pending、force-flatten、sync、risk gates）。
- **確定性**：單執行緒、sync order mode、VirtualClock 注入、不用 `time.time()`、no future data in kbars。
- **相同輸入 → byte-identical audit log**（SIGNAL_AUDIT / FILL_AUDIT / DAILY_SUMMARY）。
- MockBroker 實作 BrokerPort duck type，支援 `process_matching_queue` + kbars（no lookahead）。

**絕不**在 backtest 內 hard-code 任何策略（`strategy=` 必填，由 caller / plugin loader 提供）。

## Testing

```bash
python run_tests.py
```

目前 26 個測試（MockBroker、BacktestEngine、loader 驗證、validation / fill 比對）。CI 會在安裝 trading-engine 後執行。

## Architecture

```
trading-backtest/
├── engine.py          # BacktestEngine（組裝 TradingEngine + MockBroker + replay）
├── mock_broker.py     # IOC matching + slippage/latency 啟發式（無 shioaji）
├── loader.py          # tick / kbar 載入 + cache（gz/plain）、iter_replay_ticks
├── VirtualClock       # 可注入時鐘
└── __init__.py
```

Replay loop 保證：clock.set → broker.process_matching → host._check_pending_timeout → (in session) pre_atr + host.on_tick → daily summary。

完整 in/out scope、matching 假設、non-goals 見 [SPEC.md](SPEC.md)。

## License

MIT — see [LICENSE](LICENSE).

---

**再次提醒**：這是研究參考實作。Backtest 結果僅供驗證策略在與 live 相同狀態機下的行為。請在 simulation / paper 階段充分驗證，並嚴格遵守 trading-engine 的安全守則與 UAT 流程。作者不承擔任何交易損失責任。