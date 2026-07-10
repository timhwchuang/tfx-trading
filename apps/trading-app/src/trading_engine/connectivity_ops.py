"""Connectivity behavior: disconnect, reconnect, session watchdog, warmup.

State lives on ``ConnectivityState`` (``_link``). Phase G3: ConnectivityOpsService.
"""

from __future__ import annotations

import threading
from enum import Enum, auto
from typing import Any, Protocol

from trading_engine.core.host_service import HostBoundService
from trading_engine.logging_setup import get_logger

logger = get_logger()


class ReconnectOutcome(Enum):
    HEALTHY = auto()
    UNHEALTHY = auto()
    STALE = auto()


class ConnectivityOpsHost(Protocol):
    """Surface used by disconnect / reconnect / session watchdog."""

    lock: Any
    _cfg: Any
    _link: Any
    _book: Any
    _alerts: Any
    _clock: Any
    _resubscribe_ticks: Any
    _resubscribe_trade: Any
    api: Any

    def _call_api(self, fn, *args, **kwargs): ...

    def sync_positions(self, *, force_resync: bool = False) -> None: ...


class _ConnectivityOpsMethods:
    def _is_reconnect_warmup_active(self, ts: int) -> bool:
        return self._link._reconnect_warmup_until_ts > 0 and ts < self._link._reconnect_warmup_until_ts

    def _arm_reconnect_warmup_on_first_tick_locked(self, ts: int) -> None:
        if not self._link._pending_reconnect_warmup:
            return
        warmup_sec = self._cfg.reconnect_warmup_sec
        self._link._reconnect_warmup_until_ts = ts + warmup_sec
        self._link._pending_reconnect_warmup = False
        logger.info(
            "重連暖機開始 | %ds 內禁止新進場（until_ts=%d）",
            warmup_sec,
            self._link._reconnect_warmup_until_ts,
        )

    def _check_session_watchdog(self) -> None:
        with self.lock:
            if self._link._api_connected:
                return
            disconnected_since = self._link._disconnect_since
            next_at = self._link._next_relogin_at
            attempts = self._link._session_relogin_attempts

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
                self._link._next_relogin_at = now + 300.0
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
                if self._link._api_connected:
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
                    "Session 重登入後健康檢查失敗（subscribe/trade）",
                    level="CRITICAL",
                )
                with self.lock:
                    self._link._session_relogin_attempts = attempts + 1
                    self._link._next_relogin_at = now + backoff
            elif outcome == ReconnectOutcome.STALE:
                backoff = self._cfg.session_relogin_backoff_base_sec
                logger.info(
                    "Session 重登入被較新的 reconnect 取代，短暫 backoff %.1fs",
                    backoff,
                )
                with self.lock:
                    self._link._next_relogin_at = now + backoff
        except Exception as e:
            backoff = self._cfg.session_relogin_backoff_base_sec * (2**attempts)
            logger.error("Session 重登入失敗: %s | backoff=%.1fs", e, backoff)
            self._alerts.send(f"Session 重登入失敗: {e}", level="CRITICAL")
            with self.lock:
                self._link._session_relogin_attempts = attempts + 1
                self._link._next_relogin_at = now + backoff

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
            if require_silent_sec is not None and self._ticks._last_tick_wall_time > 0:
                if self._clock() - self._ticks._last_tick_wall_time < require_silent_sec:
                    return False
            if (
                max_connected_reconnect_generation is not None
                and self._link._connected_reconnect_generation
                > max_connected_reconnect_generation
            ):
                return False
            if (
                reconnect_generation is not None
                and reconnect_generation != self._link._reconnect_generation
            ):
                return False
            if (
                reconnect_generation is not None
                and self._link._api_connected
                and reconnect_generation != self._link._connected_reconnect_generation
            ):
                return False
            was_connected = self._link._api_connected
            self._link._api_connected = False
            if reconnect_generation is None:
                self._link._connected_reconnect_generation = 0
            if self._link._disconnect_since <= 0:
                self._link._disconnect_since = self._clock()
            if was_connected:
                self._link._disconnect_count_today += 1
                alert_qty = self._book.position_qty
                alert_dir = self._book.position_dir
                disconnect_count = self._link._disconnect_count_today
            else:
                disconnect_count = self._link._disconnect_count_today
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
                self._book.block_new_entry = True
            self._alerts.send(
                f"單日斷線達 {disconnect_count} 次（上限 "
                f"{self._cfg.max_disconnects_per_day}）→ 停止新進場至日切換；請排查網路",
                level="CRITICAL",
            )
        return True

    def handle_session_event(
        self, resp_code: int, event_code: int, info: str, event: str
    ):
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

        Returns HEALTHY when subscribe health gate passed and connected state applied.
        """
        with self.lock:
            self._link._reconnect_generation += 1
            generation = self._link._reconnect_generation
            has_pending = self._book.is_pending

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

        with self.lock:
            if generation != self._link._reconnect_generation:
                logger.info(
                    "重連同步結果已過期，忽略 | gen=%d current=%d healthy=%s",
                    generation,
                    self._link._reconnect_generation,
                    session_healthy,
                )
                return ReconnectOutcome.STALE
            if session_healthy:
                self._link._pending_reconnect_warmup = True
                self._link._reconnect_warmup_until_ts = 0
                self._link._api_connected = True
                self._link._connected_reconnect_generation = generation
                self._link._disconnect_since = 0.0
                self._link._session_relogin_attempts = 0
                self._link._next_relogin_at = 0.0
                self._ticks._no_tick_resubscribe_streak = 0

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
                self._link._reconnect_generation,
            )
            return ReconnectOutcome.STALE
        return ReconnectOutcome.UNHEALTHY


class ConnectivityOpsService(HostBoundService):
    def __init__(self, host: ConnectivityOpsHost) -> None:
        super().__init__(host, _ConnectivityOpsMethods)


ConnectivityOpsMixin = ConnectivityOpsService

__all__ = [
    "ConnectivityOpsHost",
    "ConnectivityOpsService",
    "ConnectivityOpsMixin",
    "ReconnectOutcome",
]
