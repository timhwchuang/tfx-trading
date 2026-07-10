from __future__ import annotations

import datetime
import queue
import threading
import time
from collections.abc import Callable
from typing import Any

from trading_engine.api_errors import is_api_session_error
from trading_engine.book import BOOK_FIELD_NAMES, Book
from trading_engine.calendar.port import MarketCalendarPort, TaifexMarketCalendar
from trading_engine.connectivity import LINK_FIELD_NAMES, ConnectivityState
from trading_engine.connectivity_ops import ConnectivityOpsService, ReconnectOutcome
from trading_engine.capital import CapitalService
from trading_engine.core.capital_store import CapitalStore
from trading_engine.core.engine_service import EngineService
from trading_engine.core.host_service import service_defines
from trading_engine.core.ports import BrokerPort
from trading_engine.core.runtime_config import RuntimeConfig
from trading_engine.core.side_effect_ports import (
    AlertPort,
    ArchivePort,
    NullAlertPort,
    NullArchivePort,
)
from trading_engine.core.strategy import Strategy
from trading_engine.core.types import (
    EngineStateSnapshot,
    MarketSnapshot,
    OrderSignal,
    PositionSnapshot,
    RiskGate,
    TickSnapshot,
)
from trading_engine.integrity import INTEGRITY_FIELD_NAMES, IntegrityState
from trading_engine.locking import DomainLock, assert_api_entry_allowed
from trading_engine.logging_setup import get_logger, shutdown_async_logging
from trading_engine.maintenance import MaintenanceScheduler, default_engine_jobs
from trading_engine.order_executor import OrderExecutor
from trading_engine.position_sync import PositionSyncService
from trading_engine.reconcile import (
    check_position_reconcile,
    is_severe_drift,
    severe_drift_confirmed,
)
from trading_engine.risk_gate import build_risk_gate
from trading_engine.session import SessionService
from trading_engine.tick_watchdog import TickWatchdogService
from trading_engine.ticks import TICK_FIELD_NAMES, TickState

logger = get_logger()

# Former flat surface names (Phase B/C forwarders). Reject writes so callers
# cannot silently create dead instance attrs after G1 demagic.
_REJECTED_FLAT_ATTRS: frozenset[str] = (
    BOOK_FIELD_NAMES
    | LINK_FIELD_NAMES
    | INTEGRITY_FIELD_NAMES
    | TICK_FIELD_NAMES
)

# Re-export for call sites / tests that imported from engine historically.
__all__ = ["TradingEngine", "ReconnectOutcome"]


class TradingEngine:
    """Execution host dispatcher (Phase G3 — no Mixin MRO).

    Domain state lives on composed owners (``_book`` / ``_link`` / …).
    Behavior lives on injected services (``orders`` / ``positions`` / …).
    Public call sites keep ``engine.place_order`` etc. via ``__getattr__``
    routing to the service that defines the method.
    """

    def __init__(
        self,
        api: BrokerPort,
        clock: Any = None,
        strategy: Strategy | None = None,
        runtime_config: RuntimeConfig | None = None,
        order_adapter: Any = None,
        alerts: AlertPort | None = None,
        archive: ArchivePort | None = None,
        calendar: MarketCalendarPort | None = None,
        capital_store: CapitalStore | None = None,
    ):
        if runtime_config is None:
            raise TypeError("runtime_config is required; inject at app layer")
        if order_adapter is None:
            raise TypeError("order_adapter is required; inject at app layer")
        self._cfg = runtime_config
        self._alerts = alerts or NullAlertPort()
        self._archive = archive or NullArchivePort()
        self._calendar = calendar or TaifexMarketCalendar()
        if api is None:
            raise TypeError("api is required; inject a BrokerPort at the app layer")
        self.api = api
        self._order_adapter = order_adapter
        # Optional hook set by live bootstrap (e.g. ShioajiLiveBootstrap.subscribe_tick).
        self._resubscribe_ticks: Callable[[], None] | None = None
        # Optional hook set by live bootstrap to re-attach the order/deal report
        # channel (subscribe_trade + set_order_callback) after reconnect / relogin.
        # Without this, reconnect only restores quote ticks while order/fill
        # callbacks stay dead -> silent fills + perpetual pending timeouts.
        self._resubscribe_trade: Callable[[], None] | None = None
        # 注入式時鐘：實盤預設 time.time()；回測傳入 tick 時間驅動的時鐘以確保確定性。
        self._clock = clock if clock is not None else time.time
        if strategy is None:
            raise TypeError("strategy is required; inject at app layer")

        # Phase B/C/G1: composed state owners (explicit access only — no __getattr__).
        #   _book       — position + single flight (max_qty=1)
        #   _link       — broker connectivity / reconnect / warmup
        #   _integrity  — SETTLING / HALT / reconcile / miss CB
        #   _ticks      — last tick + no-tick counters
        #   _capital_svc — progressive MDD Host policy (impl not inlined here)
        self._book = Book(pending_ioc_slippage=int(self._cfg.ioc_slippage_points))
        self._link = ConnectivityState()
        self._integrity = IntegrityState()
        self._ticks = TickState()
        store = capital_store or CapitalStore(
            getattr(runtime_config, "capital_state_path", "") or ""
        )
        self._capital_svc = CapitalService(
            store,
            product_code=str(self._cfg.product_code),
            max_mdd_points=lambda: float(
                getattr(self._cfg, "max_mdd_points", 0) or 0
            ),
        )
        self._trading_date: datetime.date | None = None

        self._next_signal_seq: int = 0
        self._current_signal_date: str = ""
        # Staged CRITICAL alert (under lock) → flush outside lock.
        self._staged_critical_alert: str | None = None

        self.strategy: Strategy = strategy
        # Phase G0 dual-lock contract — see trading_engine.locking:
        # never acquire _api_lock while holding domain lock (self.lock).
        self.lock = DomainLock()
        self._api_lock = threading.RLock()  # Shioaji mutable ops; avoid PyBorrowMutError
        self.contract = None
        self._running = False
        self._raw_order_evt_dumped: set = set()
        self._order_queue: queue.Queue[OrderSignal | None] = queue.Queue()
        self._order_sync_mode = False
        self._order_worker_started = False
        # Phase G3: injected services (host-backed; engine is dispatcher only).
        self.orders = OrderExecutor(self)
        self.positions = PositionSyncService(self)
        self.connectivity = ConnectivityOpsService(self)
        self.watchdog = TickWatchdogService(self)
        self.session = SessionService(self)
        # Phase G4: isolated jobs replace serial _timeout_loop blob.
        self._maintenance = MaintenanceScheduler(
            default_engine_jobs(self),
            clock=self._clock,
        )
        # Lifecycle-owned services (start/stop from run()).
        self._services: list[EngineService] = [self._maintenance, self.orders]

        # After staged-alert attr exists (persist fail may stage CRITICAL).
        self._load_capital_state()
        self._flush_staged_critical_alert()

    def __getattr__(self, name: str) -> Any:
        """Facade: route pipeline methods to the service that defines them."""
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        d = object.__getattribute__(self, "__dict__")
        for key in ("orders", "positions", "connectivity", "watchdog", "session"):
            svc = d.get(key)
            if svc is not None and service_defines(svc, name):
                return getattr(svc, name)
        raise AttributeError(
            f"{type(self).__name__!s} object has no attribute {name!r}"
        )

    def __setattr__(self, name: str, value: Any) -> None:
        # Phase G1 follow-up: reject former flat SSOT names (no silent dead attrs).
        if name in _REJECTED_FLAT_ATTRS:
            raise AttributeError(
                f"TradingEngine.{name} is not a writable attribute after Phase G1; "
                f"use self._book / _link / _integrity / _ticks (or Book mutation API)"
            )
        object.__setattr__(self, name, value)

    def _call_api(self, fn, *args, **kwargs):
        """Serialize Shioaji mutable calls under ``_api_lock`` (Phase G0).

        Must not be entered while the current thread holds the domain lock.
        Pattern: broker I/O first (or after releasing domain lock) → then
        ``with self.lock:`` for Book/Link/Integrity mutations.
        """
        assert_api_entry_allowed(self.lock)
        with self._api_lock:
            return fn(*args, **kwargs)

    @property
    def has_position(self) -> bool:
        """Derived from Book.position_qty (single source of truth for Phase 1+)."""
        return self._book.has_position

    @property
    def _capital(self):
        """Progressive capital book state (owned by CapitalService)."""
        return self._capital_svc.state

    @property
    def _capital_store(self) -> CapitalStore:
        """Durable capital store (owned by CapitalService)."""
        return self._capital_svc.store

    @_capital_store.setter
    def _capital_store(self, value: CapitalStore) -> None:
        """Test/helper rebind: rebuild CapitalService around a new store."""
        self._capital_svc = CapitalService(
            value,
            product_code=str(self._cfg.product_code),
            max_mdd_points=lambda: float(
                getattr(self._cfg, "max_mdd_points", 0) or 0
            ),
        )

    @property
    def capital_frozen(self) -> bool:
        """Sticky flag on the capital book (may be ignored when MDD gate is off)."""
        return self._capital_svc.capital_frozen

    @property
    def realized_pnl(self) -> float:
        return self._capital_svc.realized_pnl

    @property
    def equity_peak(self) -> float:
        return self._capital_svc.equity_peak

    @property
    def current_drawdown(self) -> float:
        return self._capital_svc.current_drawdown

    def _capital_gate_active(self) -> bool:
        """True when progressive MDD is configured to block entries (limit > 0)."""
        return self._capital_svc.gate_active()

    @property
    def entry_blocked(self) -> bool:
        """Ops latch or active capital freeze (Host entry gate, not strategy)."""
        return self._book.block_new_entry or self._capital_svc.blocks_entry()

    def clear_capital_risk(self) -> None:
        """Operator action: reset progressive MDD book and unfreeze capital."""
        with self.lock:
            _ok, alert = self._capital_svc.clear()
            if alert:
                self._stage_critical_alert(alert)
        self._flush_staged_critical_alert()
        logger.warning("資本風控已手動清除（realized_pnl / equity_peak / capital_frozen）")

    def _load_capital_state(self) -> None:
        """Boot/reload capital book via CapitalService; stage any CRITICAL alerts."""
        for msg in self._capital_svc.load():
            self._stage_critical_alert(msg)

    def _persist_capital_state(self) -> bool:
        """Thin wrapper: persist capital book (fill path prefers on_exit_fill)."""
        ok, alert = self._capital_svc.persist()
        if alert:
            self._stage_critical_alert(alert)
        return ok

    def _market_snapshot(
        self, ts: int, price: float, dt: datetime.datetime
    ) -> MarketSnapshot:
        return MarketSnapshot(ts=ts, price=price, dt=dt)

    def _position_snapshot(self) -> PositionSnapshot:
        """Read-only Book view for Strategy.evaluate."""
        return self._book.to_position_snapshot()

    def get_state_snapshot(self) -> EngineStateSnapshot:
        """Return a frozen read-only view of engine state.

        Flat names like ``position_qty`` / ``is_pending`` are **not** on
        ``TradingEngine`` after Phase G1 (writes raise; reads AttributeError).
        Mutate via ``_book`` Book API / services only; prefer this snapshot
        for app/smoke read paths.
        """
        with self.lock:
            return EngineStateSnapshot(
                position_qty=self._book.position_qty,
                position_dir=self._book.position_dir,
                entry_price=self._book.entry_price,
                is_pending=self._book.is_pending,
                pending_intent=self._book.pending_intent,
                exit_pending=self._book.exit_pending,
                pending_qty=self._book.pending_qty,
                filled_qty=self._book.filled_qty,
                daily_pnl=self._book.daily_pnl,
                consecutive_loss=self._book.consecutive_loss,
                block_new_entry=self.entry_blocked,
                api_connected=self._link._api_connected,
                has_position=self.has_position,
                trailing_peak=self._book.trailing_peak,
                ticks_since_entry=self._book.ticks_since_entry,
                settling=self._integrity._settling,
                position_unconfirmed=self._integrity._position_unconfirmed,
                capital_frozen=self._capital.capital_frozen,
                realized_pnl=self._capital.realized_pnl,
                equity_peak=self._capital.equity_peak,
                current_drawdown=self._capital.current_drawdown,
            )

    def _risk_gate(self, ts: int, dt: datetime.datetime) -> RiskGate:
        """Delegate to ``risk_gate.build_risk_gate`` (Wave 3 RiskAssembler)."""
        return build_risk_gate(self, ts, dt)

    def _parse_tick_locked(self, tick: Any) -> tuple[int, float, int, int, int]:
        """Parse tick inside lock; infer buy/sell from price when type0."""
        ts = int(tick.datetime.timestamp())
        price = float(tick.close)
        volume = int(tick.volume)
        original_tick_type = int(getattr(tick, "tick_type", 0) or 0)
        tick_type = original_tick_type

        if tick_type == 0 and self._ticks.last_tick_price > 0:
            if price > self._ticks.last_tick_price:
                tick_type = 1
            elif price < self._ticks.last_tick_price:
                tick_type = 2

        self._ticks.last_tick_price = price
        if original_tick_type == 0 and tick_type in (1, 2):
            self._ticks._tick_type_inferred_counts[tick_type] = (
                self._ticks._tick_type_inferred_counts.get(tick_type, 0) + 1
            )
        return ts, price, volume, tick_type, original_tick_type

    def on_tick(self, tick: Any):
        """Hot path for one market tick (broker native or TickSnapshot).

        Reading map (under ``self.lock``):
          1. Normalize tick → price/ts/type (``_ticks``)
          2. Record arrival + reconnect warmup (``_link`` / ``_ticks``)
          3. Kernel force-flatten at session boundary (session)
          4. Strategy evaluate → OrderSignal | None (uses Book + RiskGate)
          5. Validate + arm flight (Book) / audit
        Outside lock: archive enqueue, place order worker.
        Integrity (SETTLING/HALT) freezes strategy via RiskGate; capital via entry_blocked.
        """
        signal: OrderSignal | None = None
        ts = 0
        price = 0.0
        volume = 0
        tick_type = 0
        original_tick_type = 0
        exchange_dt = None
        with self.lock:
            # --- 1. normalize ---
            if isinstance(tick, TickSnapshot):
                ts = tick.ts
                price = tick.price
                volume = tick.volume
                tick_type = tick.tick_type
                original_tick_type = tick_type  # already normalized by adapter
                exchange_dt = tick.exchange_dt
                self._ticks.last_tick_price = price  # minimal side effect for inference path
            else:
                ts, price, volume, tick_type, original_tick_type = self._parse_tick_locked(tick)
                exchange_dt = getattr(tick, "datetime", None) or (
                    self._ticks._last_tick_exchange_dt or datetime.datetime.fromtimestamp(ts)
                )

            # --- 2. arrival + warmup ---
            self._record_tick_arrival_locked(ts, exchange_dt, tick_type)
            self._arm_reconnect_warmup_on_first_tick_locked(ts)
            self._book.note_tick_while_held()

            # --- 3–4. kernel flatten, then strategy ---
            dt_for_risk = (
                exchange_dt or tick.datetime if not isinstance(tick, TickSnapshot) else exchange_dt
            )
            signal = self._maybe_kernel_force_flatten(ts, price, dt_for_risk)
            if signal is None:
                signal = self.process_strategy(ts, price, dt_for_risk)

            if signal is not None:
                if not self._validate_order_signal(signal):
                    signal = None
                else:
                    if signal.intent == "entry":
                        self._integrity._pending_intent_cancel_exchange_dt = dt_for_risk
                    elif signal.intent == "exit":
                        # P1-1: kernel owns exit sizing — always flatten the full
                        # held position regardless of what the strategy requested
                        # (strategy may default to 1 lot). Prevents leaving a
                        # residual broker position unmanaged after a stop/exit.
                        if self._book.position_qty > 0:
                            signal.qty = self._book.position_qty
                    if not getattr(signal, "signal_id", ""):
                        signal.signal_id = self._make_signal_id(signal.exchange_ts or ts)
                    if signal.audit is not None and not getattr(signal.audit, "signal_id", ""):
                        signal.audit.signal_id = signal.signal_id
                    self._arm_pending(signal)
                    self._log_signal_audit(signal)

        self._archive.enqueue_tick(tick, tick_type)

        if volume >= 20:
            logger.debug(
                "Tick | Price:%.1f | Vol:%d | Type:%d (orig=%d)",
                price,
                volume,
                tick_type,
                original_tick_type,
            )

        if signal is not None:
            self._enqueue_order(signal)

    def _today(self) -> datetime.date:
        """交易所「今天」：有 tick 時以 tick 日期為準（回測確定性），否則用系統日期。"""
        if self._ticks._last_tick_exchange_dt is not None:
            return self._ticks._last_tick_exchange_dt.date()
        return datetime.date.today()

    def _make_signal_id(self, ts: int) -> str:
        """Generate per-day signal_id like 20260617-sig-007. Used for every OrderSignal (Phase 2)."""
        try:
            from trading_engine.calendar.taifex import TAIWAN_TZ

            dt = datetime.datetime.fromtimestamp(ts, tz=TAIWAN_TZ)
            date_str = dt.strftime("%Y%m%d")
        except Exception:
            dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
            date_str = dt.strftime("%Y%m%d")
        if date_str != self._current_signal_date:
            self._current_signal_date = date_str
            self._next_signal_seq = 0
        self._next_signal_seq += 1
        return f"{date_str}-sig-{self._next_signal_seq:03d}"

    @staticmethod
    def _is_severe_drift(
        kernel_qty: int,
        kernel_dir: str,
        broker_qty: int,
        broker_dir: str,
    ) -> bool:
        """Delegate to reconcile module (compat for tests / call sites)."""
        return is_severe_drift(kernel_qty, kernel_dir, broker_qty, broker_dir)

    def _severe_drift_confirmed(
        self,
        kernel_qty: int,
        kernel_dir: str,
        broker_qty: int,
        broker_dir: str,
    ) -> bool:
        return severe_drift_confirmed(
            self, kernel_qty, kernel_dir, broker_qty, broker_dir
        )

    def _prune_cleared_orders(self) -> None:
        ttl = int(self._cfg.cleared_order_registry_sec)
        if ttl <= 0:
            return
        now = self._clock()
        while self._integrity._recent_cleared_orders and now - self._integrity._recent_cleared_orders[0][2] > ttl:
            self._integrity._recent_cleared_orders.popleft()

    def _record_cleared_pending(self) -> None:
        """Caller holds lock."""
        order_id = self._book.pending_order_id
        intent = self._book.pending_intent
        if not order_id or not intent:
            return
        if int(self._cfg.cleared_order_registry_sec) <= 0:
            return
        self._integrity._recent_cleared_orders.append((order_id, intent, self._clock()))

    def _lookup_recent_cleared_order(self, order_id: str) -> tuple[str, str] | None:
        self._prune_cleared_orders()
        for oid, intent, _ in self._integrity._recent_cleared_orders:
            if oid == order_id:
                return oid, intent
        return None

    def _check_position_reconcile(self) -> None:
        """Delegate to ``reconcile.check_position_reconcile`` (position domain)."""
        check_position_reconcile(self)

    def _timeout_loop(self):
        """Compat alias: one ``MaintenanceScheduler.run_once()`` (not a loop).

        Continuous background cadence requires ``self._maintenance.start()``
        (invoked from ``run()`` via ``_services``). Prefer calling
        ``self._maintenance.run_once()`` in new tests.
        """
        self._maintenance.run_once()

    def _clear_pending(self, *, watch_late_fill: bool = False):
        if watch_late_fill:
            self._record_cleared_pending()
        self._book.clear_flight()
        self._book.pending_ioc_slippage = int(self._cfg.ioc_slippage_points)
        self._integrity._exit_order_retry_count = 0
        self._integrity._exit_order_retry_at = 0.0
        # P0-5: clear SETTLING only. HALT (_position_unconfirmed) stays sticky.
        self._integrity.clear_settling_window()

    def run(self) -> None:
        """Broker-neutral blocking run loop (login + live wiring must be done first)."""
        self._running = True

        if self._cfg.tick_archive:
            self._archive.maybe_start_tick_archive(self.contract.code)
            logger.info(
                "Tick 落盤已啟用 | TICK_ARCHIVE=1 | code=%s",
                self.contract.code,
            )

        strategy = getattr(self._cfg, "strategy_name", "simple")
        logger.info(
            "策略已啟動 | strategy=%s | config=%s | 模擬=%s",
            strategy,
            self._cfg.config_path,
            self._cfg.simulation,
        )

        try:
            for svc in self._services:
                svc.start()
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("策略手動停止")
        finally:
            self._running = False
            for svc in reversed(self._services):
                try:
                    svc.stop()
                except Exception as e:
                    logger.warning("service stop 失敗: %s", e)
            if getattr(self._maintenance, "join_timed_out", False):
                logger.critical(
                    "維運執行緒 stop 逾時仍可能佔用 API — logout 可能與背景 job 競態"
                )
            self._archive.shutdown_tick_archive()
            if self._trading_date is not None:
                self._emit_daily_summary(self._trading_date)
            try:
                self._call_api(self.api.logout)
            except Exception as e:
                if is_api_session_error(e):
                    logger.warning("logout 略過（session 已失效）: %s", e)
                else:
                    logger.warning("logout 失敗: %s", e)
            shutdown_async_logging()

