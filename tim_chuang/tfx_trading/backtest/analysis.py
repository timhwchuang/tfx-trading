from __future__ import annotations

import itertools
import math
import random
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Literal

from tfx_trading.bar_store import session_key
from tfx_trading.kbar import KBar
from tfx_trading.strategy.setup_a import EntryPrice, SetupAParams, TakeProfit

MIN_IS_TRADES = 30
MIN_OOS_TRADES = 10
MC_DRAWS = 1000
FillModeName = Literal["optimistic", "conservative"]
SplitName = Literal["is", "oos"]
FoldStatus = Literal["skipped", "insufficient_sample", "empty_plateau", "elected"]
GateVerdict = Literal["go", "no_go", "smoke"]

_CATEGORICAL: frozenset[str] = frozenset({"entry_price", "take_profit", "require_external"})
_NUMERIC: frozenset[str] = frozenset({"min_points", "stop_buffer", "max_hold_bars"})
_FIELD_ORDER: tuple[str, ...] = (
    "entry_price",
    "min_points",
    "stop_buffer",
    "take_profit",
    "require_external",
    "max_hold_bars",
)


@dataclass(frozen=True)
class GridSpec:
    entry_price: tuple[EntryPrice, ...] = ("top", "ce")
    min_points: tuple[float, ...] = (15.0, 20.0, 30.0)
    stop_buffer: tuple[float, ...] = (3.0, 5.0, 8.0)
    take_profit: tuple[TakeProfit, ...] = ("2R", "opposite_liquidity")
    require_external: tuple[bool, ...] = (False, True)
    max_hold_bars: tuple[int, ...] = (12, 24, 10_000)

    def combos(self) -> tuple[StrategyCombo, ...]:
        rows: list[StrategyCombo] = []
        for values in itertools.product(
            self.entry_price,
            self.min_points,
            self.stop_buffer,
            self.take_profit,
            self.require_external,
            self.max_hold_bars,
        ):
            rows.append(
                StrategyCombo(
                    entry_price=values[0],
                    min_points=values[1],
                    stop_buffer=values[2],
                    take_profit=values[3],
                    require_external=values[4],
                    max_hold_bars=values[5],
                )
            )
        return tuple(rows)


@dataclass(frozen=True)
class StrategyCombo:
    entry_price: EntryPrice
    min_points: float
    stop_buffer: float
    take_profit: TakeProfit
    require_external: bool
    max_hold_bars: int

    def to_params(self, base: SetupAParams) -> SetupAParams:
        return replace(
            base,
            entry_price=self.entry_price,
            min_points=self.min_points,
            stop_buffer=self.stop_buffer,
            take_profit=self.take_profit,
            require_external=self.require_external,
            max_hold_bars=self.max_hold_bars,
        )


DEFAULT_COMBO = StrategyCombo(
    entry_price="top",
    min_points=20.0,
    stop_buffer=5.0,
    take_profit="2R",
    require_external=False,
    max_hold_bars=10_000,
)


@dataclass(frozen=True)
class CellMetrics:
    combo: StrategyCombo
    n_trades: int
    expected_nt: float | None
    expected_r: float | None
    total_pnl_nt: float
    mdd_nt: float
    win_rate: float
    profit_factor: float
    max_margin_nt: float
    fill_mode: FillModeName
    slippage_ticks: int
    split: SplitName | None = None


@dataclass(frozen=True)
class WindowBounds:
    start: datetime
    end: datetime
    day_dates: tuple[date, ...]


@dataclass(frozen=True)
class RollingFold:
    test_month: tuple[int, int]
    train_months: tuple[tuple[int, int], tuple[int, int], tuple[int, int]]
    train_dates: tuple[date, ...]
    test_dates: tuple[date, ...]


@dataclass(frozen=True)
class GateCheck:
    name: str
    passed: bool
    detail: str
    hard: bool


@dataclass(frozen=True)
class GateReport:
    verdict: GateVerdict
    checks: tuple[GateCheck, ...]
    decay: float | None
    capital_nt: float | None


def day_session_dates(bars: list[KBar]) -> list[date]:
    seen: set[date] = set()
    out: list[date] = []
    for bar in bars:
        key = session_key(bar.timestamp)
        if key is None or key[1] != "day":
            continue
        if key[0] not in seen:
            seen.add(key[0])
            out.append(key[0])
    out.sort()
    return out


def split_70_30(dates: list[date]) -> tuple[list[date], list[date]]:
    n_is = int(len(dates) * 0.7)
    return dates[:n_is], dates[n_is:]


def add_month(year_month: tuple[int, int], delta: int) -> tuple[int, int]:
    year, month = year_month
    month += delta
    while month > 12:
        year += 1
        month -= 12
    while month < 1:
        year -= 1
        month += 12
    return year, month


def month_le(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left <= right


def calendar_month_buckets(day_dates: list[date]) -> list[tuple[int, int]]:
    return sorted({(d.year, d.month) for d in day_dates})


def rolling_folds(day_dates: list[date]) -> list[RollingFold]:
    buckets = calendar_month_buckets(day_dates)
    if len(buckets) < 4:
        return []
    first = buckets[0]
    last = buckets[-1]
    folds: list[RollingFold] = []
    test = add_month(first, 3)
    while month_le(test, last):
        train_months = (add_month(test, -3), add_month(test, -2), add_month(test, -1))
        train_set = set(train_months)
        train_dates = tuple(d for d in day_dates if (d.year, d.month) in train_set)
        test_dates = tuple(d for d in day_dates if (d.year, d.month) == test)
        folds.append(
            RollingFold(
                test_month=test,
                train_months=train_months,
                train_dates=train_dates,
                test_dates=test_dates,
            )
        )
        test = add_month(test, 1)
    return folds


def fold_status(
    fold: RollingFold,
    train_cells: dict[StrategyCombo, CellMetrics] | None,
    spec: GridSpec,
) -> FoldStatus:
    if not fold.train_dates:
        return "insufficient_sample"
    if train_cells is None:
        return "insufficient_sample"
    if not any(cell.n_trades >= MIN_IS_TRADES for cell in train_cells.values()):
        return "insufficient_sample"
    if not plateau_combos(train_cells, spec):
        return "empty_plateau"
    return "elected"


def window_bounds(bars: list[KBar], day_dates: list[date]) -> WindowBounds | None:
    if not day_dates:
        return None
    first = day_dates[0]
    last = day_dates[-1]
    start = datetime.combine(first, time.min)
    end: datetime | None = None
    for bar in reversed(bars):
        if bar.timestamp.date() == last:
            end = bar.timestamp
            break
    if end is None:
        return None
    return WindowBounds(start=start, end=end, day_dates=tuple(day_dates))


def bars_through(bars: list[KBar], window_end: datetime) -> list[KBar]:
    return [bar for bar in bars if bar.timestamp <= window_end]


def expected_nt(total_pnl_nt: float, n_trades: int) -> float | None:
    if n_trades <= 0:
        return None
    return total_pnl_nt / n_trades


def neighbors(combo: StrategyCombo, spec: GridSpec) -> tuple[StrategyCombo, ...]:
    out: list[StrategyCombo] = []
    for name in _FIELD_ORDER:
        values = getattr(spec, name)
        current = getattr(combo, name)
        idx = list(values).index(current)
        if name in _CATEGORICAL:
            for j, value in enumerate(values):
                if j == idx:
                    continue
                out.append(replace(combo, **{name: value}))
            continue
        if name not in _NUMERIC:
            continue
        for j, value in enumerate(values):
            if abs(j - idx) == 1:
                out.append(replace(combo, **{name: value}))
    return tuple(out)


def is_profitable(cell: CellMetrics | None) -> bool:
    if cell is None:
        return False
    return cell.n_trades >= MIN_IS_TRADES and cell.expected_nt is not None and cell.expected_nt > 0


def plateau_combos(
    cells: dict[StrategyCombo, CellMetrics],
    spec: GridSpec,
) -> tuple[StrategyCombo, ...]:
    plateau: list[StrategyCombo] = []
    for combo, cell in cells.items():
        if not is_profitable(cell):
            continue
        if all(is_profitable(cells.get(nb)) for nb in neighbors(combo, spec)):
            plateau.append(combo)
    return tuple(plateau)


def _worst_neighbor_ev(
    combo: StrategyCombo,
    cells: dict[StrategyCombo, CellMetrics],
    spec: GridSpec,
) -> float:
    values: list[float] = []
    for nb in neighbors(combo, spec):
        cell = cells[nb]
        assert cell.expected_nt is not None
        values.append(cell.expected_nt)
    if not values:
        # Degenerate grid where every axis has one value: no Hamming-1
        # neighbors exist, so rank the lone plateau cell by its own EV.
        own = cells[combo].expected_nt
        assert own is not None
        return own
    return min(values)


def _default_rank(combo: StrategyCombo) -> tuple[int | float, ...]:
    return (
        0 if combo.entry_price == DEFAULT_COMBO.entry_price else 1,
        abs(combo.min_points - DEFAULT_COMBO.min_points),
        abs(combo.stop_buffer - DEFAULT_COMBO.stop_buffer),
        0 if combo.take_profit == DEFAULT_COMBO.take_profit else 1,
        0 if combo.require_external == DEFAULT_COMBO.require_external else 1,
        0 if combo.max_hold_bars == DEFAULT_COMBO.max_hold_bars else 1,
    )


def elect(
    plateau: tuple[StrategyCombo, ...],
    cells: dict[StrategyCombo, CellMetrics],
    spec: GridSpec,
) -> StrategyCombo | None:
    if not plateau:
        return None

    def key(combo: StrategyCombo) -> tuple[object, ...]:
        cell = cells[combo]
        return (
            -_worst_neighbor_ev(combo, cells, spec),
            -cell.n_trades,
            *_default_rank(combo),
        )

    return min(plateau, key=key)


def decay(is_expected_nt: float, oos_expected_nt: float) -> float:
    return (is_expected_nt - oos_expected_nt) / is_expected_nt


def evaluate_gates(
    *,
    smoke: bool,
    oos_dates_empty: bool,
    plateau: tuple[StrategyCombo, ...],
    elected: StrategyCombo | None,
    elected_is: CellMetrics | None,
    elected_oos: CellMetrics | None,
    elected_slip2_oos: CellMetrics | None,
    elected_opt_oos: CellMetrics | None,
    full_elected_p90: float | None,
    initial_margin_nt: float,
) -> GateReport:
    decay_value: float | None = None
    if (
        elected_is is not None
        and elected_is.expected_nt is not None
        and elected_is.expected_nt > 0
        and elected_oos is not None
        and elected_oos.expected_nt is not None
    ):
        decay_value = decay(elected_is.expected_nt, elected_oos.expected_nt)

    plateau_ok = bool(plateau) and elected is not None
    oos_n_ok = (
        not oos_dates_empty and elected_oos is not None and elected_oos.n_trades >= MIN_OOS_TRADES
    )
    oos_ev_ok = (
        elected_oos is not None
        and elected_oos.expected_nt is not None
        and elected_oos.expected_nt > 0
    )
    decay_ok = (
        elected_is is not None
        and elected_is.expected_nt is not None
        and elected_is.expected_nt > 0
        and decay_value is not None
        and decay_value < 0.5
    )
    slip2_ok = (
        elected_slip2_oos is not None
        and elected_slip2_oos.expected_nt is not None
        and elected_slip2_oos.expected_nt > 0
    )
    n_cons = elected_oos.n_trades if elected_oos is not None else None
    n_opt = elected_opt_oos.n_trades if elected_opt_oos is not None else None
    fill_count_ok = n_cons is not None and n_opt is not None and n_cons <= n_opt
    opt_ev = elected_opt_oos.expected_nt if elected_opt_oos is not None else None

    checks = (
        GateCheck(
            "is_plateau_and_elect",
            plateau_ok,
            "IS plateau non-empty and elect succeeded" if plateau_ok else "no plateau/elect",
            True,
        ),
        GateCheck(
            "elected_oos_n",
            oos_n_ok,
            f"elected OOS n={elected_oos.n_trades if elected_oos else 0}"
            + (" empty OOS dates" if oos_dates_empty else ""),
            True,
        ),
        GateCheck(
            "elected_oos_expected_nt",
            oos_ev_ok,
            f"elected OOS expected_nt={elected_oos.expected_nt if elected_oos else None}",
            True,
        ),
        GateCheck(
            "elected_decay",
            decay_ok,
            f"decay={decay_value}",
            True,
        ),
        GateCheck(
            "elected_slip2_oos_expected_nt",
            slip2_ok,
            f"slip2 OOS expected_nt={elected_slip2_oos.expected_nt if elected_slip2_oos else None}",
            True,
        ),
        GateCheck(
            "optimistic_oos_ev",
            opt_ev is not None,
            f"elected optimistic OOS expected_nt={opt_ev}",
            False,
        ),
        GateCheck(
            "n_conservative_le_optimistic",
            fill_count_ok,
            f"n_conservative={n_cons} n_optimistic={n_opt}",
            False,
        ),
    )
    hard_ok = all(check.passed for check in checks if check.hard)
    if smoke:
        verdict: GateVerdict = "smoke"
    elif hard_ok:
        verdict = "go"
    else:
        verdict = "no_go"
    capital = None
    if full_elected_p90 is not None:
        capital = initial_margin_nt + full_elected_p90
    return GateReport(verdict=verdict, checks=checks, decay=decay_value, capital_nt=capital)


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    rank = (pct / 100.0) * (len(sorted_vals) - 1)
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return sorted_vals[lo]
    weight = rank - lo
    return sorted_vals[lo] * (1.0 - weight) + sorted_vals[hi] * weight


def sequence_mdd(pnls: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    mdd = 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        mdd = max(mdd, peak - equity)
    return mdd


def monte_carlo_mdd(
    pnls: list[float],
    *,
    draws: int = MC_DRAWS,
    seed: int = 42,
) -> tuple[float, float, float]:
    if not pnls:
        return (0.0, 0.0, 0.0)
    rng = random.Random(seed)
    mdds: list[float] = []
    for _ in range(draws):
        shuffled = list(pnls)
        rng.shuffle(shuffled)
        mdds.append(sequence_mdd(shuffled))
    mdds.sort()
    return (_percentile(mdds, 50), _percentile(mdds, 90), _percentile(mdds, 99))


def format_profit_factor(value: float) -> str:
    if math.isinf(value):
        return "inf"
    return f"{value}"


def format_month(year_month: tuple[int, int]) -> str:
    return f"{year_month[0]:04d}-{year_month[1]:02d}"


def source_files(kbars_path: Path, start: date, end: date) -> list[str]:
    root = kbars_path
    names: list[str] = []
    current = start
    while current <= end:
        name = f"TMFR1_kbars_{current.isoformat()}.csv"
        if (root / name).is_file():
            names.append(name)
        current += timedelta(days=1)
    return names


__all__ = [
    "DEFAULT_COMBO",
    "CellMetrics",
    "FoldStatus",
    "GateCheck",
    "GateReport",
    "GateVerdict",
    "GridSpec",
    "MIN_IS_TRADES",
    "MIN_OOS_TRADES",
    "MC_DRAWS",
    "RollingFold",
    "SplitName",
    "StrategyCombo",
    "WindowBounds",
    "add_month",
    "bars_through",
    "calendar_month_buckets",
    "day_session_dates",
    "decay",
    "elect",
    "evaluate_gates",
    "expected_nt",
    "fold_status",
    "format_month",
    "format_profit_factor",
    "is_profitable",
    "monte_carlo_mdd",
    "neighbors",
    "plateau_combos",
    "rolling_folds",
    "sequence_mdd",
    "source_files",
    "split_70_30",
    "window_bounds",
]
