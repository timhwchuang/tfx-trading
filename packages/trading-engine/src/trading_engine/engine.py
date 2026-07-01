from __future__ import annotations

import datetime
import queue
import threading
import time
from collections import deque
from collections.abc import Callable
from enum import Enum, auto
from typing import Any, NamedTuple

from trading_engine.api_errors import is_api_session_error
from trading_engine.calendar.port import MarketCalendarPort, TaifexMarketCalendar
from trading_engine.core.audit.signal_audit import SignalAudit
from trading_engine.core.ports import BrokerPort
from trading_engine.core.runtime_config import RuntimeConfig
from trading_engine.core.side_effect_ports import (
    AlertPort,
    ArchivePort,
    NullAlertPort,
    NullArchivePort,
    NullTelemetryPort,
    NullStructureRefreshPort,
    NullTrendRefreshPort,
    StructureRefreshPort,
    TelemetryPort,
    TrendRefreshPort,
)
from trading_engine.core.strategy import Strategy
from trading_engine.core.types import (
    EngineStateSnapshot,
    OrderSignal,
    PositionSnapshot,
    RiskGate,
    TickSnapshot,
)
from trading_engine.indicators import IndicatorState
from trading_engine.logging_setup import get_logger, shutdown_async_logging
from trading_engine.order_executor import OrderExecutorMixin
from trading_engine.session import SessionMixin

logger = get_logger()


class AtrRefreshResult(NamedTuple):
    ok: bool
    session_error: bool = False

    def __bool__(self) -> bool:
        return self.ok


class ReconnectOutcome(Enum):
    HEALTHY = auto()
    UNHEALTHY = auto()
    STALE = auto()


class TradingEngine(OrderExecutorMixin, SessionMixin):
    def __init__(
        self,
        api: BrokerPort,
        clock: Any = None,
        strategy: Strategy | None = None,
        runtime_config: RuntimeConfig | None = None,
        order_adapter: Any = None,
        telemetry: TelemetryPort | None = None,
        alerts: AlertPort | None = None,
        archive: ArchivePort | None = None,
        trend_refresh: TrendRefreshPort | None = None,
        structure_refresh: StructureRefreshPort | None = None,
        calendar: MarketCalendarPort | None = None,
    ):
        if runtime_config is None:
            raise TypeError("runtime_config is required; inject at app layer")
        if order_adapter is None:
            raise TypeError("order_adapter is required; inject at app layer")
        self._cfg = runtime_config
        self._telemetry = telemetry or NullTelemetryPort()
        self._alerts = alerts or NullAlertPort()
        self._archive = archive or NullArchivePort()
        self._trend_refresh = trend_refresh or NullTrendRefreshPort()
        self._structure_refresh = structure_refresh or NullStructureRefreshPort()
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

        # 持倉狀態（Phase 1: position_qty 為單一事實來源；has_position 為 derived property）
        self.position_qty = 0
        self.position_dir = "Flat"  # Long / Short / Flat
        self.entry_price = 0.0
        self.entry_exchange_ts = 0
        self.ticks_since_entry = 0
        self.trailing_peak = 0.0
        self.last_exit_time = 0
        self.daily_pnl = 0.0
        self.consecutive_loss = 0
        self.block_new_entry = False
        self._trading_date: datetime.date | None = None

        # 下單狀態
        self.is_pending = False
        self.pending_intent: str | None = None
        self.exit_pending = False
        self.pending_trade = None
        self.pending_order_id: str | None = None
        self.pending_since = 0.0  # system time; relative pending timeout only
        self.pending_exchange_ts = 0
        self.pending_qty = 0
        self.pending_signal_price = 0.0
        self.pending_limit_price = 0.0
        self.pending_exit_reason = ""
        self.pending_ioc_slippage = self._cfg.ioc_slippage_points
        self.pending_market = False  # P0-5: current pending is an emergency market order
        # P0-5: a stop-loss IOC missed → escalate to a kernel-owned market flatten.
        self._stop_market_flatten_request = False
        self.pending_episode_id: str = ""
        self.pending_signal_id: str = ""
        self._next_signal_seq: int = 0
        self._current_signal_date: str = ""
        self.filled_qty = 0  # P2-1: 累計部分成交；IOC 結束前不全解鎖；多口管理前置（Mock+單測）
        self._pending_exit_pnl = 0.0  # exit IOC 逐筆成交累積 PnL（FILL_AUDIT 用）
        self._resynced_position = False  # sync_positions 後待首 tick 校準 trailing_peak
        self._api_connected = True
        self._disconnect_since = 0.0
        self._disconnect_count_today = 0
        self._reconnect_warmup_until_ts = 0
        self._pending_reconnect_warmup = False
        self._atr_refresh_in_flight = False
        self._session_relogin_attempts = 0
        self._next_relogin_at = 0.0
        self._exit_order_retry_count = 0
        self._exit_order_retry_at = 0.0
        self._pending_action: str | None = None
        # Staged CRITICAL alert text produced under lock (e.g. orphan deal,
        # position drift); sent outside lock to avoid network I/O on hot path.
        self._staged_critical_alert: str | None = None
        # Set True once a broker/kernel position mismatch is detected; cleared on
        # a clean reconcile. Observability only.
        self._position_drift_detected = False
        self._last_reconcile_wall = 0.0
        # P0-5 (truth-driven execution) state machine extension.
        # _settling: pending timed out → outcome UNKNOWN → actively reconciling
        #   against the broker (no callback trust); new orders frozen.
        # _settle_since: wall-time the SETTLING window started.
        # _position_unconfirmed: broker truth not yet confirmed / mismatch / ceiling
        #   breach → HALT; kernel converges (single flatten) but strategy is frozen.
        # _reconcile_last_read / _reconcile_read_streak: debounce broker reads.
        # _converge_flatten_at: throttle for kernel convergence flatten.
        self._settling = False
        self._settle_since = 0.0
        self._position_unconfirmed = False
        self._reconcile_last_read: tuple[int, str] | None = None
        self._reconcile_read_streak = 0
        # Debounce severe-drift HALT in periodic reconcile (post-exit broker lag).
        self._severe_drift_broker_read: tuple[int, str] | None = None
        self._severe_drift_read_streak = 0
        self._converge_flatten_at = 0.0
        # P0-5: consecutive entry IOC misses (clean resume path); circuit breaker
        # trips to HALT when max_consecutive_missed_entries is exceeded.
        self._consecutive_missed_entries = 0
        # True only while the kernel arms its own convergence flatten (lets that
        # one order bypass the settling/unconfirmed freeze in _validate_order_signal).
        self._kernel_converging = False
        # Monotonic pending generation: bumped on every arm (audit / future guards).
        self._pending_generation = 0
        # Post-exit fast reconcile window (over-flatten detection).
        self._post_exit_reconcile_until = 0.0
        # Recently cleared pending orders for late-deal attribution.
        self._recent_cleared_orders: deque[tuple[str, str, float]] = deque(maxlen=64)

        self.indicators = IndicatorState(
            vwap_window_min=self._cfg.vwap_window_min,
            atr_period=self._cfg.atr_period,
        )
        self.strategy: Strategy = strategy

        self.lock = threading.Lock()
        self._api_lock = threading.RLock()  # 保護 Shioaji api 的 mutable 操作，避免 PyBorrowMutError
        self.contract = None
        self._running = False
        self._raw_order_evt_dumped: set = set()
        self.last_tick_exchange_ts = 0
        self._last_tick_wall_time = 0.0
        self._last_tick_exchange_dt: datetime.datetime | None = None
        self._tick_type_counts = {0: 0, 1: 0, 2: 0}
        self._tick_type_inferred_counts = {1: 0, 2: 0}
        self._last_tick_type_log_wall = 0.0
        self._last_clock_skew_warn_wall = 0.0
        self._last_no_tick_resubscribe_wall = 0.0
        self._no_tick_resubscribe_streak = 0
        self._reconnect_generation = 0
        self._connected_reconnect_generation = 0
        self._pending_intent_cancel_exchange_dt: datetime.datetime | None = None
        self._order_queue: queue.Queue[OrderSignal | None] = queue.Queue()
        self._order_sync_mode = False
        self._order_worker_started = False

    def _call_api(self, fn, *args, **kwargs):
        """Helper to serialize Shioaji mutable calls under _api_lock."""
        with self._api_lock:
            return fn(*args, **kwargs)

    @property
    def current_vwap(self) -> float:
        return self.indicators.current_vwap

    @current_vwap.setter
    def current_vwap(self, value: float) -> None:
        self.indicators.current_vwap = value

    @property
    def vol_1s(self) -> int:
        return self.indicators.vol_1s

    @vol_1s.setter
    def vol_1s(self, value: int) -> None:
        self.indicators.vol_1s = value

    @property
    def buy_vol_1s(self) -> int:
        return self.indicators.buy_vol_1s

    @property
    def sell_vol_1s(self) -> int:
        return self.indicators.sell_vol_1s

    @property
    def current_atr(self) -> float:
        return self.indicators.current_atr

    @current_atr.setter
    def current_atr(self, value: float) -> None:
        self.indicators.current_atr = value

    @property
    def last_atr_refresh(self) -> float:
        return self.indicators.last_atr_refresh

    @last_atr_refresh.setter
    def last_atr_refresh(self, value: float) -> None:
        self.indicators.last_atr_refresh = value

    @property
    def trend_dir(self) -> str:
        return self.indicators.trend_dir

    @trend_dir.setter
    def trend_dir(self, value: str) -> None:
        self.indicators.trend_dir = value

    @property
    def trend_strength(self) -> float:
        return self.indicators.trend_strength

    @property
    def has_position(self) -> bool:
        """Derived from position_qty (single source of truth for Phase 1+)."""
        return self.position_qty > 0

    def build_entry_audit(
        self, dt: datetime.datetime, price: float, ts: int, direction: str
    ) -> SignalAudit:
        vol_threshold = self._vol_threshold(dt)
        market = self.indicators.snapshot(ts, price, dt)
        base_vol, multiplier, threshold = vol_threshold
        return self.strategy.build_entry_audit(market, direction, multiplier, threshold)

    def build_exit_audit(
        self,
        price: float,
        ts: int,
        direction: str,
        reason: str,
        *,
        trail_points_used: float = 0.0,
        entry_price: float = 0.0,
        hold_ticks: int = 0,
        in_grace: bool = False,
        hard_stop_level: float = 0.0,
        vwap_stop_level: float = 0.0,
        trailing_peak: float = 0.0,
    ) -> SignalAudit:
        """Delegate to strategy. Extended signature for FT-001 exit audit enrichment.

        Note: Most call sites go directly through the strategy plugin's build_exit_audit.
        This wrapper exists for API symmetry and future kernel use.
        """
        dt = self._last_tick_exchange_dt or datetime.datetime.fromtimestamp(ts)
        market = self.indicators.snapshot(ts, price, dt)
        return self.strategy.build_exit_audit(
            market,
            direction,
            reason,
            trail_points_used=trail_points_used,
            entry_price=entry_price,
            hold_ticks=hold_ticks,
            in_grace=in_grace,
            hard_stop_level=hard_stop_level,
            vwap_stop_level=vwap_stop_level,
            trailing_peak=trailing_peak,
        )

    def _position_snapshot(self) -> PositionSnapshot:
        return PositionSnapshot(
            has_position=self.has_position,
            position_dir=self.position_dir,
            entry_price=self.entry_price,
            trailing_peak=self.trailing_peak,
            entry_exchange_ts=self.entry_exchange_ts,
            ticks_since_entry=self.ticks_since_entry,
            qty=self.position_qty,
        )

    def get_state_snapshot(self) -> EngineStateSnapshot:
        """Return a frozen read-only view of engine state.

        **Do not** assign to ``TradingEngine`` attributes (``position_qty``,
        ``is_pending``, etc.) from telemetry, strategy, or app code — that
        bypasses kernel invariants.
        """
        with self.lock:
            return EngineStateSnapshot(
                position_qty=self.position_qty,
                position_dir=self.position_dir,
                entry_price=self.entry_price,
                is_pending=self.is_pending,
                pending_intent=self.pending_intent,
                exit_pending=self.exit_pending,
                pending_qty=self.pending_qty,
                filled_qty=self.filled_qty,
                daily_pnl=self.daily_pnl,
                consecutive_loss=self.consecutive_loss,
                block_new_entry=self.block_new_entry,
                api_connected=self._api_connected,
                has_position=self.has_position,
                trailing_peak=self.trailing_peak,
                ticks_since_entry=self.ticks_since_entry,
                settling=self._settling,
                position_unconfirmed=self._position_unconfirmed,
            )

    def _is_atr_stale(self, ts: int) -> bool:
        success_ts = int(self.indicators.last_atr_refresh)
        if success_ts <= 0:
            return True
        stale_after = int(self._cfg.atr_refresh_sec * self._cfg.atr_stale_multiplier)
        return ts - success_ts > stale_after

    def _is_structure_stale(self, ts: int) -> bool:
        if not self._cfg.live_get(
            "STRUCTURE_FILTER_ENABLED", self._cfg.structure_filter_enabled
        ):
            return False
        success_ts = int(self.indicators.last_structure_refresh)
        if success_ts <= 0:
            return True
        stale_after = int(self._cfg.atr_refresh_sec * self._cfg.atr_stale_multiplier)
        return ts - success_ts > stale_after

    def _is_reconnect_warmup_active(self, ts: int) -> bool:
        return self._reconnect_warmup_until_ts > 0 and ts < self._reconnect_warmup_until_ts

    def _arm_reconnect_warmup_on_first_tick_locked(self, ts: int) -> None:
        if not self._pending_reconnect_warmup:
            return
        warmup_sec = self._cfg.reconnect_warmup_sec
        self._reconnect_warmup_until_ts = ts + warmup_sec
        self._pending_reconnect_warmup = False
        logger.info(
            "重連暖機開始 | %ds 內禁止新進場（until_ts=%d）",
            warmup_sec,
            self._reconnect_warmup_until_ts,
        )

    def _risk_gate(self, ts: int, dt: datetime.datetime) -> RiskGate:
        return RiskGate(
            api_connected=self._api_connected,
            is_pending=self.is_pending,
            exit_pending=self.exit_pending,
            cooldown_active=ts - self.last_exit_time < self._cfg.cooldown_sec,
            in_trading_session=self.is_trading_session(dt),
            block_new_entry=self.block_new_entry,
            consecutive_loss=self.consecutive_loss,
            daily_pnl=self.daily_pnl,
            after_flatten_time=self._calendar.is_at_or_after(dt, self._cfg.session_flatten_time),
            force_flatten=self._calendar.is_at_or_after(dt, self._cfg.session_force_flatten_time),
            atr_stale=self._is_atr_stale(ts),
            structure_stale=self._is_structure_stale(ts),
            reconnect_warmup_active=self._is_reconnect_warmup_active(ts),
            settling=self._settling,
            position_unconfirmed=self._position_unconfirmed,
        )

    def _parse_tick_locked(self, tick: Any) -> tuple[int, float, int, int, int]:
        """Parse tick inside lock; infer buy/sell from price when type0."""
        ts = int(tick.datetime.timestamp())
        price = float(tick.close)
        volume = int(tick.volume)
        original_tick_type = int(getattr(tick, "tick_type", 0) or 0)
        tick_type = original_tick_type

        if tick_type == 0 and self.indicators.last_tick_price > 0:
            if price > self.indicators.last_tick_price:
                tick_type = 1
            elif price < self.indicators.last_tick_price:
                tick_type = 2

        self.indicators.last_tick_price = price
        if original_tick_type == 0 and tick_type in (1, 2):
            self._tick_type_inferred_counts[tick_type] = (
                self._tick_type_inferred_counts.get(tick_type, 0) + 1
            )
            self._telemetry.record_tick_type(original_tick_type, tick_type)
        return ts, price, volume, tick_type, original_tick_type

    def on_tick(self, tick: Any):
        """Accept either native broker tick (e.g. Shioaji TickFOPv1 via live adapter)
        or a TickSnapshot (preferred internal normalized form for decoupling).
        """
        signal: OrderSignal | None = None
        ts = 0
        price = 0.0
        volume = 0
        tick_type = 0
        original_tick_type = 0
        exchange_dt = None
        lock_wait_start = time.perf_counter()
        with self.lock:
            self._telemetry.record_lock_wait((time.perf_counter() - lock_wait_start) * 1000)

            if isinstance(tick, TickSnapshot):
                ts = tick.ts
                price = tick.price
                volume = tick.volume
                tick_type = tick.tick_type
                original_tick_type = tick_type  # already normalized by adapter
                exchange_dt = tick.exchange_dt
                self.indicators.last_tick_price = price  # minimal side effect for inference path
            else:
                ts, price, volume, tick_type, original_tick_type = self._parse_tick_locked(tick)
                exchange_dt = getattr(tick, "datetime", None) or (
                    self._last_tick_exchange_dt or datetime.datetime.fromtimestamp(ts)
                )

            self._record_tick_arrival_locked(ts, exchange_dt, tick_type)
            self._arm_reconnect_warmup_on_first_tick_locked(ts)
            self._telemetry.record_atr(self.indicators.current_atr)
            self._maybe_refresh_atr(ts)
            self.indicators.update_vwap(ts, price, volume)
            self.indicators.update_momentum(ts, volume, tick_type)
            if self.has_position:
                self.ticks_since_entry += 1
                if self._resynced_position:
                    self._calibrate_trailing_peak_after_resync(price)
                self._update_trailing_peak(price)

            # Kernel force-flatten (owned by host for hard session boundary safety).
            # Runs before normal strategy decision so force exit has priority.
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
                        self._pending_intent_cancel_exchange_dt = dt_for_risk
                        self._telemetry.record_entry_signal()
                    elif signal.intent == "exit":
                        # P1-1: kernel owns exit sizing — always flatten the full
                        # held position regardless of what the strategy requested
                        # (strategy may default to 1 lot). Prevents leaving a
                        # residual broker position unmanaged after a stop/exit.
                        if self.position_qty > 0:
                            signal.qty = self.position_qty
                        self._telemetry.record_exit_signal()
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

    def _maybe_refresh_atr(self, ts: int):
        if self._atr_refresh_in_flight:
            return
        last_success = int(self.indicators.last_atr_refresh)
        last_attempt = int(self.indicators.last_atr_refresh_attempt)
        retry_interval = (
            min(30, self._cfg.atr_refresh_sec)
            if last_success <= 0
            else self._cfg.atr_refresh_sec
        )
        if last_attempt > 0 and ts - last_attempt < retry_interval:
            return
        if last_success > 0 and ts - last_success < self._cfg.atr_refresh_sec:
            return
        self.indicators.last_atr_refresh_attempt = float(ts)
        self._atr_refresh_in_flight = True
        threading.Thread(target=self.refresh_atr, daemon=True).start()

    def _today(self) -> datetime.date:
        """交易所「今天」：有 tick 時以 tick 日期為準（回測確定性），否則用系統日期。"""
        if self._last_tick_exchange_dt is not None:
            return self._last_tick_exchange_dt.date()
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

    def refresh_atr(self) -> AtrRefreshResult:
        try:
            today = self._today()
            with self.lock:
                current_atr = self.indicators.current_atr
                long_done = self.indicators._atr_long_lookback_date
            start, used_long = self._atr_kline_start(
                today,
                current_atr=current_atr,
                long_lookback_days=self._cfg.atr_kline_lookback_days,
                long_lookback_done_for=long_done,
            )
            kbars = self._call_api(
                self.api.kbars,
                contract=self.contract,
                start=start.isoformat(),
                end=today.isoformat(),
            )
            atr = IndicatorState.compute_atr(kbars, atr_period=self._cfg.atr_period)
            # live_get reads sweep-patched config module attributes at runtime.
            _live_trend_enabled = self._cfg.live_get(
                "TREND_FILTER_ENABLED", self._cfg.trend_filter_enabled
            )
            if _live_trend_enabled:
                trend_dir, trend_strength = self._trend_refresh.refresh_trend(
                    kbars,
                    exchange_dt=self._last_tick_exchange_dt,
                    used_long_lookback=used_long,
                    atr=atr,
                    cfg=self._cfg,
                )
            else:
                with self.lock:
                    trend_dir = self.indicators.trend_dir
                    trend_strength = self.indicators.trend_strength
            _live_structure_enabled = self._cfg.live_get(
                "STRUCTURE_FILTER_ENABLED", self._cfg.structure_filter_enabled
            )
            if _live_structure_enabled:
                structure_state = self._structure_refresh.refresh_structure(
                    kbars,
                    exchange_dt=self._last_tick_exchange_dt,
                    used_long_lookback=used_long,
                    atr=atr,
                    cfg=self._cfg,
                )
            else:
                structure_state = None
            refresh_ts = float(self.last_tick_exchange_ts or 0)
            with self.lock:
                self.indicators.current_atr = atr
                self.indicators.trend_dir = trend_dir
                self.indicators.trend_strength = trend_strength
                if structure_state is not None:
                    self.indicators.structure_bias = str(
                        getattr(structure_state, "bias", "Neutral")
                    )
                    self.indicators.structure_strength = float(
                        getattr(structure_state, "strength", 0.0)
                    )
                    self.indicators.structure_in_discount = bool(
                        getattr(structure_state, "in_discount", False)
                    )
                    self.indicators.structure_in_premium = bool(
                        getattr(structure_state, "in_premium", False)
                    )
                    self.indicators.structure_fvg_low = getattr(
                        structure_state, "active_fvg_low", None
                    )
                    self.indicators.structure_fvg_high = getattr(
                        structure_state, "active_fvg_high", None
                    )
                    self.indicators.structure_sweep_reclaim = bool(
                        getattr(structure_state, "sweep_reclaim", False)
                    )
                    if refresh_ts > 0:
                        self.indicators.last_structure_refresh = refresh_ts
                if refresh_ts > 0:
                    self.indicators.last_atr_refresh = refresh_ts
                if used_long:
                    self.indicators._atr_long_lookback_date = today
            lookback_label = f"{self._cfg.atr_kline_lookback_days}d" if used_long else "當日"
            logger.info(
                "ATR(%d) 更新: %.2f | start=%s lookback=%s",
                self._cfg.atr_period,
                atr,
                start.isoformat(),
                lookback_label,
            )
            self._log_api_usage("atr_refresh")
            if self._cfg.kbars_archive:
                try:
                    self._archive.archive_kbars(
                        kbars,
                        product_code=self.contract.code,
                        trade_date=today,
                    )
                except Exception as arch_err:
                    logger.warning("Kbars 落盤失敗: %s", arch_err)
            return AtrRefreshResult(True)
        except Exception as e:
            session_err = is_api_session_error(e)
            logger.warning("ATR 更新失敗: %s", e)
            return AtrRefreshResult(False, session_err)
        finally:
            self._atr_refresh_in_flight = False

    def _vol_threshold(self, dt: datetime.datetime) -> tuple[float, float, float]:
        """P1-2: (base_vol, multiplier, vol_threshold)."""
        return self._calendar.compute_vol_threshold(
            self.indicators.current_atr,
            dt,
            base_vol=self._cfg.base_vol,
            atr_vol_mult=self._cfg.atr_vol_mult,
            mult_futures=self._cfg.open_mult_futures,
            mult_spot=self._cfg.open_mult_spot,
            mult_normal=self._cfg.open_mult_normal,
        )

    def _calibrate_trailing_peak_after_resync(self, price: float) -> None:
        """P0-3: 重啟對帳後首 tick，保守初始化 trailing_peak。"""
        old_peak = self.trailing_peak
        if self.position_dir == "Long":
            self.trailing_peak = max(self.entry_price, price)
        elif self.position_dir == "Short":
            self.trailing_peak = min(self.entry_price, price)
        self._resynced_position = False
        logger.info(
            "持倉 peak 校準 | %s entry=%.1f tick=%.1f peak %.1f→%.1f",
            self.position_dir,
            self.entry_price,
            price,
            old_peak,
            self.trailing_peak,
        )

    def _record_tick_arrival_locked(
        self, ts: int, exchange_dt: datetime.datetime, tick_type: int
    ) -> None:
        """Must be called with self.lock held."""
        self.last_tick_exchange_ts = ts
        self._last_tick_wall_time = self._clock()
        self._last_tick_exchange_dt = exchange_dt
        bucket = tick_type if tick_type in self._tick_type_counts else 0
        self._tick_type_counts[bucket] = self._tick_type_counts.get(bucket, 0) + 1
        self._no_tick_resubscribe_streak = 0
        self._maybe_warn_clock_skew(ts)

    def _record_tick_arrival(self, ts: int, exchange_dt: datetime.datetime, tick_type: int) -> None:
        self.last_tick_exchange_ts = ts
        self._last_tick_wall_time = self._clock()
        self._last_tick_exchange_dt = exchange_dt
        bucket = tick_type if tick_type in self._tick_type_counts else 0
        self._tick_type_counts[bucket] = self._tick_type_counts.get(bucket, 0) + 1
        self._no_tick_resubscribe_streak = 0
        self._maybe_warn_clock_skew(ts)

    def _maybe_warn_clock_skew(self, exchange_ts: int) -> None:
        skew = abs(exchange_ts - self._clock())
        if skew <= self._cfg.clock_skew_warn_sec:
            return
        now = self._clock()
        if now - self._last_clock_skew_warn_wall < 300:
            return
        self._last_clock_skew_warn_wall = now
        logger.warning(
            "系統鐘與交易所時間偏差 %.1fs | 策略決策仍以 tick 時間為準",
            skew,
        )

    def _maybe_log_tick_type_summary(self) -> None:
        """P1-3: 每 30 分鐘輸出 tick_type 分布（UAT 觀測）。"""
        if self._last_tick_exchange_dt is None:
            return
        if not self._calendar.is_trading_session(
            self._last_tick_exchange_dt,
            self._cfg.session_start,
            self._cfg.session_end,
        ):
            return
        now = self._clock()
        if now - self._last_tick_type_log_wall < 1800:
            return
        total = sum(self._tick_type_counts.values())
        if total == 0:
            return
        self._last_tick_type_log_wall = now
        inferred_total = sum(self._tick_type_inferred_counts.values())
        logger.info(
            "tick_type 分布 | type0=%d type1=%d type2=%d total=%d "
            "| type0_pct=%.1f%% | inferred_buy=%d inferred_sell=%d inferred_total=%d",
            self._tick_type_counts.get(0, 0),
            self._tick_type_counts.get(1, 0),
            self._tick_type_counts.get(2, 0),
            total,
            100.0 * self._tick_type_counts.get(0, 0) / total,
            self._tick_type_inferred_counts.get(1, 0),
            self._tick_type_inferred_counts.get(2, 0),
            inferred_total,
        )

    def _check_no_tick_watchdog(self) -> None:
        """P4-8: 交易時段內長時間無 tick → 告警並嘗試重訂閱。"""
        if not self._api_connected or self.contract is None:
            return
        if self._last_tick_exchange_dt is None or self._last_tick_wall_time <= 0:
            return
        if not self._calendar.is_trading_session(
            self._last_tick_exchange_dt,
            self._cfg.session_start,
            self._cfg.session_end,
        ):
            return
        silent = self._clock() - self._last_tick_wall_time
        if silent < self._cfg.no_tick_timeout_sec:
            return
        now = self._clock()
        if now - self._last_no_tick_resubscribe_wall < 60:
            return
        self._last_no_tick_resubscribe_wall = now
        self._telemetry.record_no_tick_resubscribe()
        self._no_tick_resubscribe_streak += 1
        escalate_after = self._cfg.no_tick_resubscribe_escalate_after
        logger.warning(
            "No-tick 看門狗 | %.0fs 無 tick，嘗試重訂閱 %s（streak=%d/%d）",
            silent,
            self.contract.code,
            self._no_tick_resubscribe_streak,
            escalate_after,
        )
        try:
            if self._resubscribe_ticks is None:
                logger.warning("No-tick 看門狗 | 未設定 tick 重訂閱 hook，略過")
                return
            self._resubscribe_ticks()
            logger.info("No-tick 看門狗 | 重訂閱已送出")
        except Exception as e:
            logger.warning("No-tick 看門狗 | 重訂閱失敗: %s", e)
            self._no_tick_resubscribe_streak = 0
            self._mark_disconnected()
            return

        with self.lock:
            if not self._api_connected:
                return
            if self._no_tick_resubscribe_streak < escalate_after:
                return
            silent_after = self._clock() - self._last_tick_wall_time
            if silent_after < self._cfg.no_tick_timeout_sec:
                return
            streak = self._no_tick_resubscribe_streak
            self._no_tick_resubscribe_streak = 0
            connected_gen = self._connected_reconnect_generation

        if not self._mark_disconnected(
            require_silent_sec=self._cfg.no_tick_timeout_sec,
            max_connected_reconnect_generation=connected_gen,
            require_was_connected=True,
        ):
            logger.info("No-tick 升級已取消：tick 或 reconnect 已恢復")
            return

        self._telemetry.record_no_tick_escalation()
        msg = (
            f"No-tick 看門狗 | 連續 {streak} 次重訂閱仍無 tick → "
            "升級 session relogin"
        )
        logger.warning(msg)
        self._alerts.send(msg, level="CRITICAL")

    @staticmethod
    def _is_severe_drift(
        kernel_qty: int,
        kernel_dir: str,
        broker_qty: int,
        broker_dir: str,
    ) -> bool:
        """Over-flatten or direction reversal — must HALT, not strategy retry."""
        if kernel_qty == 0 and broker_qty > 0:
            return True
        if (
            kernel_qty > 0
            and broker_qty > 0
            and kernel_dir not in ("Flat", "")
            and broker_dir not in ("Flat", "")
            and kernel_dir != broker_dir
        ):
            return True
        return False

    def _severe_drift_confirmed(
        self,
        kernel_qty: int,
        kernel_dir: str,
        broker_qty: int,
        broker_dir: str,
    ) -> bool:
        """True once severe drift is seen on debounced consecutive broker reads."""
        if not self._is_severe_drift(
            kernel_qty, kernel_dir, broker_qty, broker_dir
        ):
            with self.lock:
                self._severe_drift_broker_read = None
                self._severe_drift_read_streak = 0
            return False
        broker = (broker_qty, broker_dir)
        need = max(1, int(self._cfg.reconcile_confirm_reads))
        with self.lock:
            if self._severe_drift_broker_read == broker:
                self._severe_drift_read_streak += 1
            else:
                self._severe_drift_broker_read = broker
                self._severe_drift_read_streak = 1
            return self._severe_drift_read_streak >= need

    def _prune_cleared_orders(self) -> None:
        ttl = int(self._cfg.cleared_order_registry_sec)
        if ttl <= 0:
            return
        now = self._clock()
        while self._recent_cleared_orders and now - self._recent_cleared_orders[0][2] > ttl:
            self._recent_cleared_orders.popleft()

    def _record_cleared_pending(self) -> None:
        """Caller holds lock."""
        order_id = self.pending_order_id
        intent = self.pending_intent
        if not order_id or not intent:
            return
        if int(self._cfg.cleared_order_registry_sec) <= 0:
            return
        self._recent_cleared_orders.append((order_id, intent, self._clock()))

    def _lookup_recent_cleared_order(self, order_id: str) -> tuple[str, str] | None:
        self._prune_cleared_orders()
        for oid, intent, _ in self._recent_cleared_orders:
            if oid == order_id:
                return oid, intent
        return None

    def _check_position_reconcile(self) -> None:
        """P0-3: periodically reconcile kernel position with the broker.

        Background safety net for lost order/fill callbacks: if the broker shows
        a different position than the kernel believes, adopt the broker truth,
        block new entries, and raise a CRITICAL alert. Exchange-time gated.

        P0-5: cadence is ``reconcile_fast_sec`` whenever the position is
        unconfirmed (HALT) so the kernel re-checks the broker quickly; otherwise
        the steady ``position_reconcile_sec``. Skipped while an order is in flight
        (pending) or settling — those windows are owned by ``_settle_via_reconcile``
        / ``_maybe_converge_flatten`` at the fast (1s) loop cadence, so the root
        cause "had a pending → never reconciled" no longer applies.
        """
        steady = self._cfg.position_reconcile_sec
        if steady <= 0:
            return
        if not self._api_connected or self.contract is None:
            return
        if self._last_tick_exchange_dt is None:
            return
        if not self._calendar.is_trading_session(
            self._last_tick_exchange_dt,
            self._cfg.session_start,
            self._cfg.session_end,
        ):
            return

        with self.lock:
            if self.is_pending or self._settling:
                return
            kernel_qty = self.position_qty
            kernel_dir = self.position_dir
            unconfirmed = self._position_unconfirmed
            post_exit = self._clock() < self._post_exit_reconcile_until

        interval = (
            max(1, int(self._cfg.reconcile_fast_sec))
            if (unconfirmed or post_exit)
            else steady
        )
        now = self._clock()
        if now - self._last_reconcile_wall < interval:
            return

        broker = self.read_broker_position()
        if broker is None:
            return  # failed read; throttle not consumed — retry next cycle
        broker_qty, broker_dir = broker

        # Only consume the throttle after a successful broker read and comparison.
        self._last_reconcile_wall = now

        ceiling = self._cfg.max_position_qty
        if ceiling > 0 and broker_qty > ceiling and broker_qty > kernel_qty:
            # P0-5 hard backstop: broker holds more than the kernel believed and
            # over the ceiling → HALT + converge flatten (catches the >1-lot
            # accumulation even if every other guard somehow missed it).
            self._position_drift_detected = True
            self._halt_position_unconfirmed(
                f"週期對帳發現超過部位上限 | kernel={kernel_dir} {kernel_qty}口 "
                f"broker={broker_dir} {broker_qty}口 > max={ceiling}"
            )
            return

        if self._is_severe_drift(kernel_qty, kernel_dir, broker_qty, broker_dir):
            if not self._severe_drift_confirmed(
                kernel_qty, kernel_dir, broker_qty, broker_dir
            ):
                return
            self._position_drift_detected = True
            logger.warning(
                "嚴重持倉漂移 | kernel=%s %d口 broker=%s %d口 → HALT 並收斂平倉",
                kernel_dir,
                kernel_qty,
                broker_dir,
                broker_qty,
            )
            with self.lock:
                self._severe_drift_broker_read = None
                self._severe_drift_read_streak = 0
            self._halt_position_unconfirmed(
                f"週期對帳嚴重漂移 | kernel={kernel_dir} {kernel_qty}口 "
                f"broker={broker_dir} {broker_qty}口",
                clear_pending=False,
            )
            self.sync_positions()
            self._alerts.send(
                f"嚴重持倉漂移 | kernel={kernel_dir} {kernel_qty}口 vs "
                f"broker={broker_dir} {broker_qty}口 → 已 HALT 並收斂平倉；請人工核對",
                level="CRITICAL",
            )
            return

        if broker_qty == kernel_qty and broker_dir == kernel_dir:
            if self._position_drift_detected:
                logger.info(
                    "週期對帳 | 已恢復一致 | %s %d口", kernel_dir, kernel_qty
                )
            self._position_drift_detected = False
            with self.lock:
                self._severe_drift_broker_read = None
                self._severe_drift_read_streak = 0
            return

        logger.warning(
            "持倉漂移偵測 | kernel=%s %d口 broker=%s %d口 → 以券商為準並停止新進場",
            kernel_dir,
            kernel_qty,
            broker_dir,
            broker_qty,
        )
        self._position_drift_detected = True
        with self.lock:
            self.block_new_entry = True
        # Adopt broker truth via the canonical write path.
        self.sync_positions()
        self._alerts.send(
            f"持倉漂移 | kernel={kernel_dir} {kernel_qty}口 vs broker={broker_dir} "
            f"{broker_qty}口 → 已以券商為準並停止新進場；請人工核對",
            level="CRITICAL",
        )

    def _timeout_loop(self):
        while self._running:
            try:
                self._check_pending_timeout()
                self._settle_via_reconcile()
                self._maybe_converge_flatten()
                self._maybe_emergency_market_flatten()
                self._check_exit_order_retry()
                self._check_session_watchdog()
                self._check_no_tick_watchdog()
                self._check_position_reconcile()
                self._reconcile_recent_cleared_deals()
                self._maybe_log_tick_type_summary()
            except BaseException as e:
                # Catch PanicException etc. from PyO3 to prevent silent thread death.
                # Log and continue (thread may be compromised; monitor will notice).
                logger.error("背景維運檢查嚴重異常 (可能殺死 thread): %s", e)
            time.sleep(1)

    def _check_session_watchdog(self) -> None:
        with self.lock:
            if self._api_connected:
                return
            disconnected_since = self._disconnect_since
            next_at = self._next_relogin_at
            attempts = self._session_relogin_attempts

        if disconnected_since <= 0:
            return
        now = self._clock()
        if now < next_at:
            return
        if now - disconnected_since < self._cfg.session_watchdog_sec:
            return
        if attempts >= self._cfg.session_relogin_max_attempts:
            self._alerts.send(
                f"Session 重登入已達上限 {self._cfg.session_relogin_max_attempts}",
                level="CRITICAL",
            )
            with self.lock:
                self._next_relogin_at = now + 300.0
            return

        try:
            logger.warning(
                "Session 看門狗觸發重登入 | attempt=%d",
                attempts + 1,
            )
            self._call_api(
                self.api.login,
                api_key=self._cfg.api_key,
                secret_key=self._cfg.secret_key,
                subscribe_trade=True,
            )
            with self.lock:
                if self._api_connected:
                    logger.info(
                        "Session 看門狗略過 _on_reconnected：已由其他路徑恢復連線"
                    )
                    return
            outcome = self._on_reconnected()
            if outcome == ReconnectOutcome.UNHEALTHY:
                backoff = self._cfg.session_relogin_backoff_base_sec * (2**attempts)
                logger.error(
                    "Session 重登入後健康檢查失敗 | backoff=%.1fs", backoff
                )
                self._alerts.send(
                    "Session 重登入後健康檢查失敗（subscribe/ATR）",
                    level="CRITICAL",
                )
                with self.lock:
                    self._session_relogin_attempts = attempts + 1
                    self._next_relogin_at = now + backoff
            elif outcome == ReconnectOutcome.STALE:
                backoff = self._cfg.session_relogin_backoff_base_sec
                logger.info(
                    "Session 重登入被較新的 reconnect 取代，短暫 backoff %.1fs",
                    backoff,
                )
                with self.lock:
                    self._next_relogin_at = now + backoff
        except Exception as e:
            backoff = self._cfg.session_relogin_backoff_base_sec * (2**attempts)
            logger.error("Session 重登入失敗: %s | backoff=%.1fs", e, backoff)
            self._alerts.send(f"Session 重登入失敗: {e}", level="CRITICAL")
            with self.lock:
                self._session_relogin_attempts = attempts + 1
                self._next_relogin_at = now + backoff

    def _mark_disconnected(
        self,
        *,
        reconnect_generation: int | None = None,
        require_silent_sec: float | None = None,
        max_connected_reconnect_generation: int | None = None,
        require_was_connected: bool = False,
    ) -> bool:
        """Mark API disconnected. Returns False when superseded or preconditions fail."""
        alert_qty = 0
        alert_dir = "Flat"
        with self.lock:
            if require_silent_sec is not None and self._last_tick_wall_time > 0:
                if self._clock() - self._last_tick_wall_time < require_silent_sec:
                    return False
            if (
                max_connected_reconnect_generation is not None
                and self._connected_reconnect_generation
                > max_connected_reconnect_generation
            ):
                return False
            if (
                reconnect_generation is not None
                and reconnect_generation != self._reconnect_generation
            ):
                return False
            if (
                reconnect_generation is not None
                and self._api_connected
                and reconnect_generation != self._connected_reconnect_generation
            ):
                return False
            was_connected = self._api_connected
            self._api_connected = False
            if reconnect_generation is None:
                self._connected_reconnect_generation = 0
            if self._disconnect_since <= 0:
                self._disconnect_since = self._clock()
            if was_connected:
                self._disconnect_count_today += 1
                alert_qty = self.position_qty
                alert_dir = self.position_dir
                disconnect_count = self._disconnect_count_today
            else:
                disconnect_count = self._disconnect_count_today
        if not was_connected:
            if require_was_connected:
                return False
            return True
        if (
            alert_qty > 0
            and self._cfg.alert_on_disconnect_with_position
        ):
            self._alerts.send(
                f"API 斷線且有持倉 | dir={alert_dir} qty={alert_qty} | "
                f"第 {disconnect_count} 次斷線（今日）",
                level="CRITICAL",
            )
        if disconnect_count >= self._cfg.max_disconnects_per_day:
            with self.lock:
                self.block_new_entry = True
            self._alerts.send(
                f"單日斷線達 {disconnect_count} 次（上限 "
                f"{self._cfg.max_disconnects_per_day}）→ 停止新進場至日切換；請排查網路",
                level="CRITICAL",
            )
        return True

    def _clear_pending(self, *, watch_late_fill: bool = False):
        if watch_late_fill:
            self._record_cleared_pending()
        self.is_pending = False
        self.pending_intent = None
        self.exit_pending = False
        self.pending_trade = None
        self.pending_order_id = None
        self.pending_since = 0.0
        self.pending_exchange_ts = 0
        self.pending_qty = 0
        self.pending_signal_price = 0.0
        self.pending_limit_price = 0.0
        self.pending_exit_reason = ""
        self.pending_ioc_slippage = self._cfg.ioc_slippage_points
        self.pending_market = False
        self.pending_episode_id = ""
        self.pending_signal_id = ""
        self.filled_qty = 0
        self._pending_exit_pnl = 0.0
        self._pending_action = None
        self._exit_order_retry_count = 0
        self._exit_order_retry_at = 0.0
        # P0-5: clearing pending also exits the SETTLING window. ``_position_unconfirmed``
        # (HALT) is intentionally NOT reset here — it is a sticky safety flag lifted
        # only by a clean confirmed reconcile or daily reset, never by clearing pending.
        self._settling = False
        self._settle_since = 0.0
        self._reconcile_last_read = None
        self._reconcile_read_streak = 0

    def handle_session_event(self, resp_code: int, event_code: int, info: str, event: str):
        if event_code == 12:
            logger.warning("API 重連中 | resp=%s info=%s", resp_code, info)
            self._mark_disconnected()
        elif event_code == 13:
            logger.info("API 重連成功 | resp=%s", resp_code)
            threading.Thread(
                target=self._on_reconnected, daemon=True, name="reconnect-sync"
            ).start()

    def handle_session_down(self):
        logger.warning("API 連線中斷")
        self._mark_disconnected()

    def _on_reconnected(self) -> ReconnectOutcome:
        """P4-1: 先補查 pending，再對帳持倉，最後重新訂閱。

        Returns HEALTHY when subscribe/ATR health gate passed and connected state applied.
        """
        with self.lock:
            self._reconnect_generation += 1
            generation = self._reconnect_generation
            has_pending = self.is_pending

        if has_pending:
            try:
                self._reconcile_pending_trade()
            except Exception as e:
                logger.warning("重連後 pending 補查失敗: %s", e)

        self.sync_positions()

        session_healthy = True
        try:
            if self._resubscribe_ticks is not None:
                self._resubscribe_ticks()
        except Exception as e:
            logger.warning("重連後 subscribe 失敗: %s", e)
            session_healthy = False

        # P0-1: re-attach order/deal report channel. A reconnect that restores
        # only quote ticks (above) but not the trade channel leaves order/fill
        # callbacks dead -> broker fills silently while kernel keeps timing out.
        try:
            if self._resubscribe_trade is not None:
                self._resubscribe_trade()
        except Exception as e:
            logger.warning("重連後委託回報通道重掛失敗: %s", e)
            session_healthy = False

        atr = self.refresh_atr()
        if not atr.ok and atr.session_error:
            session_healthy = False

        with self.lock:
            if generation != self._reconnect_generation:
                logger.info(
                    "重連同步結果已過期，忽略 | gen=%d current=%d healthy=%s",
                    generation,
                    self._reconnect_generation,
                    session_healthy,
                )
                return ReconnectOutcome.STALE
            if session_healthy:
                self._pending_reconnect_warmup = True
                self._reconnect_warmup_until_ts = 0
                self._api_connected = True
                self._connected_reconnect_generation = generation
                self._disconnect_since = 0.0
                self._session_relogin_attempts = 0
                self._next_relogin_at = 0.0
                self._no_tick_resubscribe_streak = 0

        if session_healthy:
            logger.info("重連後狀態同步完成（暖機待首筆 tick 起算）")
            return ReconnectOutcome.HEALTHY

        logger.warning(
            "重連後 session 不健康，降級為 disconnected，交由 Session 看門狗重登入"
        )
        if not self._mark_disconnected(reconnect_generation=generation):
            logger.info(
                "重連不健康結果已過期，略過 disconnect | gen=%d current=%d",
                generation,
                self._reconnect_generation,
            )
            return ReconnectOutcome.STALE
        return ReconnectOutcome.UNHEALTHY

    def run(self) -> None:
        """Broker-neutral blocking run loop (login + live wiring must be done first)."""
        self._running = True

        if self._cfg.tick_archive:
            self._archive.maybe_start_tick_archive(self.contract.code)
            logger.info(
                "Tick 落盤已啟用 | TICK_ARCHIVE=1 | code=%s",
                self.contract.code,
            )

        logger.info(
            "VWAP Momentum 策略已啟動 | config=%s | ATR=%.2f | 模擬=%s",
            self._cfg.config_path,
            self.current_atr,
            self._cfg.simulation,
        )

        threading.Thread(target=self._timeout_loop, daemon=True).start()
        self._start_order_worker()

        try:
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("策略手動停止")
        finally:
            self._running = False
            if not self._order_sync_mode:
                self._order_queue.put_nowait(None)
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

    def start(self) -> None:
        """Live Shioaji convenience entry (delegates to ShioajiLiveBootstrap)."""
        from trading_engine.adapters.shioaji_live import ShioajiLiveBootstrap

        ShioajiLiveBootstrap(self).start_live()
