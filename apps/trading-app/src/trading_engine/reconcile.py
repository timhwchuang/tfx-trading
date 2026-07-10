"""Periodic kernel↔broker position reconcile (drift / severe HALT).

Owns the **background safety net** for lost fill callbacks: compare Book to
broker, adopt truth, block entries, or HALT on severe drift.

State flags live on ``IntegrityState`` (``_position_drift_detected``,
``_last_reconcile_wall``, severe-drift debounce). This module is the behavior.
"""

from __future__ import annotations

from typing import Any, Protocol

from trading_engine.logging_setup import get_logger

logger = get_logger()


class ReconcileHost(Protocol):
    """Surface used by periodic position reconcile (TradingEngine)."""

    lock: Any
    contract: Any
    _cfg: Any
    _api_connected: bool
    _last_tick_exchange_dt: Any
    is_pending: bool
    _settling: bool
    position_qty: int
    position_dir: str
    _position_unconfirmed: bool
    _post_exit_reconcile_until: float
    _last_reconcile_wall: float
    _position_drift_detected: bool
    _severe_drift_broker_read: Any
    _severe_drift_read_streak: int
    block_new_entry: bool
    _alerts: Any

    def _clock(self) -> float: ...

    def is_trading_session(self, dt) -> bool: ...

    def read_broker_position(self) -> tuple[int, str] | None: ...

    def sync_positions(self, *, force_resync: bool = False) -> None: ...

    def _halt_position_unconfirmed(
        self,
        reason: str,
        *,
        clear_pending: bool = False,
        send_alert: bool = True,
    ) -> None: ...


def is_severe_drift(
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


def severe_drift_confirmed(
    host: ReconcileHost,
    kernel_qty: int,
    kernel_dir: str,
    broker_qty: int,
    broker_dir: str,
) -> bool:
    """True once severe drift is seen on debounced consecutive broker reads."""
    if not is_severe_drift(kernel_qty, kernel_dir, broker_qty, broker_dir):
        with host.lock:
            host._severe_drift_broker_read = None
            host._severe_drift_read_streak = 0
        return False
    broker = (broker_qty, broker_dir)
    need = max(1, int(host._cfg.reconcile_confirm_reads))
    with host.lock:
        if host._severe_drift_broker_read == broker:
            host._severe_drift_read_streak += 1
        else:
            host._severe_drift_broker_read = broker
            host._severe_drift_read_streak = 1
        return host._severe_drift_read_streak >= need


def check_position_reconcile(host: ReconcileHost) -> None:
    """P0-3: periodically reconcile kernel position with the broker.

    Background safety net for lost order/fill callbacks: if the broker shows
    a different position than the kernel believes, adopt the broker truth,
    block new entries, and raise a CRITICAL alert. Exchange-time gated.

    P0-5: cadence is ``reconcile_fast_sec`` whenever the position is
    unconfirmed (HALT) so the kernel re-checks the broker quickly; otherwise
    the steady ``position_reconcile_sec``. Skipped while an order is in flight
    (pending) or settling — those windows are owned by settle/converge at the
    fast (1s) loop cadence.
    """
    steady = host._cfg.position_reconcile_sec
    if steady <= 0:
        return
    if not host._api_connected or host.contract is None:
        return
    if host._last_tick_exchange_dt is None:
        return
    if not host.is_trading_session(host._last_tick_exchange_dt):
        return

    with host.lock:
        if host.is_pending or host._settling:
            return
        kernel_qty = host.position_qty
        kernel_dir = host.position_dir
        unconfirmed = host._position_unconfirmed
        post_exit = host._clock() < host._post_exit_reconcile_until

    interval = (
        max(1, int(host._cfg.reconcile_fast_sec))
        if (unconfirmed or post_exit)
        else steady
    )
    now = host._clock()
    if now - host._last_reconcile_wall < interval:
        return

    broker = host.read_broker_position()
    if broker is None:
        return  # failed read; throttle not consumed — retry next cycle
    broker_qty, broker_dir = broker

    # Only consume the throttle after a successful broker read and comparison.
    host._last_reconcile_wall = now

    ceiling = host._cfg.max_position_qty
    if ceiling > 0 and broker_qty > ceiling and broker_qty > kernel_qty:
        host._position_drift_detected = True
        host._halt_position_unconfirmed(
            f"週期對帳發現超過部位上限 | kernel={kernel_dir} {kernel_qty}口 "
            f"broker={broker_dir} {broker_qty}口 > max={ceiling}"
        )
        return

    if is_severe_drift(kernel_qty, kernel_dir, broker_qty, broker_dir):
        if not severe_drift_confirmed(
            host, kernel_qty, kernel_dir, broker_qty, broker_dir
        ):
            return
        host._position_drift_detected = True
        logger.warning(
            "嚴重持倉漂移 | kernel=%s %d口 broker=%s %d口 → HALT 並收斂平倉",
            kernel_dir,
            kernel_qty,
            broker_dir,
            broker_qty,
        )
        with host.lock:
            host._severe_drift_broker_read = None
            host._severe_drift_read_streak = 0
        # Halt already syncs when no live pending; suppress generic CRITICAL so
        # this path emits a single severe-specific alert (no double list_positions).
        host._halt_position_unconfirmed(
            f"週期對帳嚴重漂移 | kernel={kernel_dir} {kernel_qty}口 "
            f"broker={broker_dir} {broker_qty}口",
            clear_pending=False,
            send_alert=False,
        )
        host._alerts.send(
            f"嚴重持倉漂移 | kernel={kernel_dir} {kernel_qty}口 vs "
            f"broker={broker_dir} {broker_qty}口 → 已 HALT 並收斂平倉；請人工核對",
            level="CRITICAL",
        )
        return

    if broker_qty == kernel_qty and broker_dir == kernel_dir:
        if host._position_drift_detected:
            logger.info(
                "週期對帳 | 已恢復一致 | %s %d口", kernel_dir, kernel_qty
            )
        host._position_drift_detected = False
        with host.lock:
            host._severe_drift_broker_read = None
            host._severe_drift_read_streak = 0
        return

    logger.warning(
        "持倉漂移偵測 | kernel=%s %d口 broker=%s %d口 → 以券商為準並停止新進場",
        kernel_dir,
        kernel_qty,
        broker_dir,
        broker_qty,
    )
    host._position_drift_detected = True
    with host.lock:
        host.block_new_entry = True
    host.sync_positions()
    host._alerts.send(
        f"持倉漂移 | kernel={kernel_dir} {kernel_qty}口 vs broker={broker_dir} "
        f"{broker_qty}口 → 已以券商為準並停止新進場；請人工核對",
        level="CRITICAL",
    )


__all__ = [
    "ReconcileHost",
    "is_severe_drift",
    "severe_drift_confirmed",
    "check_position_reconcile",
]
