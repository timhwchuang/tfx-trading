# Changelog — tfx-trading monorepo

All notable changes are documented here by package.  
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).  
Per-package `version` in `pyproject.toml` follows [SemVer](https://semver.org/) (0.x = API may still evolve).

Historical standalone-repo release links are kept for archaeology only; development continues in this monorepo.

---

## Docs

### [Unreleased]

#### Changed

- **tick_cache SSOT (breaking)**：`kbar_cache/` 目錄與 `--kbar-cache-dir` / `--mirror-kbars` CLI 已移除；tick 與 kbar 皆寫入/讀取 `tick_cache/`（`{code}_kbars_{date}.csv`）。路徑 API 更名：`kbar_path` / `kbar_gz_path` / `resolve_kbar_path` / `kbars_satisfy_request`（取代 `kbars_cache_*` / `kbar_cache_satisfies_request`）。舊目錄遷移：`scripts/linux/migrate-legacy-kbar-cache.sh`；`structure_calibration` / `param_sweep` 讀 kbar 前自動遷移（`ensure_legacy_kbars_migrated`）。

#### Added

- **FT-003**：SHARED_ASSUMPTIONS **v1.1** — TMFR1 摩擦 **5 點/趟**（手續費 30 + 稅 20 NTD）上線；`friction.enabled: true`（主 config + 各 workspace）
- **GCE Live 運維 SSOT**：[`docs/ops/LinuxOps.md`](docs/ops/LinuxOps.md) §GCE（目錄、cron 13:50 stop → 13:54 post-session、sync）；[`HYBRID_DEPLOY.md`](docs/ops/HYBRID_DEPLOY.md) 已部署摘要；[`TODO.md`](docs/TODO.md) §GCP 營運（2026-07-23 帳單）。
- **FT-002 Phase 4**：`regime_allows_entry` 接線；`structure_veto` / armed structure enrichment DECISION_AUDIT；`structure_stale` → `risk_blocked` audit；`record_structure_veto`；filter-on 3-run determinism；[`TODO.md`](docs/TODO.md) / [`WeeklyStatus.md`](docs/WeeklyStatus.md) / [`uat/APP.md`](docs/uat/APP.md) 同步 P6-SMC-CAL 指引。
- **FT-002 Phase 3 + sweep（A1–A8）**：`StructureRefreshPort` / `structure_stale` / `refresh_atr` 掛載；`structure_refresh.py`；config + runtime 互斥；`structure_calibration_cli --sweep`；`param_sweep` structure grid；`test_structure_stale_guards`。
- **FT-002 Phase 2** P6-SMC-CAL offline harness: `structure_calibration.py` + `structure_calibration_cli.py` —三組 counterfactual（no_filter / structure_only / trend_only）、friction-adjusted expectancy、`structure_events.csv` + `structure_armed_join.csv`、30s armed conversion；A/B-class tests + kbar fixture。
- **FT-002** SMC structure filter: SPEC v2 + PLAN Phase 1 complete + `REVIEW.md` Phase 1 re-review（PASS）；[`docs/TODO.md`](docs/TODO.md) §P6-SMC-CAL

---

## trading-engine

### [Unreleased]

#### Changed

- **FT-003 sweep overlay keys**: `SWEEP_FIELD_TO_CONST` 補齊（含 `min_atr_threshold`、`ioc_slippage_points`、`pending_timeout_sec`、`momentum_vol_1s` 等）；`RuntimeConfig.__getattr__` overlay-aware；`apply_overlay` 對未知 key `raise ValueError`（杜絕靜默失效）。

#### Added

- **Shioaji Time Contract** ([`SPEC.md`](packages/trading-engine/SPEC.md)): documents historical `ts` decode (equivalent to official polars cast), live `TickFOPv1.datetime`, and anti-patterns. Code SSOT: `trading_engine.calendar.shioaji_ts.shioaji_historical_ts_from_ns`. Legacy cache policy: read paths do no time correction; pre-2026-06-26 +8h files are deleted and re-fetched.
- **Layer 2 IOC terminal query (`order_status_query_enabled`, default OFF)**: `update_status(trade)` on the order worker; `QueryStatusTask`; place-time refresh; flag-only gating; graceful fallback. Signal taxonomy fix: during HALT, L3 inference (unchanged broker read) does not clear exit pending; L1 callback / L2 authoritative terminal (`cancelled`/`failed`/`inactive`) clears and allows convergence retry. `_check_pending_timeout` when flag ON: L3 snapshot → `order_deal_records` → L2 enqueue. Tests: `test_order_status_query.py` (26 cases).
- **P0-5 truth-driven execution — >1-lot accumulation RCA (2026-06-26)**: After repeated `Pending 超時` the kernel treated UNKNOWN order outcomes as FAILED, cleared pending, and let the strategy re-issue exits while delayed/orphan fills landed — accumulating a 2-lot short under a 1-lot strategy. Reworked the state machine so the **broker `list_positions` is the single source of truth**:
  - **Timeout = UNKNOWN, not FAILED**: `_check_pending_timeout` no longer clears pending + re-arms. It keeps `pending_order_id` (so a late fill still attributes), enters `_settling`, and converges against the broker via the new `_settle_via_reconcile` (fast poll + `reconcile_confirm_reads` debounce). Unresolved past `settle_timeout_sec` → `_position_unconfirmed` (HALT) + `block_new_entry` + CRITICAL.
  - **Freeze on uncertainty**: `_validate_order_signal` and the strategy (`evaluate`) now reject **both entry and exit** while `_settling` / `_position_unconfirmed` (previously only entry was gated). A `_kernel_converging` flag lets the kernel's own flatten bypass the freeze.
  - **Kernel convergence flatten**: while HALT and not flat, `_maybe_converge_flatten` sends exactly ONE exit sized to the held qty (throttled by `reconcile_fast_sec`), then returns to `_settling`; HALT lifts once confirmed flat (entries stay blocked until daily reset).
  - **Orphan / mismatched fills → HALT**: `_handle_futures_deal` now sets `_position_unconfirmed` (full freeze), not just `block_new_entry`.
  - **Ceiling hard backstop**: reconcile/settle finding `broker_qty > max_position_qty` AND `> kernel_qty` → HALT + converge flatten.
  - **Fast reconcile cadence**: `_check_position_reconcile` polls at `reconcile_fast_sec` while unconfirmed (no longer permanently skipped just because something is pending — the original "busy → never reconciled" gap).
  - New `RiskGate` / `EngineStateSnapshot` fields `settling` / `position_unconfirmed`. New settings `settle_timeout_sec` (30) / `reconcile_fast_sec` (2) / `reconcile_confirm_reads` (2); `pending_timeout_sec` semantics redefined to "callback wait → switch to active reconcile". `MockBroker` gained net-position tracking + `list_positions()`; the backtest replay loop drives the settle/converge/reconcile steps deterministically. Tests: `test_truth_driven_execution.py` + updated timeout regressions.
- **P0-5 hardening — live net position must never exceed `max_position_qty` (=1) — 2026-06-26**: A second incident (10:39) showed a momentary 2-lot short even with truth-driven execution. RCA: the broker reported an entry fill **~18s late**; `list_positions` read flat inside that report-latency window, so the kernel concluded "entry 未成交 → 清 pending", **exited SETTLING and unfroze the strategy**, which re-armed a second entry — then both filled. Fixes:
  - **Entry never clears on a flat snapshot (D1)**: `_apply_pending_broker_truth` entry branch removed the clear-on-flat no-fill path; an entry resolves **only** on a positive fill, otherwise it keeps settling. Any entry uncertainty routes to HALT with sticky `block_new_entry` (**never re-arm**) — a flat read during report latency is not proof of non-fill.
  - **Strict single-flight for all kernel orders (D2)**: `_halt_position_unconfirmed` gained `clear_pending` (default `False`) and is idempotent — it drops a live order's `order_id` only when the caller knows it is terminal (entry IOC confirmed missed). A possibly-live exit/flatten is kept (no clear, no sync), so convergence can never double-send a flatten.
  - **Convergence sizes to fresh debounced broker truth (D3)**: `_maybe_converge_flatten` re-reads + debounces `list_positions` and sizes the single flatten to the confirmed broker qty (not the possibly-stale kernel belief), keeping its `is_pending`/`_settling` single-flight guard.
  - **Conservative timeouts (D4)**: defaults bumped so the common late fill is adopted and only true misses HALT — `pending_timeout_sec` 8→15, `settle_timeout_sec` 30→45, `reconcile_confirm_reads` 2→3 (across `settings.py` / `testing/defaults.py` / app `config.py` / `config.yaml`). Correctness does not depend on the exact values (uncertainty → HALT, never re-arm).
  - **Accepted tradeoff**: a genuinely-missed IOC entry now HALTs and stops new entries for the day (no auto-retry); a future broker order-status-by-id query would distinguish Filled vs Cancelled and resume after a confirmed cancel.
  - `MockBroker` gained configurable `position_report_delay_sec` / `deal_report_delay_sec` to reproduce the stale-flat read deterministically. Tests: incident replay + convergence single-flight + entry-no-clear in `test_truth_driven_execution.py`, mock-broker latency in `test_mock_broker.py`; entry-flat regressions updated to HALT-no-rearm.
- **P0-5 extension — emergency market orders + faster unknown window + residual-hole hardening — 2026-06-26**: A 30-lot UAT log revealed the broker can report fills/positions **minutes** late (≫ the 18s assumption), and that a hard stop falling into the unknown window bleeds with no fast way out. Three coordinated changes (all extend "never >1 lot"; the normal entry/profit path is unchanged):
  - **Emergency market orders (new `emergency_market_orders`, default True)**: a STOP-LOSS exit IOC (`stop_loss` / `stop_loss_vwap`) that comes back Cancelled with no fill no longer re-chases with a limit — the kernel arms exactly one guaranteed-fill **market** flatten (`_maybe_emergency_market_flatten`, single-flight, `_kernel_converging` bypass). The HALT **convergence flatten** is also sent as a market order. New `OrderSignal.market`; new adapter `place_market` (Shioaji `FuturesPriceType.MKP` IOC) on base/shioaji/mock; `MockBroker` fills market orders at `close ± slippage` with no limit gate. This decouples exit/stop time-to-flat from the unknown window (≈ tick-speed + one market order) at the cost of slippage.
  - **Faster unknown window**: `pending_timeout_sec` 15→1 and `reconcile_fast_sec` 2→1 (1s background polling) so active reconcile starts immediately. `settle_timeout_sec` stays 45 (an unconfirmed entry doesn't bleed — it waits and never re-arms). **Honest floor:** the real unknown window is bounded by the broker's own report latency (`list_positions`/deal callbacks lag too); tuning these cannot push it below broker latency — which is exactly why exits use market escalation rather than relying on the window.
  - **Residual-hole hardening (no infer-clear during HALT)**: `_apply_pending_broker_truth` no longer clears a live exit/flatten on an "unchanged & consistent" broker read while `_position_unconfirmed` — under multi-minute latency that read is just the not-yet-reflected pre-flatten position, and clearing it would let convergence send a second flatten. During HALT an exit resolves only on a real reduction or an explicit Cancelled callback.
  - Settings added across `settings.py` / `testing/defaults.py` / app `config.py` / `config.yaml` (`emergency_market_orders`). Tests: stop→market escalation, convergence-market (+ disabled variants), HALT no-consistent-clear, mock market fills.
- **P0-5 two-tier state machine — SETTLING (transient) vs HALT (anomaly) — 2026-06-26**: A stable long-running daemon must not sticky-HALT for the whole day on occasional callback silence / network jitter. IOC in live is exchange-native (ms terminal); sim report latency (seconds–minutes) is an artifact and must not define live behavior.
  - **Entry miss → clean resume**: after stable readable-flat for `entry_miss_confirm_sec` (default 5) + debounce, `_resolve_entry_missed` clears pending, logs WARNING, resumes normal entries — **no sticky `block_new_entry`**. Explicit `Cancelled` callback path unchanged (immediate resume).
  - **HALT reserved for anomalies only**: ceiling breach, orphan/mismatched fill, broker unreadable past `settle_timeout_sec`, entry debounce never stabilizes (45s), or `max_consecutive_missed_entries` circuit breaker (default 3).
  - **Safety does not depend on the miss window**: freeze while unsettled + ceiling check + market convergence backstop still guarantee ≤1 lot; sim may show caught transient orphan→flatten (expected under UAT==live).
  - **`CALLBACK_LATENCY` instrumentation**: logs `exchange_ts` vs local receive delta at order/deal callbacks for UAT calibration.
  - New settings: `entry_miss_confirm_sec`, `max_consecutive_missed_entries`. Tests: `TestEntryMissResume` + updated incident replay (miss→orphan→converge).

#### Removed

- **`calendar.legacy_tick_cache` (entire module) + read-time +8h normalization**: removed `legacy_tick_cache.py` and all `normalize_legacy_plus8h*` / `is_legacy_plus8h_tick_candidate` / `existing_ticks_for_backfill_merge` / `cache_likely_legacy_plus8h_day_session` helpers and their `calendar` exports. Tick read paths (`tick_loader`, `trading_backtest.loader`) now read the CSV cache verbatim with zero transform. Policy: pre-2026-06-26 +8h files are deleted and re-fetched (`--overwrite`), never corrected on read — removes the recurring evening-shift ambiguity at its source.

#### Fixed

- **`calendar/taifex.select_recent_trading_days_closes`**: raw `api.kbars` ns now uses `shioaji_historical_ts_from_ns` (wall clock) instead of +8 decode — fixes live trend day slicing when `used_long_lookback=True`.
- **Position/broker sync hardening — 24-lot phantom short RCA (2026-06-25)**: Kernel position drifted from the broker after a reconnect/relogin, accumulating 24 untracked short lots overnight. Three-layer fix + a separate exit bug:
  - **P0-1 reconnect re-attaches the trade report channel**: `_on_reconnected` (and watchdog relogin, which routes through it) now calls a new broker-neutral `_resubscribe_trade` hook in addition to `_resubscribe_ticks`. `ShioajiLiveBootstrap.resubscribe_trade` re-runs `subscribe_trade` + `set_order_callback`. Failure degrades the session to unhealthy → relogin. Previously only quote ticks were restored, so fills arrived silently and every order timed out — the primary root cause.
  - **P0-2 orphan deals are no longer dropped**: `_handle_futures_deal` for a deal with no pending or a non-matching `order_id` now forces `sync_positions` + `block_new_entry` + a staged CRITICAL alert instead of silently returning.
  - **P1-1 exit fills flatten by actual qty + re-sync**: an exit fill reduces `position_qty` by the filled amount and only flips to Flat at zero; it then triggers a re-sync to confirm the broker is truly flat. The kernel sizes exits to the held `position_qty` (the strategy may still default to 1 lot). Previously an exit fill blanket-zeroed `position_qty`, orphaning residual lots.
  - **P1-2 simulation reconcile uses the broker snapshot**: `_reconcile_pending_trade` no longer pure-short-circuits in sim; it reconciles against `list_positions` and resolves cleanly when the broker reflects the fill, only falling through to the timeout path when the broker read fails.
  - `sync_positions` / `read_broker_position` materialize `list_positions` defensively so an unreadable broker is treated as a failed read rather than crashing the callback path.

#### Added

- **P0-3 periodic position reconcile + drift circuit-breaker**: `_check_position_reconcile` runs in `_timeout_loop` every `position_reconcile_sec` (default 60, `<=0` disables) during the trading session, skipped while pending. Broker/kernel qty/dir mismatch → adopt broker truth via `sync_positions` + `block_new_entry` + CRITICAL alert + `_position_drift_detected`. New `session.py:read_broker_position` helper.
- **P0-4 hard position ceiling**: `max_position_qty` config (default 1). `_validate_order_signal` rejects entries when `position_qty + signal.qty > max_position_qty`.
- **Config**: `operations.position_reconcile_sec` (60), `operations.max_position_qty` (1) wired through `config.yaml` → app `Settings` → engine `Settings`/`RuntimeConfig`/test defaults.
- **Tests**: `test_shioaji_live_wiring.py` (reconnect re-attach), `test_position_reconcile.py` (drift block/alert/throttle/skip-pending/disabled), orphan-deal-adopts + duplicate-deal-reconciles in `test_adversarial_callbacks.py`, max-qty rejects in `test_signal_validation.py`, partial-exit + exit-resync in `test_position_qty.py`, sim-resolve + broker-still-holds in `test_order_smoke.py`, and updated B4 / reconnect-race / pending-armed sim reconcile expectations.

#### Changed

- **`_resolve_contract`**: resolve rolling contracts via product category prefix (`TXF` / `MXF` / `TMF`) so `TMFR1` (微台) and `MXFR1` work without hardcoding大台 `TXF` only.
- **`setup_async_logging`**: optional `console_level` (use `"OFF"` to omit stdout sink); `flush_async_logging()` waits for the async queue to drain then flushes sinks.

#### Fixed

- **Zombie session after reconnect (SessionNotEstablished)**: `_on_reconnected` no longer sets `_api_connected=True` when subscribe fails or `refresh_atr()` hits a session-level error (`api_errors.is_api_session_error`). No-tick watchdog escalates to `_mark_disconnected()` after `no_tick_resubscribe_escalate_after` (default 3) failed resubscribes, delegating to session watchdog relogin. `run()` shutdown swallows dead-session `logout` errors. See [`docs/ops/LIVE_SAFETY.md`](../../docs/ops/LIVE_SAFETY.md).

- **Live order callbacks ignored (UAT pending timeout)**: Shioaji `OrderState.FuturesOrder` / `FuturesDeal` are str-like (`isinstance(stat, str)` is True) but not equal to `"FuturesOrder"` / `"FuturesDeal"`. `normalize_order_stat` now prefers `.name` before the `isinstance(str)` branch so `handle_order_event` routes live callbacks. Mock/backtest string stats unchanged. Symptom: `RAW_ORDER_EVT` in log but no `委託回報` / `FILL_AUDIT`, then `Pending 超時`. Documented in [`docs/ops/LIVE_SAFETY.md`](../../docs/ops/LIVE_SAFETY.md) and SPEC §4.2 Order/fill.

#### Added

- **`api_errors.is_api_session_error`**: Classify `SessionNotEstablished` / `NotReady` / `ShioajiConnectionError` without importing shioaji in core.
- **Config** `operations.no_tick_resubscribe_escalate_after` (default 3).
- **`DAILY_SUMMARY.operational.no_tick_escalations`**: Count of no-tick → session-relogin escalations.
- **Tests**: `test_api_errors.py`, `test_no_tick_escalation.py`, `test_graceful_logout.py`, B3 unhealthy reconnect regression.

- **Shioaji API thread-safety (root cause of PyBorrowMutError)**: Prevented background threads from mutating live `Trade` objects via `update_status(trade=...)` or account-level calls that trigger internal Rust borrows. Primary path now relies on `handle_order_event` callbacks. Reconcile fallback uses non-mutating `order_deal_records()` (query + order_id match). Full review feedback addressed:
  - Removed all live trade mutation in bg paths (reconcile/place_order no longer call update_status on trade objects).
  - Fixed empty `order_id` at place time (backfill from first callback; post-place population only in non-sim when necessary).
  - Consistent simulation short-circuit for entire broker reconcile (callback/test injection only).
  - `pending_since` uses consistent internal `_clock()` (no exchange_ts mix to avoid skew).
  - Order worker now catches `BaseException` (prevents critical path silent death).
  - Removed bg reads of live trade.status in reconcile; pre-pop support only for direct test/reconnect paths via records.
  - Enhanced callback handlers to backfill `pending_order_id` if missing at arm time.
  - `place_order` defers `pending_armed` EXEC when `order_id` empty at place time (callback backfill emits the single compliant event; fixes duplicate armed in replay).
  - `_still_own_pending` no longer reads live trade; empty `pending_order_id` still counts as owned so timeout can clear stuck sim pending.
  - `place_order` log uses captured `oid` only (no second read of `trade.order.id`).
  - `except BaseException` in `_timeout_loop` (thread resilience).
  - SPEC.md and lock rules updated.

  This eliminates the source of Shioaji internal concurrent borrow instead of adding more locks. All 95 runtime tests pass.

#### Added

- **FT-002 Phase 4** `DecisionAudit` structure fields + `format_decision_audit` for `structure_veto` / armed enrichment。

- **KERNEL UAT regression** `tests/runtime/test_kernel_uat_regression.py`: B3 `event_code` 12/13 reconnect, B4 pending-timeout CRITICAL + `sync_positions` + `EXEC_AUDIT`, B6 `sync_positions` → `get_state_snapshot` chain (85 kernel tests).

- **FT-001 Phase 1** `DecisionAudit` + emitter in strategy; `episode_id` generation (date-seq); enriched `SignalAudit` (entry/exit fields); `EXEC` prep (pending ids stored in kernel).
- Audit fields are optional; old logs/parsers/determinism unaffected.

- **FT-001 Phase 2** Kernel `signal_id` assigned to every `OrderSignal`; `ExecAudit` + `EXEC_AUDIT` emissions for `pending_armed` / `pending_cancelled` / `pending_timeout` / `position_sync`.

### [0.2.2] - 2026-06-17

#### Added

- **P0** `RiskGate.atr_stale`: blocks new entries when last successful ATR refresh is older than `atr_refresh_sec × atr_stale_multiplier` (default 2×).
- **P4-13** Reconnect warmup: `reconnect_warmup_sec` (default 300) blocks new entries after reconnect until exchange tick ts catches up; exits still allowed.
- **P4-13** Daily disconnect limit: `max_disconnects_per_day` (default 3) sets `block_new_entry` + CRITICAL alert.
- **P4-13** Alert on disconnect with open position (`alert_on_disconnect_with_position`, default true).

#### Changed

- ATR refresh: `last_atr_refresh` advances only on **successful** kbars fetch; failed refreshes retry sooner (30s when never succeeded, else `atr_refresh_sec`).
- `_maybe_refresh_atr` uses in-flight guard to avoid duplicate daemon threads.

### [0.2.1] - 2026-06-16

Patch release to support `strategy-vwap-momentum` v0.1.0 (first public reference strategy plugin) and improve sweep integration.

#### Added

- `momentum_timeout_sec` (with const `MOMENTUM_TIMEOUT_SEC`) to `Settings`, `SWEEP_FIELD_TO_CONST`, `_CONST_TO_SNAKE`, and test defaults.
  - Enables first-class `patch_strategy_params` / sweep support for the momentum episode timeout in strategy plugins.
  - Default 180s (matching previous hardcoded value in the reference plugin).

#### Changed

- `SWEEPABLE_PARAMS` in consuming strategy plugins (e.g. `strategy-vwap-momentum`) will now automatically surface `MOMENTUM_TIMEOUT_SEC`.

### [0.2.0] - 2026-06-16

UAT-ready release addressing CodeReview#2 (see `docs/ARCHIVE/reviews/` for re-review).

#### Added

- `TradingEngine.get_state_snapshot()` and frozen `EngineStateSnapshot` for read-only state observation
- `_validate_order_signal()` — kernel rejects invalid `OrderSignal` before arming pending
- `RuntimeConfig.warn_if_placeholder_credentials()` on live login
- Docs: LIVE_SAFETY, UAT checklist, ARCHIVE migration notes
- README: Disclaimer, Live Safety, Go-Live Checklist, Secrets, Logging (`configure_root=False`)
- `.env.example`, `examples/minimal_live/`
- CI `quality` job: ruff lint/format, gradual mypy, explicit no-shioaji guard step
- Tests: `test_state_snapshot.py`, `test_signal_validation.py` (73 kernel tests total)

#### Changed

- Logger name `theman` → `trading_engine`; lazy `get_logger()` init
- SPEC.md: CI status, position model scope (§4.2.1), theman section historicalized
- Ruff format applied across `src/` and `tests/` (CI enforcement)

#### Fixed

- Removed last `theman` reference in `NullTelemetryPort` docstring

### [0.1.0] - 2026-06 (initial public release)

- Broker-agnostic futures execution kernel (Shioaji + Mock adapters)
- `position_qty` model, kernel-owned force-flatten, reconnect reconcile
- 63 kernel tests, GitHub Actions CI matrix (Python 3.11–3.13)
- Core docs: README, SPEC, DESIGN (now archived)

---

## trading-backtest

### [Unreleased]

#### Changed

- **`loader` tick validation**: warn on non-positive price / large jumps / unsorted input; **identical full rows** logged at INFO and **kept for replay** (same-ms different price = silent). SPEC §7 documents adhoc tick×kbar volume cross-check (kbar `ts` = minute end; raw tick sum must match `Volume`; do not dedupe identical rows on load).

#### Fixed

- **`loader` kbar cache**: `load_kbars_csv` / `iter_kbars_in_range` now read `tick_cache/{code}_kbars_{date}.csv.gz` mirrors (plain CSV still preferred when both exist), so backtest ATR warmup works after `python -m storage` compresses kbar mirrors.

### [0.1.1] - 2026-06-16

#### Fixed

- `MockBroker.process_matching_queue`: coerce `tick.close` with `float()` so CSV replay ticks (str close) match against limit price without `TypeError`.

### [0.1.0] - 2026-06-16

Initial public release of the deterministic tick replay driver for `trading-engine`.

#### Added

- `BacktestEngine`: thin deterministic host that wires `TradingEngine` (exact same as live) + `MockBroker` + `VirtualClock` + replay loop.
- `MockBroker`: IOC matching, latency gate, normal/blowout/flatten slippage, no-lookahead kbars via loader, spread calibration option.
- `loader`: `iter_replay_ticks`, `ReplayTick`, kbar helpers, cache (plain + .gz), data-quality warnings.
- `VirtualClock`: injectable clock for determinism (no `time.time()`).
- `validation`: audit log parsing, determinism hash, backtest-vs-reference fill comparison.
- Examples: `compare_fill_audits.py`, `tick_cache_template.py`, `minimal_backtest_smoke.py`.
- Tests (25+): MockBroker, BacktestEngine, loader guards, validation helpers.
- Package metadata, MIT license, py.typed, runnable `python run_tests.py`.

#### Documentation (pre-release polish)

- Rewrote standalone SPEC.md — authoritative spec for this package.
- Added prominent **Backtest Fidelity & Limitations** sections to README and release notes.

#### Changed / Notes

- Depends on `trading-engine>=0.2.0,<1.0`. Iron laws: reuses same `TradingEngine`; no strategy hard-coding; determinism contract.

---

## strategy-vwap-momentum

### [Unreleased]

#### Changed

- **`risk_blocked` DECISION_AUDIT**：`_emit_risk_blocked_audit` 依 `obs.record_risk_blocked()` 節流（60s/reason，與 `DailyObservability` 共用）。

- **FT-002 Phase 4** `_try_pullback_entry` 改用 `regime_allows_entry`；`structure_veto` DECISION_AUDIT；`momentum_armed` structure 戰場快照；`structure_stale` → `risk_blocked`。

#### Added

- **FT-002 Phase 1** `strategy_vwap_momentum.structure`: frozen SMC v0.1 (`compute_structure`, `regime_allows_entry`, `structure_allows_entry`); 15+ unit tests (`test_structure.py`). No engine wiring yet (`structure_filter_enabled` not in runtime).

---

### [0.1.2] - 2026-06-17

#### Added

- Block new entries when `RiskGate.atr_stale` or `RiskGate.reconnect_warmup_active` (exits unchanged).

#### Changed

- Depends on `trading-engine>=0.2.2,<1.0`.

### [0.1.1] - 2026-06-16

#### Fixed

- `_try_pullback_entry`: define `trend_dir` from `market.trend_dir` before `trend_allows_entry` / `trend_veto` audit (fixes `NameError` on pullback entry path).

### [0.1.0] - 2026-06-16

Initial public release of the first reference `strategy-<name>` plugin for `trading-engine`.

#### Added

- `VWAPMomentumStrategy` — full implementation of the `trading_engine.core.strategy.Strategy` Protocol.
- `StrategyParams` + live overlay / sweep helpers for research & calibration.
- `trend.py` — `compute_trend`, Level-2 gating, dynamic trail / vwap-stop math.
- Rich `SignalAudit` builders; unit & behavior tests (~27 tests).
- Entry point registration: `trading_engine.strategies = "vwap_momentum"`.
- Package metadata, MIT license, py.typed, runnable `python run_tests.py`.

#### Changed / Notes

- Removed dead `MomentumState.peak` + `update_momentum_peak()`.
- `MOMENTUM_TIMEOUT_SEC` moved into `StrategyParams.momentum_timeout_sec` (sweepable).
- Depends on `trading-engine>=0.2.0,<1.0`.

---

## trading-app

### [Unreleased]

#### Changed

- **TMFR1 摩擦上線**：`friction.enabled: true`；`mode: ntd`（單邊手續費 15 NTD ×2 + 稅 20 NTD = **5 點/趟**）；SSOT [`workspaces/SHARED_ASSUMPTIONS.md`](workspaces/SHARED_ASSUMPTIONS.md) §3.1。DAILY_SUMMARY `expectancy_net` / sweep `valid_score` 以 net 為準。`observability` 每次 summary 自 `CONFIG_PATH` 重讀 friction。

#### Added

- **FT-003 調參硬化**：`sweep.holdout_guard`（2026-05 封印；`FT003_HOLDOUT_UNSEAL=1` 解封）已接線至 `param_sweep.sweep`、`backtest`、`overlay_smoke`；`sweep.overlay_smoke`（grid key 開工前驗證：KPI 變化或執行/計時 key 之 overlay 讀回）；`param_sweep` KPI 新增 `trade_count`；grid combo 硬上限 **36**、keys 上限 **4**（SPEC §4.4）。

- **`storage.cache_audit` / `storage.cache_repair`**：`python -m storage.cache_audit --code TMFR1` 掃描 `tick_cache/` 逐日輸出 `差異vols` / `ohlc差` / `kbars:N/300`；`cache_repair --fix` 自動 TMFR1+TMFR2 跨月尾盤合併、從 ticks 補 kbar 缺口並重稽核。`backfilldata` 預設 `--merge-rollover`（`--no-merge-rollover` 關閉）。模組：`storage/tick_rollover.py`、`storage/kbar_repair.py`；`kbar_loader.dedupe_kbars`。

- **`python -m backfilldata month YYYY-MM`**：依 [pin-yi Taiwan calendar](https://api.pin-yi.me/taiwan-calendar/{year})（`isHoliday`）篩選當月交易日（跳過週末與國定假日）；自動以 10 日為一批符合 Shioaji tick 上限；`--dry-run` 預覽、`--no-holiday-calendar` 僅跳週末、API 失敗時 fallback 週末模式。

- **`python -m live.order_smoke`**: Manual UAT smoke for Shioaji Buy/Sell IOC — raw `place_order` + `TradingEngine` path; `DUMP_ORDER_EVENTS=1` recommended. Refuses `simulation: false`.

- **`--dates-from-cache`** on `python -m backtest` and `python -m reporting.calibration_cli`：自動掃描 `tick_cache/{code}_YYYY-MM-DD.csv[.gz]`（排除 `_kbars_` mirror）；可選 `--from-date` / `--to-date` 區間篩選（僅與 `--dates-from-cache` 併用）。共用 `storage.tick_loader.resolve_cli_tick_cache_dates`。
- **`python -m backtest --report` / `--log-file`**：回放後從 backtest log 產出 UAT 報告（終端只印結論；完整 replay log + metrics JSON）。`--dates` → `logs/backtest_{code}_{date}.log` + `reports/backtest_{code}_{date}.json`；`--dates-from-cache --cache-dir tick_cache/2026_05` → `backtest_2026_05.*`。
- **`reporting.uat_report.read_log_text`**：支援 UTF-8 / UTF-16（PowerShell `Tee-Object`）。

#### Fixed

- **`storage/tick_loader` / `storage/kbar_loader` historical `ts` decode**: SSOT in `trading_engine.calendar.shioaji_ts.shioaji_historical_ts_from_ns`. Read paths do no time correction. Re-fetch pre-2026-06-26 tick/kbar caches with `--overwrite` if stored with the old +8 decode.

- **`python -m backtest --report`**：修正 logging 接線（`configure_backtest_session_logging` 於 `BacktestEngine` 前呼叫 `setup_async_logging`，audit 寫入 backtest log 而非僅 `LOG_FILE`）；`flush_async_logging` 後再 parse。
- **Plain `python -m backtest`**（無 `--report`/`--log-file`）：恢復寫入 config `LOG_FILE`（不再被空 session 鎖死 `_logging_configured`）。

- **`storage/kbar_loader`**: `load_kbars_csv`, `iter_kbars_in_range`, and cache-satisfaction checks accept gzip kbar mirrors in `tick_cache/` (plain preferred); fixes 0-trade backtests when only `*_kbars_*.csv.gz` remains after storage compression.

- **`storage/tick_loader` / `backfilldata`**：`api.ticks(AllDay)` 改用 30s timeout（Shioaji 預設 5s 常不足以下載全日 tick）；逾時自動重試最多 3 次（間隔 2s）。`storage/kbar_loader` 同步將 `api.kbars` timeout 設為 30s。

#### Removed

- **`storage/tick_loader` read-time legacy +8h normalization + `_ns_to_taipei_naive` + `shioaji_ts_from_ns` alias**: tick read/backfill/replay paths (`load_merged_tick_cache`, `download_and_cache`, `iter_replay_ticks`, `tick_cache_satisfies_request`, `cache_audit`, `cache_repair`, `kbar_repair`, `tick_rollover`, `trading_backtest.loader`) no longer transform timestamps on read — the CSV cache is the single source of truth and is read verbatim. Pre-2026-06-26 +8h files must be deleted and re-fetched (`--overwrite`).

#### Changed

- **`python -m backtest --report`**：移除 `--report-json`；`--report` 一律寫 log + JSON。`--dates-from-cache` 輸出檔名改為 `backtest_{cache_dir_name}`（預設 `tick_cache/` → `backtest_tick_cache`；`--from-date`/`--to-date` 加 `_{date_range}` 後綴；cache 在 monorepo 外則 `{parent}_{leaf}`）；`--dates` 維持 `backtest_{code}_{date}`；`--log-file` 時 JSON 為 `reports/{log_stem}.json`。

- **`backfilldata` tick query mode**: default tick fetch switched from `TicksQueryType.AllDay` to `TicksQueryType.RangeTime` (`08:45:00`–`13:45:00`) for UAT day-session補洞; CLI adds `--time-start` / `--time-end` and `--all-day-ticks`.
- **`storage/tick_loader` gap merge**: RangeTime backfill merges into existing partial cache (dedupe by `datetime`); removes stale `*.csv.gz` when rewriting plain CSV; `--overwrite` replaces only the requested window and keeps out-of-window ticks.
- **`storage/tick_loader` window quality**: 1-minute edge tolerance for session bounds; large in-window gap re-fetch trigger.
- **`storage/kbar_loader`**: post-fetch session filter + merge (same window rules as ticks); mirror no longer force-overwrites existing `tick_cache` kbars on skip paths unless `--overwrite`; simulation tick/kbar ts via shared `shioaji_historical_ts_from_ns`.
- **`risk_blocked` 節流**：`RISK_BLOCKED_THROTTLE_SEC`（60s/reason）；`record_risk_blocked` 回傳 `bool`；`DAILY_SUMMARY.risk_blocked_count` 與 strategy `DECISION_AUDIT` emit 共用節流（先前僅 counter 節流）。

- **Default contract `product_code`**: `TXFR1`（大台近月）→ **`TMFR1`（微台近月）** for 奈米戶 UAT/Pilot；`point_value_ntd: 10` 已對齊微台。大台/小台仍可用 `TXFR1` / `MXFR1`，需分開 `tick_cache` 與校準。
- **Docs**: UAT checklist、README、ops、strategy README 範例改為 `TMFR1` 或 `{product_code}` 占位；Phase 0 快照 `snapshots/config_20260622.yaml` 保留歷史 `TXFR1`。

#### Added

- **`backfilldata` CLI** — `python -m backfilldata date YYYY-MM-DD [end]`：透過 Shioaji `api.ticks` / `api.kbars` 補歷史 tick、kbar 快取；預設寫入 `tick_cache/` + `kbar_cache/`（kbar mirror 至 `tick_cache` 對齊 UAT archiver）；辨識 `*.csv.gz` 已壓縮 tick、單次 ≤10 tick 日 / ≤270 kbar 日；模組文件 `apps/trading-app/src/backfilldata/{README,SPEC}.md`。

#### Changed

- **`storage/tick_loader`**: `download_and_cache` 以 `resolve_tick_cache_path` 跳過已存在 plain CSV 或 gzip，避免 `python -m storage` 後重複打 API。
- **`storage/kbar_loader`**: `download_and_cache_kbars` 支援 `simulation=`、`mirror_cache_dir`、`pace_sec`；mirror 自 primary 強制同步，避免 `tick_cache` 殘留舊 kbar。

- **FT-002 Phase 4** `observability.record_structure_veto` + `episode_funnel.structure_veto`；`uat_report` 將 `structure_veto` 計入 episode outcome `veto`。

- **FT-001 Phase 1**: `DECISION_AUDIT` + `DecisionAudit` dataclass + `format_decision_audit`; `momentum_armed` emission from `vwap-momentum` with `episode_id`; `SignalAudit`/`FillAudit` enriched with optional `episode_id`/`signal_id`/exit fields; `episode_id` propagated through pending to entry FILL.
- `build_exit_audit` now carries `entry_price`, `hold_ticks`, `in_grace`, stop levels, `trailing_peak`.
- Unit tests in `strategy` for armed DECISION and enriched exits (Phase 1 DoD).
- **FT-001** `docs/features/audit-event-replay/`: audit event replay SPEC + PLAN (qualified audit contract, episode timeline examples); `docs/features/` feature board + `_template/`.
- Grok project skill **`audit-event-replay`** (slash `/audit-event-replay`) for FT-001 implementation and audit contract review.
- FT-001 **REVIEW.md** (senior-trader): pressure metrics, high-pressure episode §6.4, Agent consumers §8.2; FT-002/003 scoped out.
- Grok project skill **`senior-trading-professional`** (slash `/senior-trading-professional`): risk-first trader persona for strategy review, Pilot Go/No-Go, sweep interpretation, CAL-8 framing.
- Role prompts: `prompts/roles/senior-trading-professional.md`, `prompts/roles/references/txf-gates.md` (UAT / Pilot / Live gate quick reference).

#### Added / Changed (UAT to Pilot hardening)

- `determinism_check.py` CLI for UAT evidence collection.
- `docs/uat/APP.md` (formerly UAT_CHECKLIST) v2: phased UAT→Pilot flow, evidence collection, Pilot Readiness Gate.
- Monorepo docs slim: single root CHANGELOG, centralized `docs/`.

#### FT-001 Phase 3 + Phase 4 (Audit Event Replay)

- **Phase 3**: `parse_decision_audit_line` / `parse_exec...`, `build_episode_timeline` + richer `Episode` (pressure_context, trade_date, outcome), `--episodes` / `--episode-id` CLI, `build_tuning_hints` using episode funnel + pressure, `DAILY_SUMMARY` with `episode_funnel` + `pressure` (max_consec, ratio, risk_blocked_count), streak emit in DECISION_AUDIT.
- Synthetic fixture + snapshot test for `--episodes`.
- **Phase 4 migration/land**: trend_veto/momentum_timeout/risk now primary via `DECISION_AUDIT` (legacy SIGNAL removed); determinism includes DEC/EXEC; contracts merged to `apps/trading-app/SPEC.md`; strategy SPEC updated; status → Landed.
- Risk_blocked now throttled (60s/reason).
- Full review fixes + 89+ tests green.

#### CLI discoverability

- **`python -m cli_help`**: catalog of all trading-app entry points; delegates to per-module `--help`.
- Richer `--help` epilog examples on `live`, `reporting`, `uat_evidence_export`, `pilot_gate_check`, `determinism_check`, `storage`, `backtest`.
- Root [`README.md`](README.md) + [`apps/trading-app/README.md`](apps/trading-app/README.md) CLI index tables.

#### Fixed (CLI discoverability follow-up)

- **`live --help`**: lazy-import Shioaji/engine after `argparse`; `raise SystemExit` exit semantics aligned with other CLIs.
- **`cli_help` delegate**: subprocess sets `cwd=src` and `PYTHONPATH` (app `src/` + monorepo sibling packages); removed dead `--list` flag.
- **Doc SSOT**: [`SPEC.md`](apps/trading-app/SPEC.md) + root [`README.md`](README.md) aligned with `CATALOG` (`storage`, `determinism_check`, `calibration_cli`); `storage.compress` documented as alias.
- **Tests**: +5 (`test_cli_help`: SPEC↔catalog drift guard, delegate mock/integration, `live --help` without `shioaji` import); **121** app tests green.

#### Hybrid ops (on-prem research + GCE live)

- **[`docs/ops/HYBRID_DEPLOY.md`](docs/ops/HYBRID_DEPLOY.md)**: 地雲雙管架構、GCE `asia-east1` 規格（`e2-standard-2` UAT/Pilot）、tick_cache rsync 流程。
- **[`docs/ops/LinuxOps.md`](docs/ops/LinuxOps.md)**: systemd、cron、`post-session.sh`；[`scripts/linux/`](scripts/linux/)（`start-trading-app.sh`, `install-systemd.sh`, `sync-from-gce.sh`）。
- **Doc sweep**: `python -m storage` 為主、`storage.compress` alias — [`TODO.md`](docs/TODO.md), [`AGENTS.md`](docs/AGENTS.md), [`uat/APP.md`](docs/uat/APP.md), [`WindowsOps.md`](docs/ops/WindowsOps.md)；測試基線 **269**（85+27+36+121）。
- **`calibration_cli`**: `--help` epilog examples；`cli_help.parse_spec_cli_modules()` 從 SPEC 解析防 catalog drift。

#### Fixed (hybrid ops review follow-up)

- **`install-systemd.sh`**: `chown -R tfx:tfx` monorepo + data dirs；env `640 root:tfx`；`TICK_ARCHIVE`/`KBARS_ARCHIVE` 預設啟用。
- **`post-session.sh`**: source `/etc/tfx-trading/env`；加 `determinism_check` → `snapshots/`；略過缺 log。
- **`sync-from-gce.sh`**: `ubuntu@` deploy 帳號；sync `kbar_cache/`；遠端缺目錄不 fail。
- **`parse_spec_cli_modules`**: 僅解析 SPEC `## CLI` 表格；`calibration_cli` Linux epilog；AGENTS/SPEC 測試數對齊。

#### UAT tooling (Phase 3–5 automation)

- **`reporting.uat_evidence_export`**: broker reconciliation + tick stratification CSV from `reports/day*.json`; merge-by-date; `--broker-data` import; invalid PnL safe-parse.
- **`sweep.pilot_gate_check`**: APP.md Phase 5 auto checklist (sample, density, expectancy, Sharpe per-trade/daily, MDD, big-loss streak, Critical scan); reads broker/tick evidence CSV when present.
- **`reporting.metrics_extract`** / **`reporting.evidence_csv`**: shared JSON→metric helpers + CSV validation for gate.
- **Episode timeline**: EXEC `pending_*` via `signal_id`; `position_sync` operational section in `--episodes` output.
- **Tests**: +23 (112 app tests); KERNEL regression in engine package.
- **Docs**: [`docs/uat/APP.md`](docs/uat/APP.md), [`uat_evidence/README.md`](uat_evidence/README.md), [`apps/trading-app/SPEC.md`](apps/trading-app/SPEC.md).

#### Changed

- BeforePilot content fully merged into [`docs/uat/APP.md`](docs/uat/APP.md) Phase 5 (Pilot Readiness Gate).
- Emphasis on determinism hash discipline from monorepo root.
- Phase 3/4 evidence CSV: manual copy-from-template → `python -m reporting.uat_evidence_export` (broker PnL still human/API sourced).

### [0.1.2] - 2026-06-17

#### Added

- P4-13 `operations` config: reconnect warmup, disconnect limits, `atr_stale_multiplier`
- Cumulative MDD risk budget in `uat_report` / `performance_metrics`

#### Changed

- Pin `trading-engine@v0.2.2`, `strategy-vwap-momentum@v0.1.2`
- Docs sync: README, SPEC, UAT, Architecture, WeeklyStatus

### [0.1.1] - 2026-06-16

#### Changed

- Remove deprecated `theman_*` port / config aliases; use `trading_app_*` symbols only
- Alert prefix `[theman]` → `[trading-app]`
- Windows ops: `start-trading-app.ps1`, `register-task.ps1` default task `trading-app-vwap`
- Pin siblings: `trading-backtest@v0.1.1`, `strategy-vwap-momentum@v0.1.1`

#### Fixed

- Sweep tick helpers: `ReplayTick.close` as `str` (pairs with backtest MockBroker float coercion fix)

### [0.1.0] - 2026-06-16

First public release as **reference integrator app** (renamed from internal `theman`).

#### Added

- `pyproject.toml`, `SPEC.md`, `LICENSE`, `.env.example`
- `trading_app_engine_ports()` wiring for live, backtest, and tests
- `reporting/` UAT log parser; `storage/` tick/kbar archive; `sweep/` param research tooling
- CI: standalone clone via git-tagged sibling packages

#### Changed

- Renamed from `theman` → `trading-app`
- Dependencies: `trading-engine`, `trading-backtest`, `strategy-vwap-momentum`
- App tests scoped to integration / storage / reporting / sweep (~30 tests)

#### Notes

- **UAT-ready**, not Live-ready — see `docs/uat/APP.md`