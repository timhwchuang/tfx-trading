from __future__ import annotations

import csv
import math
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from tfx_trading.backtest.config import FillMode
from tfx_trading.bar_store import session_kind
from tfx_trading.kbar import KBar
from tfx_trading.trading.costs import POINT_VALUE_NT, CostConfig, margin_required_nt
from tfx_trading.trading.models import Position, TradeRecord


@dataclass(frozen=True)
class RunMeta:
    git_hash: str | None = None
    source_files: str = "in-memory"


@dataclass(frozen=True)
class BacktestResult:
    """Ledger snapshot. profit_factor is inf when there are no losing trades."""

    trades: tuple[TradeRecord, ...]
    equity_curve: tuple[tuple[datetime, float], ...]
    total_pnl_nt: float
    mdd_nt: float
    win_rate: float
    profit_factor: float
    expected_r: float | None
    avg_hold: float
    day_pnl_nt: float
    night_pnl_nt: float
    max_margin_nt: float
    min_account_nt: float
    fill_mode: FillMode
    git_hash: str
    source_files: str
    n_1m: int
    start: datetime | None
    end: datetime | None
    commission_nt: float
    slippage_ticks: int
    flatten_slippage_ticks: int
    initial_margin_nt: float
    maintenance_margin_nt: float

    def write_trade_log(self, path: Path) -> None:
        lines = [
            f"# git_hash: {self.git_hash}",
            f"# fill_mode: {self.fill_mode}",
            f"# commission_nt: {self.commission_nt}",
            f"# slippage_ticks: {self.slippage_ticks}",
            f"# flatten_slippage_ticks: {self.flatten_slippage_ticks}",
            f"# initial_margin_nt: {self.initial_margin_nt}",
            f"# maintenance_margin_nt: {self.maintenance_margin_nt}",
            f"# start: {self.start.isoformat() if self.start else ''}",
            f"# end: {self.end.isoformat() if self.end else ''}",
            f"# n_1m: {self.n_1m}",
            f"# source_files: {self.source_files}",
        ]
        fieldnames = [
            "side",
            "entry_ts",
            "entry_price",
            "exit_ts",
            "exit_price",
            "qty",
            "pnl_nt",
            "r_multiple",
            "reason",
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            handle.write("\n".join(lines) + "\n")
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for trade in self.trades:
                writer.writerow(
                    {
                        "side": trade.side,
                        "entry_ts": trade.entry_ts.isoformat(),
                        "entry_price": trade.entry_price,
                        "exit_ts": trade.exit_ts.isoformat(),
                        "exit_price": trade.exit_price,
                        "qty": trade.qty,
                        "pnl_nt": trade.pnl_nt,
                        "r_multiple": trade.r_multiple,
                        "reason": trade.reason,
                    }
                )


def resolve_git_hash(meta: RunMeta | None) -> str:
    if meta is not None and meta.git_hash is not None:
        return meta.git_hash
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return "unknown"
    if completed.returncode != 0:
        return "unknown"
    return completed.stdout.strip() or "unknown"


def entry_session(ts: datetime) -> str | None:
    kind = session_kind(ts)
    if kind is not None:
        return kind
    if ts.hour == 13 and ts.minute == 46:
        return "day"
    if ts.hour == 5 and ts.minute == 1:
        return "night"
    return None


class Ledger:
    """Records trades and equity. Does not call close_trade."""

    def __init__(self, cost_cfg: CostConfig, fill_mode: FillMode, meta: RunMeta | None) -> None:
        self._cost = cost_cfg
        self._fill_mode = fill_mode
        self._meta = meta
        self._trades: list[TradeRecord] = []
        self._equity: list[tuple[datetime, float]] = []
        self._realized = 0.0
        self._peak = 0.0
        self._mdd = 0.0
        self._max_margin = 0.0

    def on_bar(self, bar: KBar, trade: TradeRecord | None, position: Position) -> None:
        if trade is not None:
            self._trades.append(trade)
            self._realized += trade.pnl_nt
            self._max_margin = max(
                self._max_margin,
                margin_required_nt(trade.qty, self._cost, kind="initial"),
            )
        if position.side is not None:
            assert position.avg_price is not None
            sign = 1.0 if position.side == "long" else -1.0
            mtm = (bar.close - position.avg_price) * sign * POINT_VALUE_NT * position.qty
            equity = self._realized + mtm
            self._max_margin = max(
                self._max_margin,
                margin_required_nt(position.qty, self._cost, kind="initial"),
            )
        else:
            equity = self._realized
        self._equity.append((bar.timestamp, equity))
        self._peak = max(self._peak, equity)
        dd = self._peak - equity
        if dd > self._mdd:
            self._mdd = dd

    def finish(self, bars: list[KBar]) -> BacktestResult:
        trades = tuple(self._trades)
        wins = [t.pnl_nt for t in trades if t.pnl_nt > 0]
        losses = [t.pnl_nt for t in trades if t.pnl_nt < 0]
        n = len(trades)
        if not losses:
            profit_factor = math.inf
        else:
            profit_factor = sum(wins) / abs(sum(losses))
        r_values = [t.r_multiple for t in trades if t.r_multiple is not None]
        expected_r = (sum(r_values) / len(r_values)) if r_values else None
        if n == 0:
            avg_hold = 0.0
            win_rate = 0.0
        else:
            holds = [(t.exit_ts - t.entry_ts).total_seconds() / 60.0 for t in trades]
            avg_hold = sum(holds) / n
            win_rate = sum(1 for t in trades if t.pnl_nt > 0) / n
        day_pnl = 0.0
        night_pnl = 0.0
        for trade in trades:
            bucket = entry_session(trade.entry_ts)
            if bucket == "day":
                day_pnl += trade.pnl_nt
            elif bucket == "night":
                night_pnl += trade.pnl_nt
        source = self._meta.source_files if self._meta is not None else "in-memory"
        return BacktestResult(
            trades=trades,
            equity_curve=tuple(self._equity),
            total_pnl_nt=self._realized,
            mdd_nt=self._mdd,
            win_rate=win_rate,
            profit_factor=profit_factor,
            expected_r=expected_r,
            avg_hold=avg_hold,
            day_pnl_nt=day_pnl,
            night_pnl_nt=night_pnl,
            max_margin_nt=self._max_margin,
            min_account_nt=self._max_margin + self._mdd,
            fill_mode=self._fill_mode,
            git_hash=resolve_git_hash(self._meta),
            source_files=source,
            n_1m=len(bars),
            start=bars[0].timestamp if bars else None,
            end=bars[-1].timestamp if bars else None,
            commission_nt=self._cost.commission_nt,
            slippage_ticks=self._cost.slippage_ticks,
            flatten_slippage_ticks=self._cost.flatten_slippage_ticks,
            initial_margin_nt=self._cost.initial_margin_nt,
            maintenance_margin_nt=self._cost.maintenance_margin_nt,
        )


def empty_result(cost_cfg: CostConfig, fill_mode: FillMode, meta: RunMeta | None) -> BacktestResult:
    ledger = Ledger(cost_cfg, fill_mode, meta)
    return ledger.finish([])


__all__ = [
    "BacktestResult",
    "Ledger",
    "RunMeta",
    "empty_result",
    "entry_session",
    "resolve_git_hash",
]
