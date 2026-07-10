from __future__ import annotations

import datetime
from trading_engine.core.types import OrderSignal
from trading_engine.orders.logutil import logger

class OrderFlattenMixin:
    def _maybe_kernel_force_flatten(
        self, ts: int, price: float, dt: datetime.datetime
    ) -> OrderSignal | None:
        """Kernel-owned force flatten at session_force_flatten_time.

        Strategy may return a custom OrderSignal via session_force_flatten_signal
        (for price/slippage/audit customization). If None, kernel synthesizes a
        standard full exit using flatten_slippage_points.
        """
        if self.position_qty <= 0:
            return None
        if self.is_pending or self.exit_pending:
            return None
        risk = self._risk_gate(ts, dt)
        if not risk.force_flatten:
            return None

        market = self._market_snapshot(ts, price, dt)
        position = self._position_snapshot()

        # Strategy hook for customization (price, slippage, reason, audit)
        windows = self._active_session_windows(dt)
        force_time = (
            windows[3] if windows is not None else self._cfg.session_force_flatten_time
        )
        custom, _effects = self.strategy.session_force_flatten_signal(
            market, position, force_time
        )
        if custom is not None:
            # Trust strategy provided signal but ensure intent/qty safety for first version
            if custom.intent != "exit":
                custom = None  # fallthrough to default
            else:
                return custom

        # Default kernel-produced exit (full position, using configured flatten slippage)
        action = "Sell" if self.position_dir == "Long" else "Buy"
        return OrderSignal(
            action=action,
            qty=self.position_qty,
            ref_price=price,
            intent="exit",
            exchange_ts=ts,
            slippage_points=self._cfg.flatten_slippage_points,
            # audit left to None for pure kernel forced exit
        )


    def _check_exit_order_retry(self) -> None:
        with self.lock:
            retry_at = self._exit_order_retry_at
            if retry_at <= 0 or self._clock() < retry_at:
                return
            self._exit_order_retry_at = 0.0

        signal = self._reconstruct_pending_signal()
        if signal is None:
            return
        logger.info("出場下單退避重試觸發")
        self._enqueue_order(signal)


    def _maybe_emergency_market_flatten(self) -> None:
        """P0-5: a stop-loss IOC missed → flatten the held position with a single
        kernel-owned MARKET order (guaranteed fill). Single-flight: never sends
        while any order is in flight; bypasses the entry/exit freeze via
        ``_kernel_converging`` because we KNOW we hold a position to kill."""
        signal = None
        with self.lock:
            if not self._stop_market_flatten_request:
                return
            if self.is_pending or self._settling:
                return  # single-flight; retry next loop once the slot is free
            if self.position_qty <= 0:
                self._stop_market_flatten_request = False
                return
            self._stop_market_flatten_request = False
            action = "Sell" if self.position_dir == "Long" else "Buy"
            qty = self.position_qty
            ref_price = self.last_tick_price or self.entry_price
            ts = int(self.last_tick_exchange_ts or self._last_tick_exchange_ts_or_zero())
            signal = OrderSignal(
                action=action,
                qty=qty,
                ref_price=ref_price,
                intent="exit",
                exchange_ts=ts,
                market=True,
            )
            self._kernel_converging = True
            try:
                if self._validate_order_signal(signal):
                    if not getattr(signal, "signal_id", ""):
                        signal.signal_id = self._make_signal_id(signal.exchange_ts or ts)
                    self._arm_pending(signal)
                else:
                    signal = None
            finally:
                self._kernel_converging = False
        if signal is not None:
            logger.warning(
                "停損市價平倉 | %s %d 口（kernel 主動，guaranteed fill）",
                signal.action,
                signal.qty,
            )
            self._enqueue_order(signal)


