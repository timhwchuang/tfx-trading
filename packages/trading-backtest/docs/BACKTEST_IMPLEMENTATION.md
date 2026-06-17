# Backtest Implementation Spec

> **Owner**: `trading-backtest`  
> **Companion**: [SPEC.md](../SPEC.md) (package API), [trading-engine BACKTEST_HOST_CONTRACT](https://github.com/timhwchuang/trading-engine/blob/main/docs/BACKTEST_HOST_CONTRACT.md)

Executable spec for replay loop, MockBroker, and acceptance tests. Phase 2–3 + backtest-side Phase 6/7 revisions from the former monolith `BackTestingSpec.md`.

---

## Phase 2 — BacktestEngine + VirtualClock

### VirtualClock

Injectable `__call__() -> float` epoch seconds; no wall clock.

### Main loop (per tick)

```
1. clock.set(tick.datetime.timestamp())
2. broker.current_dt = tick.datetime
3. broker.process_matching_queue(tick, host)   # BEFORE timeout
4. host._check_pending_timeout()
5. if is_trading_session(tick.datetime):
       pre_tick_refresh_atr(host, ts)        # sync, outside lock
       host.on_tick(tick)
6. after last tick: host._emit_daily_summary(last_date)
```

**Semantics**

- Matching before timeout avoids losing fills on long tick gaps (Phase 7.2).
- Premarket: skip `on_tick` only; still match + timeout (Phase 7.3).
- Missing cache files: loader warns and skips; engine continues.

### Acceptance (`tests/test_backtester.py`)

| Test | Expectation |
|------|-------------|
| `test_engine_runs_empty` | No exception on empty/missing cache |
| `test_clock_advances` | `clock()` equals last tick timestamp |
| `test_pending_timeout_before_tick_processing` | `is_pending` False before `on_tick` after gap |
| `test_premarket_ticks_are_filtered` | Pre-08:45 no `on_tick` |
| `test_premarket_tick_still_runs_matching` | Premarket still matches inflight |

---

## Phase 3 — MockBroker

### Required `api` surface

| Member | Behavior |
|--------|----------|
| `futopt_account` | `None` |
| `place_order` | Push inflight; return `.order.id` |
| `kbars` | No-lookahead filtered bars |
| `update_status` / `order_deal_records` | no-op / `[]` |
| `usage()` | no-op constants (7.4) |
| `resolve_contract(code)` | object with `.code` |

### Matching (IOC, close-based)

1. Latency gate: `tick_ts >= arrive_after`
2. Slippage: `NORMAL_SLIP` / `BLOWOUT_SLIP` / `FLATTEN_SLIP`
3. **Limit clamp (6.1)**:
   - Buy: `close <= limit` → `fill = min(limit, close + slip)`
   - Sell: `close >= limit` → `fill = max(limit, close - slip)`
4. No fill → `FuturesOrder` Cancel; fill → `FuturesDeal`
5. `tick.close` coerced with `float()` (v0.1.1 — CSV str replay)

### kbars no-lookahead

- `bar_ts <= current_dt`
- `bar_ts + 1min <= current_dt` (closed bar only, 7.9)
- Empty kbars → ATR 0 → strategy safe no-entry

### Defaults

`latency_ms=15`, `NORMAL_SLIP=0.5`, `BLOWOUT_VOL`, `BLOWOUT_SLIP=2.5`, `FLATTEN_SLIP=8.0`

### Acceptance (`tests/test_mock_broker.py`)

Includes: normal slip, cancel above limit, sell fill, blowout, latency gate, no-lookahead kbars, limit clamp, first-tick ATR, spread calibration optional, **string close CSV replay**.

---

## Phase 6/7 backtest revisions (implemented)

| ID | Summary |
|----|---------|
| 6.1 | Limit clamp — never worse than limit |
| 6.3 | Timeout after matching, before `on_tick` |
| 6.4 | Session filter at feed layer (not engine) |
| 6.5 | Prior-day kbars for 08:45 ATR warmup |
| 6.7 | Optional bid/ask spread calibration (default off) |
| 7.1 | Sync ATR; noop `_maybe_refresh_atr` |
| 7.2 | Match before timeout |
| 7.3 | Premarket match-only |
| 7.4 | `usage()` no-op |
| 7.9 | Closed 1-min bar filter |
| 7.10 | Premarket matching regression |

---

## File map

| Component | Path |
|-----------|------|
| BacktestEngine | `src/trading_backtest/engine.py` |
| MockBroker | `src/trading_backtest/mock_broker.py` |
| VirtualClock | `src/trading_backtest/clock.py` |
| Loader | `src/trading_backtest/loader.py` |
| Tests | `tests/test_backtester.py`, `tests/test_mock_broker.py` |

---

## Implementation order (new contributors)

1. MockBroker + tests
2. BacktestEngine loop + tests
3. Tick/kbar cache smoke
4. Wire strategy plugin from caller

Run `python run_tests.py` after each step (**27** tests baseline).