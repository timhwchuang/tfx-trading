# trading-backtest — Authoritative Spec

> **Package**: `trading-backtest` · **Import**: `trading_backtest` · **Version**: 0.1.0  
> **Depends on**: `trading-engine>=0.2.2,<1.0` (same major alignment)

This document is the **single source of truth** for this standalone repo. All README, release notes, and packaging metadata should point here — not to paths that existed only in the old monorepo layout.

---

## 1. Purpose & positioning

`trading-backtest` implements the **Backtest** role in a three-repo ecosystem:

| Role | Repo | Import |
|------|------|--------|
| Trading (kernel) | `trading-engine` | `trading_engine` |
| Backtest (replay driver) | `trading-backtest` (this repo) | `trading_backtest` |
| Strategy (plugin) | `strategy-<name>` e.g. `strategy-vwap-momentum` | `strategy_<name>` |

**Iron law**: Backtest drives the **exact same `TradingEngine`** used for live trading. It does not duplicate, simplify, or fork the state machine.

### Intended audience (v0.1.0)

| Use case | Suitable? |
|----------|-----------|
| Verify strategy state machine, pending timeout, force-flatten, risk gates under the same kernel as live | **Yes** |
| Determinism regression, param sweep, audit-log byte comparison | **Yes** |
| Research / alpha exploration among collaborators who understand limitations | **Yes** (with caveats) |
| Position sizing, go-live decisions based on equity curve / Sharpe / max drawdown alone | **No** |
| Broad external UAT without paper-trade fill validation | **No** |

Optional integrator apps (e.g. `trading-app`) may wrap this package with ports, storage, and sweep tooling. That integration lives outside this repo.

**Implementation detail**: [docs/BACKTEST_IMPLEMENTATION.md](docs/BACKTEST_IMPLEMENTATION.md)

---

## 2. In scope

- **BacktestEngine**: assemble `TradingEngine` + `MockBroker` + `VirtualClock` + tick replay loop.
- **MockBroker**: heuristic IOC limit-order matching (latency gate, slippage tiers, no-lookahead kbars).
- **loader**: tick / kbar cache I/O (`.csv` / `.csv.gz`), `iter_replay_ticks`, basic data sanity checks.
- **VirtualClock**: injectable clock; no `time.time()` in the replay path.
- **Determinism contract**: single-threaded, sync order mode, byte-identical audit logs for identical inputs.

## 3. Out of scope (non-goals)

- Tick data acquisition, cleaning, rollover, or overnight-gap handling (caller responsibility).
- Full execution realism: order book depth, queue position, partial fills, commission/fee/tax models.
- Strategy logic (injected via `strategy=`; never hard-coded here).
- Performance analytics harness (Sharpe, drawdown reports) — belongs in app / research layer.
- PyPI publishing (install via Git tag only for now).
- Live broker adapters (see `trading-engine`).

---

## 4. Public API

### Package exports (`trading_backtest`)

```python
from trading_backtest import (
    BacktestEngine,
    VirtualClock,
    MockBroker,
    ReplayTick,
    iter_replay_ticks,
    DEFAULT_CACHE_DIR,
    compare_fill_audits,
    capture_backtest_audits,
    hash_audit_records,
    __version__,
)
```

### BacktestEngine

```python
BacktestEngine(
    code: str,                          # contract code, e.g. "TXFR1"
    dates: list[datetime.date],         # replay calendar days (caller supplies trading days)
    strategy: Strategy,                 # required — any trading_engine Strategy plugin
    *,
    runtime_config: RuntimeConfig,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    broker: MockBroker | None = None,
    clock: VirtualClock | None = None,
    telemetry / trend_refresh / alerts / archive / order_adapter  # optional port injection
)
```

- `run()` — replay all ticks for `dates`, then emit daily summary on last tick.
- `host` — the live `TradingEngine` instance (inspect `get_state_snapshot()`, audit logs, etc.).

### Loader helpers (`trading_backtest.loader`)

| Symbol | Purpose |
|--------|---------|
| `ReplayTick` | One replay unit (datetime, close, volume, tick_type, bid/ask) |
| `iter_replay_ticks(code, dates, *, cache_dir)` | Yield ticks across dates; warns and skips missing cache files |
| `load_ticks_csv(path)` | Load one day; validates and sorts ticks |
| `KBarRecord`, `iter_kbars_in_range`, `save_kbars_csv`, `load_kbars_csv` | 1-min bar cache for ATR / indicators |
| `resolve_tick_cache_path`, `cache_path`, `cache_gz_path` | Cache path resolution (.gz preferred) |
| `date_range(start, end)` | Inclusive calendar range (no holiday filter) |

### MockBroker (advanced / unit tests)

Construct with optional overrides: `latency_ms`, `NORMAL_SLIP`, `BLOWOUT_VOL`, `BLOWOUT_SLIP`, `FLATTEN_SLIP`, `session_force_flatten_time`, `spread_calibration`.

Implements BrokerPort duck type: `place_order`, `kbars`, `process_matching_queue`, plus no-op live-only methods.

---

## 5. Architecture & replay loop

```
BacktestEngine
├── VirtualClock          # injectable time
├── MockBroker              # api stand-in + IOC matching
├── MockOrderAdapter        # from trading-engine
└── TradingEngine (host)    # SAME class as live — strategy, pending, session, risk gates
```

Per-tick order (enforced by tests):

1. `clock.set(tick.datetime.timestamp())`
2. `broker.current_dt = tick.datetime`
3. `broker.process_matching_queue(tick, host)` — fills / cancels inflight orders
4. `host._check_pending_timeout()`
5. If inside trading session: pre-tick ATR refresh + `host.on_tick(tick)`
6. After last tick: `host._emit_daily_summary(...)`

**Premarket**: `on_tick` is filtered by session; matching still runs (orders can fill before session open).

### Private coupling (known fragility)

To reuse the live kernel without a fork, `BacktestEngine` currently sets:

- `host._order_sync_mode = True`
- `host._maybe_refresh_atr = noop` (ATR refreshed explicitly pre-tick in replay)
- Calls `host._check_pending_timeout()` and `host._emit_daily_summary()` directly

These depend on `trading-engine` internals. A future `trading-engine` release should expose an official backtest-mode hook to replace monkey-patching.

---

## 6. Determinism contract

Given identical:

- `code`, `dates`, `cache_dir` tick files
- `strategy` implementation and params
- `runtime_config`
- `MockBroker` parameters

Then:

- Replay is **single-threaded**; no background threads.
- Orders are processed **synchronously** via `_order_sync_mode`.
- `VirtualClock` is the sole time source.
- `MockBroker.kbars()` excludes bars with `ts > current_dt` or incomplete 1-min bar (`ts + 1min > current`).
- Audit logs (`SIGNAL_AUDIT`, `FILL_AUDIT`, `DAILY_SUMMARY`) are **byte-identical** across runs.

Verify with repeated runs or diff against a golden log file in your research pipeline.

---

## 7. Tick cache format

### Directory layout

Default: `./tick_cache/` (override with `cache_dir=`).

| File pattern | Content |
|--------------|---------|
| `{code}_{YYYY-MM-DD}.csv` or `.csv.gz` | Tick replay data |
| `{code}_kbars_{YYYY-MM-DD}.csv` | 1-minute OHLCV bars |

`.gz` is preferred when both exist.

### Tick CSV columns (required)

| Column | Type | Notes |
|--------|------|-------|
| `datetime` | ISO 8601 | Exchange-local or TZ-aware; monotonic per file expected |
| `close` | float | Last price; normalized at load time |
| `volume` | int | Tick volume |
| `bid_price` | float | For optional spread calibration |
| `ask_price` | float | For optional spread calibration |
| `tick_type` | int | Passed through to engine |

### Producing tick cache

This package does **not** ship a data downloader. Typical workflow:

1. Record or export ticks from your broker / data vendor / internal capture pipeline.
2. Normalize to the column schema above (one file per contract per session day).
3. Optionally pre-compute `{code}_kbars_{date}.csv` for ATR (or let your pipeline generate them).
4. Place files under `tick_cache/` (or custom `cache_dir`).

**Quality is the dominant factor**: timestamp accuracy, bad-tick filtering, contract rollover, and overnight gaps are entirely the caller's responsibility. Missing cache files log a warning and are **silently skipped** — long sweeps can lose days without failing.

### Loader validation (v0.1.0+)

`load_ticks_csv` warns (does not abort) on:

- Non-monotonic timestamps (ticks are sorted before return)
- Duplicate timestamps
- Non-positive prices
- Large single-tick price jumps (default: >5% from previous tick)

Treat warnings as data-quality signals; fix upstream rather than ignoring them in production sweeps.

---

## 8. MockBroker matching model

This is a **heuristic replay**, not a market simulator.

### Algorithm (IOC limit orders)

1. `place_order` appends to `inflight` with `arrive_after = clock() + latency_ms`.
2. On each tick, orders with `tick_ts >= arrive_after` are eligible.
3. Use that tick's **close** price for fill decision:
   - **Buy**: fill if `close <= limit`; fill price = `min(limit, close + slippage)`
   - **Sell**: fill if `close >= limit`; fill price = `max(limit, close - slippage)`
4. If not fillable → immediate cancel (IOC semantics).
5. Full quantity fill only (no partial fills).

### Slippage tiers (defaults)

| Condition | Slippage (points) |
|-----------|-------------------|
| Normal | `NORMAL_SLIP` = 0.5 |
| `tick.volume > BLOWOUT_VOL` | `BLOWOUT_SLIP` = 2.5 |
| Exit intent at/after `session_force_flatten_time` | `FLATTEN_SLIP` = 8.0 |
| `spread_calibration=True` | `max(tier_slip, (ask-bid)/2)` when bid/ask valid |

Defaults are **author-tuned heuristics**, not calibrated from live fill statistics. Do not treat them as TAIFEX ground truth.

### Known limitations

| Gap | Impact |
|-----|--------|
| Next-tick close fill model | Backtest may fill easily; live may slip heavily or not fill at all |
| No order book / queue / partial fill | Overstates fill rate in thin or fast markets |
| Fixed-point slippage | Does not model slippage distribution or latency jitter |
| No commission / tax / fees | PnL and expectancy calculations must add costs elsewhere |
| kbars 1-min granularity | ATR timing must be validated against your live bar source |

---

## 9. Backtest fidelity & limitations

> **Read this before trusting any PnL number.**

### What transfers well to live

- Strategy decision logic and state transitions (same `TradingEngine` + same strategy plugin).
- Pending order timeout, force-flatten timing, session rules, risk gates.
- Deterministic regression when inputs are fixed.

### What does **not** transfer directly

- **Execution realism** is severely limited. TAIFEX microstructure (especially during blowouts or illiquid periods) is not modeled.
- **Slippage parameters** are not validated against your broker's fill history.
- **Tick cache quality** drives ~80% of backtest believability; this repo does not validate your data.
- **Fill comparison is basic** — `compare_fill_audits` reports aggregate stats; you still need paper/live logs and manual recalibration.

### Calculating realistic expectancy

`trading-backtest` does **not** model transaction costs. `FILL_AUDIT.pnl_points` (when present) reflects **gross** price difference only. Before using backtest output for sizing or go-live decisions, apply costs **outside** this package:

| Cost component | Typical source | Notes |
|----------------|----------------|-------|
| Broker commission | Your broker fee schedule | Per-side or round-turn; varies by VIP tier |
| Futures transaction tax (TW) | TAIFEX / regulations | Often on sell side for index futures |
| Slippage beyond MockBroker | Paper/live `FILL_AUDIT` | Backtest slip is heuristic; add conservative buffer |
| Opportunity cost of unfilled IOC | Paper cancel rate | Backtest may overstate fill rate |

**Minimal workflow:**

1. Parse `FILL_AUDIT` from backtest logs (`parse_fill_audits`) or use your app's reporting layer.
2. Subtract per-trade costs: `net_pnl = gross_pnl - commission - tax - extra_slippage_buffer`.
3. Compare **net** expectancy against paper trade over the same calendar window — not just backtest gross PnL.
4. If paper median slippage exceeds backtest, raise `MockBroker` slip params before re-running sweeps.

Round-turn example (illustrative — use your broker's actual rates):

```python
COMMISSION_PER_SIDE = 20  # TWD, example
TAX_RATE_SELL = 0.00002   # example; verify current regulation

def net_exit_pnl(gross_pts: float, *, is_sell: bool, extra_slip_pts: float = 1.0) -> float:
    """Convert gross points to net after illustrative costs (points space)."""
    return gross_pts - extra_slip_pts - (COMMISSION_PER_SIDE * 2 / POINT_VALUE_TWD)
```

`POINT_VALUE_TWD` depends on contract (e.g. TXF ≈ 200 TWD/point). Keep cost logic in your research / app layer (`theman` reporting, notebooks, etc.) — not in `trading-backtest`.

### Recommended validation pipeline

1. **Unit / contract tests** — strategy plugin + `trading-backtest` tests (this repo).
2. **Determinism check** — `hash_audit_records(capture_backtest_audits(engine))` identical across runs; or diff audit log files.
3. **Paper trade** — same `TradingEngine` + live adapter in simulation mode.
4. **Fill statistics** — compare paper/live `FILL_AUDIT` vs backtest using `compare_fill_audits` or `examples/compare_fill_audits.py`; recalibrate `MockBroker` params conservatively.
5. **Go-live** — only after steps 3–4 with conservative slippage assumptions; follow `trading-engine` UAT checklist.

Without steps 3–4, treat backtest equity curves as **ordinal** (strategy A vs B under same heuristic), not **cardinal** (expected live PnL).

### Validation helpers (`trading_backtest.validation`)

| Symbol | Purpose |
|--------|---------|
| `parse_fill_audits` / `parse_fill_audits_from_file` | Extract `FILL_AUDIT` JSON from log text or files |
| `compare_fill_audits` | Aggregate comparison (fill count, median slippage vs limit/signal) |
| `format_fill_comparison` | Human-readable report |
| `capture_backtest_audits(engine)` | Run replay and capture audit lines in-process |
| `hash_audit_records` | SHA-256 over canonical `SIGNAL_AUDIT` / `FILL_AUDIT` / `DAILY_SUMMARY` JSON |

CLI: `python examples/compare_fill_audits.py backtest.log paper.log` (exit 1 if warnings).

---

## 10. Testing

```bash
python run_tests.py
```

Coverage focus:

- MockBroker: latency gate, blowout slip, flatten slip, fill ≤ limit, spread calibration, no-lookahead kbars.
- BacktestEngine: clock advance, pending timeout ordering, premarket `on_tick` filter vs matching, empty run.
- Loader: sort / duplicate / price anomaly warnings.

CI installs pinned `trading-engine@v0.2.2`, runs ruff + tests (mypy non-blocking).

---

## 11. Versioning

- SemVer for this package; `0.x` = API may evolve.
- Major version tracks `trading-engine` major (0.1.x ↔ trading-engine 0.2.x).
- Pin both tags in production:

```toml
dependencies = [
  "trading-engine @ git+https://github.com/timhwchuang/trading-engine.git@v0.2.2",
  "trading-backtest @ git+https://github.com/timhwchuang/trading-backtest.git@v0.1.0",
]
```

---

## 12. Related documentation

| Document | Location |
|----------|----------|
| Strategy Protocol | `trading-engine/docs/STRATEGY.md` |
| Kernel design / invariants | `trading-engine/docs/DESIGN.md` |
| Live safety & UAT | `trading-engine/docs/UAT_CHECKLIST.md`, `trading-engine/docs/LIVE_SAFETY.md` |
| Usage quickstart | this repo `README.md` |
| Example smoke script | `examples/minimal_backtest_smoke.py` |

---

## Disclaimer

This package is published for **personal research and learning**. It does **not** constitute investment advice. Users bear all risk for live trading decisions. See `README.md` for the full disclaimer (中英).