from __future__ import annotations

import threading
from trading_engine.core.audit.exec_audit import ExecAudit, format_exec_audit
from trading_engine.core.types import OrderSignal
from trading_engine.order_errors import OrderErrorCategory, classify_order_error, should_retry_order
from trading_engine.orders.logutil import logger

class OrderPlaceMixin:
    def place_order(self, signal: OrderSignal):
        action = signal.action
        qty = signal.qty
        ref_price = signal.ref_price

        try:
            is_market = bool(getattr(signal, "market", False))
            account = self._call_api(lambda: self.api.futopt_account)
            if is_market:
                price = 0.0
                trade = self._call_api(
                    self._order_adapter.place_market,
                    self.contract,
                    action=action,
                    qty=qty,
                    account=account,
                )
            else:
                slip = (
                    signal.slippage_points
                    if signal.slippage_points is not None
                    else self._cfg.ioc_slippage_points
                )
                price = ref_price + slip if action == "Buy" else ref_price - slip
                trade = self._call_api(
                    self._order_adapter.place_ioc_limit,
                    self.contract,
                    action=action,
                    qty=qty,
                    limit_price=price,
                    account=account,
                )
            oid = str(getattr(trade.order, "id", "") or "")
            with self.lock:
                self.pending_trade = trade
                self.pending_order_id = oid
                self.pending_since = self._clock()
                self._exit_order_retry_count = 0
                self._exit_order_retry_at = 0.0

                # Phase 2: Emit pending_armed only when order_id is known (SPEC §5.3 MUST).
                # If oid empty at place time, defer to first callback backfill (avoids duplicate armed).
                if self.pending_order_id:
                    try:
                        exec_audit = ExecAudit(
                            event_type="pending_armed",
                            ts=signal.exchange_ts or 0,
                            signal_id=signal.signal_id or self.pending_signal_id,
                            order_id=self.pending_order_id,
                            limit_price=self.pending_limit_price,
                            direction=signal.action,
                        )
                        logger.info("EXEC_AUDIT %s", format_exec_audit(exec_audit))
                    except Exception:
                        pass  # never break hot path

            logger.info(
                "下單 %s %d 口 @ %s (%s%s) | trade=%s",
                action,
                qty,
                "市價" if is_market else f"{price:.1f}",
                signal.intent,
                "/MKT" if is_market else "",
                oid,
            )
        except Exception as e:
            self._handle_place_order_failure(signal, e)


    def _handle_place_order_failure(self, signal: OrderSignal, exc: Exception) -> None:
        category = classify_order_error(exc)
        intent = signal.intent
        logger.error(
            "下單失敗 | intent=%s category=%s err=%s",
            intent,
            category.value,
            exc,
        )

        if intent == "entry":
            with self.lock:
                self._clear_pending()
            if category == OrderErrorCategory.FATAL:
                self._alerts.send(f"進場下單致命錯誤: {exc}", level="CRITICAL")
            return

        with self.lock:
            attempt = self._exit_order_retry_count

        if should_retry_order(
            intent=intent,
            category=category,
            attempt=attempt,
            max_retries=self._cfg.exit_order_max_retries,
        ):
            with self.lock:
                self._exit_order_retry_count = attempt + 1
                self._exit_order_retry_at = self._clock() + self._cfg.exit_order_retry_delay_sec
            logger.warning(
                "出場下單將退避重試 | attempt=%d/%d delay=%.1fs",
                attempt + 1,
                self._cfg.exit_order_max_retries,
                self._cfg.exit_order_retry_delay_sec,
            )
            return

        self._alerts.send(
            f"出場下單失敗且重試耗盡 | category={category.value} err={exc}",
            level="CRITICAL",
        )
        with self.lock:
            self.block_new_entry = True
        try:
            self.sync_positions()
        except Exception as sync_err:
            logger.error("出場失敗後對帳異常: %s", sync_err)


    def _reconstruct_pending_signal(self) -> OrderSignal | None:
        with self.lock:
            if not self.is_pending or self.pending_intent != "exit":
                return None
            action = self._pending_action
            if not action:
                action = "Sell" if self.position_dir == "Long" else "Buy"
            # Phase 1: prefer actual position_qty for exit sizing (full flatten policy)
            exit_qty = self.position_qty if self.position_qty > 0 else (self.pending_qty or 1)
            return OrderSignal(
                action,
                exit_qty,
                self.pending_signal_price,
                "exit",
                exchange_ts=self.pending_exchange_ts,
                slippage_points=self.pending_ioc_slippage,
                market=getattr(self, "pending_market", False),
            )


    def _start_order_worker(self) -> None:
        if self._order_worker_started:
            return
        self._order_worker_started = True
        threading.Thread(
            target=self._order_worker_loop,
            daemon=True,
            name="order-worker",
        ).start()


    def _order_worker_loop(self) -> None:
        while True:
            item = self._order_queue.get()
            try:
                if item is None:
                    break
                self.place_order(item)
            except BaseException as e:
                # Catch PanicException etc. too; order worker death is critical (no more orders).
                logger.error("Order worker 嚴重異常: %s", e)
                # Re-raise only system exits; otherwise continue to not lose the worker.
                if isinstance(e, (SystemExit, KeyboardInterrupt)):
                    raise
                # else log and continue (worker stays alive)
            finally:
                self._order_queue.task_done()


    def _enqueue_order(self, signal: OrderSignal) -> None:
        """Decouple API place_order from on_tick lock (live: async worker)."""
        if self._order_sync_mode:
            self.place_order(signal)
            return
        self._start_order_worker()
        self._order_queue.put_nowait(signal)


