"""Atomic JSON persistence for progressive capital MDD state.

Position is NOT stored here — restart trusts the broker via sync_positions.
Only the progressive equity book (realized / peak / frozen) is durable.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trading_engine.core.risk import CapitalRiskState
from trading_engine.logging_setup import get_logger

logger = get_logger()

STORE_VERSION = 1


class CapitalStore:
    """Load/save ``CapitalRiskState`` to a single JSON file (atomic replace)."""

    def __init__(self, path: str | Path | None) -> None:
        """``path`` should already be absolute when set via app config.

        Relative paths still resolve against process CWD as a last resort;
        prefer ``config.resolve_capital_state_path`` at the app layer.
        """
        self.path: Path | None
        if path is None or str(path).strip() == "":
            self.path = None
        else:
            p = Path(path).expanduser()
            self.path = p.resolve() if p.is_absolute() else p

    @property
    def enabled(self) -> bool:
        return self.path is not None

    def load(self, *, product_code: str) -> CapitalRiskState | None:
        """Return stored state, or None if disabled / missing / unreadable.

        On product_code mismatch: log warning and return None (start clean)
        rather than applying another product's book.
        """
        if self.path is None:
            return None
        if not self.path.is_file():
            logger.info("資本帳檔不存在，以空白帳啟動 | path=%s", self.path)
            return None
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("資本帳檔讀取失敗，以空白帳啟動 | path=%s err=%s", self.path, exc)
            return None
        if not isinstance(raw, dict):
            logger.warning("資本帳檔格式錯誤（非 object），以空白帳啟動 | path=%s", self.path)
            return None

        stored_code = str(raw.get("product_code") or "").strip()
        if not stored_code:
            logger.warning(
                "資本帳缺少 product_code，視為損壞 → 忽略檔案 | path=%s",
                self.path,
            )
            return None
        if product_code and stored_code != product_code:
            logger.warning(
                "資本帳 product_code 不符 | file=%s runtime=%s → 忽略檔案",
                stored_code,
                product_code,
            )
            return None

        try:
            state = CapitalRiskState(
                realized_pnl=float(raw.get("realized_pnl", 0.0)),
                equity_peak=float(raw.get("equity_peak", 0.0)),
                capital_frozen=bool(raw.get("capital_frozen", False)),
            )
        except (TypeError, ValueError) as exc:
            logger.warning("資本帳欄位解析失敗，以空白帳啟動 | err=%s", exc)
            return None

        # Peak must be at least equity (repair corrupt/partial files).
        if state.realized_pnl > state.equity_peak:
            state.equity_peak = state.realized_pnl

        logger.info(
            "已載入資本帳 | path=%s realized=%.2f peak=%.2f dd=%.2f frozen=%s",
            self.path,
            state.realized_pnl,
            state.equity_peak,
            state.current_drawdown,
            state.capital_frozen,
        )
        return state

    def save(self, state: CapitalRiskState, *, product_code: str) -> bool:
        """Atomically write state. Returns True on success. No-op if disabled."""
        if self.path is None:
            return False
        payload: dict[str, Any] = {
            "version": STORE_VERSION,
            "product_code": product_code,
            "realized_pnl": float(state.realized_pnl),
            "equity_peak": float(state.equity_peak),
            "capital_frozen": bool(state.capital_frozen),
            "updated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            data = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
            fd, tmp_name = tempfile.mkstemp(
                dir=str(self.path.parent),
                prefix=f".{self.path.name}.",
                suffix=".tmp",
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(data)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp_name, self.path)
            except Exception:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
                raise
            logger.debug(
                "資本帳已寫入 | path=%s realized=%.2f frozen=%s",
                self.path,
                state.realized_pnl,
                state.capital_frozen,
            )
            return True
        except OSError as exc:
            logger.warning("資本帳寫入失敗 | path=%s err=%s", self.path, exc)
            return False


def capital_state_to_dict(state: CapitalRiskState) -> dict[str, Any]:
    """Test/debug helper."""
    return asdict(state)


__all__ = ["CapitalStore", "STORE_VERSION", "capital_state_to_dict"]
