from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml

from tfx_trading.trading.models import OrderKind, Side, TradeReason, TradeRecord

POINT_VALUE_NT = 10
TICK_SIZE = 1.0
TAX_RATE = 0.00002

_DEFAULT_COMMISSION_NT = 20
_DEFAULT_SLIPPAGE_TICKS = 1
_DEFAULT_FLATTEN_SLIPPAGE_TICKS = 2
_DEFAULT_INITIAL_MARGIN_NT = 35050
_DEFAULT_MAINTENANCE_MARGIN_NT = 26900

_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "config.yaml"

MarginKind = Literal["initial", "maintenance"]


@dataclass(frozen=True)
class CostConfig:
    commission_nt: float
    slippage_ticks: int
    flatten_slippage_ticks: int
    initial_margin_nt: float
    maintenance_margin_nt: float


def load_trading_config(path: Path | None = None) -> CostConfig:
    config_path = path if path is not None else _DEFAULT_CONFIG_PATH
    if not config_path.is_file():
        raise FileNotFoundError(f"找不到設定檔: {config_path}")
    with config_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    section = raw.get("trading") or {}
    return CostConfig(
        commission_nt=float(section.get("commission_nt", _DEFAULT_COMMISSION_NT)),
        slippage_ticks=int(section.get("slippage_ticks", _DEFAULT_SLIPPAGE_TICKS)),
        flatten_slippage_ticks=int(
            section.get("flatten_slippage_ticks", _DEFAULT_FLATTEN_SLIPPAGE_TICKS)
        ),
        initial_margin_nt=float(section.get("initial_margin_nt", _DEFAULT_INITIAL_MARGIN_NT)),
        maintenance_margin_nt=float(
            section.get("maintenance_margin_nt", _DEFAULT_MAINTENANCE_MARGIN_NT)
        ),
    )


def contract_value_nt(price: float, qty: int) -> float:
    return price * POINT_VALUE_NT * qty


def tax_nt(price: float, qty: int) -> float:
    return contract_value_nt(price, qty) * TAX_RATE


def commission_nt(qty: int, cfg: CostConfig) -> float:
    return cfg.commission_nt * qty


def round_trip_pnl_nt(
    side: Side,
    entry: float,
    exit: float,
    qty: int,
    cfg: CostConfig,
) -> float:
    """Net NT$ of a round trip. side is the position, not the exit order.

    Flattening a long still passes side='long'. Do not pass Order.side from a
    flatten/stop sell (that is 'short' and would flip the sign).
    """
    sign = 1.0 if side == "long" else -1.0
    gross_nt = (exit - entry) * sign * POINT_VALUE_NT * qty
    fees = tax_nt(entry, qty) + tax_nt(exit, qty) + 2 * commission_nt(qty, cfg)
    return gross_nt - fees


def apply_slippage(kind: OrderKind, side: Side, price: float, cfg: CostConfig) -> float:
    """Adjust a fill price. side is the order's buy/sell, same as Intent/Order.

    Buy (long) adds ticks; sell (short) subtracts. Flatten a long uses side='short'.
    """
    if kind == "limit":
        return price
    ticks = cfg.flatten_slippage_ticks if kind == "flatten" else cfg.slippage_ticks
    delta = ticks * TICK_SIZE
    if side == "long":
        return price + delta
    return price - delta


def margin_required_nt(
    qty: int,
    cfg: CostConfig,
    *,
    kind: MarginKind = "initial",
) -> float:
    per_lot = cfg.initial_margin_nt if kind == "initial" else cfg.maintenance_margin_nt
    return qty * per_lot


def close_trade(
    side: Side,
    entry_ts: datetime,
    entry_price: float,
    exit_ts: datetime,
    exit_price: float,
    qty: int,
    reason: TradeReason,
    cfg: CostConfig,
    *,
    risk_nt: float | None = None,
) -> TradeRecord:
    """Build a TradeRecord. side is the position that was held, not the exit order.

    Same rule as round_trip_pnl_nt: a stopped-out long is side='long' even when
    the flatten/stop Order.side is 'short'.
    """
    pnl = round_trip_pnl_nt(side, entry_price, exit_price, qty, cfg)
    r_multiple = (pnl / risk_nt) if risk_nt is not None else None
    return TradeRecord(
        side=side,
        entry_ts=entry_ts,
        entry_price=entry_price,
        exit_ts=exit_ts,
        exit_price=exit_price,
        qty=qty,
        pnl_nt=pnl,
        r_multiple=r_multiple,
        reason=reason,
    )


__all__ = [
    "POINT_VALUE_NT",
    "TAX_RATE",
    "TICK_SIZE",
    "CostConfig",
    "apply_slippage",
    "close_trade",
    "commission_nt",
    "contract_value_nt",
    "load_trading_config",
    "margin_required_nt",
    "round_trip_pnl_nt",
    "tax_nt",
]
