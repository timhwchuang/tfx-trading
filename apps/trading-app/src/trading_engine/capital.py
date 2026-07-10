"""Capital service: progressive MDD book + durable store (Host policy impl).

MDD freeze is a **Host** safety policy (not strategy alpha).
``TradingEngine`` only orchestrates: boot ``load()``, fill calls
``on_exit_fill``, public ``clear()`` / gate reads.

Caller holds ``TradingEngine.lock`` for fill/clear paths as today.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from trading_engine.core.capital_store import CapitalStore
from trading_engine.core.risk import CapitalRiskState
from trading_engine.logging_setup import get_logger

logger = get_logger()


@dataclass(frozen=True)
class CapitalExitEvent:
    """Result of applying one exit-fill PnL to the progressive book."""

    total_pnl: float
    newly_frozen: bool
    persist_ok: bool
    persist_alert: str | None = None
    freeze_alert: str | None = None


class CapitalService:
    """Owns ``CapitalRiskState`` + ``CapitalStore`` and max_mdd gate semantics."""

    def __init__(
        self,
        store: CapitalStore,
        *,
        product_code: str,
        max_mdd_points: float | Callable[[], float] = 0.0,
    ) -> None:
        self._store = store
        self._product_code = str(product_code)
        # Callable allows host to mutate runtime_config.max_mdd_points in tests.
        if callable(max_mdd_points):
            self._max_mdd_fn: Callable[[], float] = max_mdd_points
        else:
            fixed = float(max_mdd_points or 0)
            self._max_mdd_fn = lambda: fixed
        self._state = CapitalRiskState()

    # --- readonly surface (compat with host properties) ---

    @property
    def state(self) -> CapitalRiskState:
        return self._state

    @property
    def capital_frozen(self) -> bool:
        return self._state.capital_frozen

    @property
    def realized_pnl(self) -> float:
        return self._state.realized_pnl

    @property
    def equity_peak(self) -> float:
        return self._state.equity_peak

    @property
    def current_drawdown(self) -> float:
        return self._state.current_drawdown

    @property
    def max_mdd_points(self) -> float:
        return float(self._max_mdd_fn() or 0)

    @property
    def store(self) -> CapitalStore:
        return self._store

    def gate_active(self) -> bool:
        """True when progressive MDD is configured to block entries (limit > 0)."""
        return self.max_mdd_points > 0

    def blocks_entry(self) -> bool:
        """Capital side of entry gate: gate on AND sticky frozen."""
        return self.gate_active() and self._state.capital_frozen

    # --- lifecycle ---

    def load(self) -> list[str]:
        """Load book from store; re-evaluate MDD if gate active.

        Returns CRITICAL-stage messages (0–1 typical) for caller to stage
        after attrs exist. Does not hold engine lock.
        """
        alerts: list[str] = []
        loaded = self._store.load(product_code=self._product_code)
        if loaded is not None:
            self._state = loaded

        max_mdd = self.max_mdd_points
        if max_mdd <= 0:
            if self._state.capital_frozen:
                logger.info(
                    "max_mdd_points<=0：MDD 閘門關閉，不套用 sticky capital_frozen "
                    "（帳本 realized/peak 仍保留）| frozen_on_disk=%s",
                    self._state.capital_frozen,
                )
            return alerts

        # Enabling max_mdd against an existing progressive book must freeze
        # immediately (not wait for next exit).
        if self._state.evaluate_mdd(max_mdd):
            logger.warning(
                "啟動載入後累進 MDD 已達上限 %.1f（drawdown=%.1f）→ capital_frozen",
                max_mdd,
                self._state.current_drawdown,
            )
            ok, alert = self.persist()
            if not ok and alert:
                alerts.append(alert)
        return alerts

    def persist(self) -> tuple[bool, str | None]:
        """Write capital book. Returns (ok, critical_alert_message|None)."""
        if not self._store.enabled:
            return True, None
        ok = self._store.save(self._state, product_code=self._product_code)
        if ok:
            return True, None
        logger.error(
            "資本帳寫入失敗 | path=%s frozen=%s realized=%.2f",
            self._store.path,
            self._state.capital_frozen,
            self._state.realized_pnl,
        )
        msg = (
            f"資本帳寫入失敗 | path={self._store.path} "
            f"frozen={self._state.capital_frozen} "
            f"realized={self._state.realized_pnl:.2f} "
            f"— 記憶體狀態可能在重啟後遺失；請檢查磁碟權限/路徑"
        )
        return False, msg

    def on_exit_fill(self, total_pnl: float) -> CapitalExitEvent:
        """Apply exit PnL, evaluate MDD, persist. Caller holds lock."""
        max_mdd = self.max_mdd_points
        self._state.apply_realized_pnl(total_pnl)
        newly = self._state.evaluate_mdd(max_mdd)
        freeze_alert: str | None = None
        if newly:
            logger.warning(
                "累進 MDD 達上限 %.1f（drawdown=%.1f peak=%.1f equity=%.1f）"
                " → capital_frozen；凍結新進場直到 clear_capital_risk()",
                max_mdd,
                self._state.current_drawdown,
                self._state.equity_peak,
                self._state.realized_pnl,
            )
            freeze_alert = (
                f"累進 MDD 觸頂 | drawdown={self._state.current_drawdown:.1f} "
                f"limit={max_mdd:.1f} realized={self._state.realized_pnl:.1f} "
                f"peak={self._state.equity_peak:.1f} → 已凍結新進場；請檢視策略後 clear_capital_risk()"
            )
        # Durable progressive book (restart-safe); position still broker-SSOT.
        persist_ok, persist_alert = self.persist()
        return CapitalExitEvent(
            total_pnl=total_pnl,
            newly_frozen=newly,
            persist_ok=persist_ok,
            persist_alert=persist_alert,
            freeze_alert=freeze_alert,
        )

    def clear(self) -> tuple[bool, str | None]:
        """Operator clear: reset book and unfreeze. Caller holds lock."""
        self._state.clear()
        return self.persist()


__all__ = ["CapitalService", "CapitalExitEvent"]
