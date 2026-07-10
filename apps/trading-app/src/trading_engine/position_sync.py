"""Broker position read / adopt — kernel holds Book; broker is restart SSOT.

Position domain (Phase E):
  - ``Book`` — in-process held qty + flight (mutation API)
  - ``position_sync`` (this module) — list_positions → adopt into Book
  - ``reconcile`` — periodic drift / severe HALT against broker truth

Does not own session calendar, login, or strategy decisions.
"""

from __future__ import annotations

import time
from typing import Any, Protocol

from trading_engine.core.audit.exec_audit import ExecAudit, format_exec_audit
from trading_engine.logging_setup import get_logger

logger = get_logger()


class PositionSyncHost(Protocol):
    """Minimal surface used by broker position sync (implemented by TradingEngine)."""

    api: Any
    lock: Any
    contract: Any
    _book: Any
    _cfg: Any

    def _call_api(self, fn, *args, **kwargs): ...

    def reset_strategy_state(self) -> None: ...


def contract_position_codes(contract: Any) -> set[str]:
    codes = {contract.code}
    for attr in ("target_code", "symbol"):
        value = getattr(contract, attr, None)
        if value:
            codes.add(value)
    return codes


def position_matches_contract(contract: Any, pos: Any) -> bool:
    return pos.code in contract_position_codes(contract)


class PositionSyncMixin:
    """Mixin: broker list_positions → Book. Prefer over scattering on Session."""

    def _contract_position_codes(self) -> set:
        return contract_position_codes(self.contract)

    def _position_matches_contract(self, pos) -> bool:
        return position_matches_contract(self.contract, pos)

    def read_broker_position(self) -> tuple[int, str] | None:
        """Read the first matching non-zero broker position as (qty, dir).

        Returns ``(0, "Flat")`` when the broker is flat for this contract, or
        ``None`` when the broker query failed (caller should not act on a failed
        read). Pure query (``list_positions``); does not mutate kernel state.
        """
        try:
            account = self._call_api(lambda: self.api.futopt_account)
            positions = list(self._call_api(self.api.list_positions, account=account))
        except Exception as e:
            logger.warning("讀取券商持倉失敗: %s", e)
            return None

        from trading_engine.adapters.position_normalizer import is_long_direction

        for pos in positions:
            if int(pos.quantity) == 0:
                continue
            if self._position_matches_contract(pos):
                direction = "Long" if is_long_direction(pos.direction) else "Short"
                return int(pos.quantity), direction
        return 0, "Flat"

    def sync_positions(self, *, force_resync: bool = False):
        """Sync kernel Book from broker — restart / reconnect / HALT adopt path."""
        try:
            account = self._call_api(lambda: self.api.futopt_account)
            positions = list(self._call_api(self.api.list_positions, account=account))
        except Exception as e:
            logger.warning("持倉對帳失敗: %s", e)
            return

        matched = None
        for pos in positions:
            if int(pos.quantity) == 0:
                continue
            if self._position_matches_contract(pos):
                matched = pos
                break

        with self.lock:
            book = self._book
            if matched is None:
                book.clear_position()
                open_positions = [p for p in positions if int(p.quantity) != 0]
                if open_positions:
                    logger.warning(
                        "券商有 %d 筆持倉，但無法對應合約 %s（%s）",
                        len(open_positions),
                        self.contract.code,
                        ", ".join(p.code for p in open_positions),
                    )
                else:
                    logger.info("持倉對帳 | 無持倉")
                return

            from trading_engine.adapters.position_normalizer import is_long_direction

            is_long = is_long_direction(matched.direction)
            new_dir = "Long" if is_long else "Short"
            had_position = book.position_qty > 0
            same_direction = had_position and book.position_dir == new_dir
            preserve_peak = had_position and same_direction and not force_resync

            qty_before, qty_after = book.adopt_broker_position(
                int(matched.quantity),
                new_dir,
                float(matched.price),
                preserve_peak=preserve_peak,
                clear_entry_tracking=True,
            )

            if qty_before != qty_after:
                try:
                    ts = getattr(self, "last_tick_exchange_ts", 0) or int(time.time())
                    exec_audit = ExecAudit(
                        event_type="position_sync",
                        ts=ts,
                        qty_before=qty_before,
                        qty_after=qty_after,
                        position_dir=new_dir,
                    )
                    logger.info("EXEC_AUDIT %s", format_exec_audit(exec_audit))
                except Exception:
                    pass

            if preserve_peak:
                logger.info(
                    "持倉對帳 | 保留 trailing_peak=%.1f | %s %d口 @ %.1f",
                    book.trailing_peak,
                    book.position_dir,
                    matched.quantity,
                    book.entry_price,
                )
            self.reset_strategy_state()
            if not preserve_peak:
                logger.info(
                    "持倉對帳 | %s %d口 @ %.1f | code=%s",
                    book.position_dir,
                    matched.quantity,
                    book.entry_price,
                    matched.code,
                )


__all__ = [
    "PositionSyncHost",
    "PositionSyncMixin",
    "contract_position_codes",
    "position_matches_contract",
]
