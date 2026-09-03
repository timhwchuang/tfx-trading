from __future__ import annotations

from datetime import date, datetime

from tfx_trading.backtest.analysis import (
    DEFAULT_COMBO,
    MIN_IS_TRADES,
    MIN_OOS_TRADES,
    CellMetrics,
    GridSpec,
    StrategyCombo,
    calendar_month_buckets,
    day_session_dates,
    decay,
    elect,
    evaluate_gates,
    expected_nt,
    fold_status,
    monte_carlo_mdd,
    neighbors,
    plateau_combos,
    rolling_folds,
    sequence_mdd,
    split_70_30,
    window_bounds,
)
from tfx_trading.kbar import KBar


def _tiny_spec() -> GridSpec:
    return GridSpec(
        entry_price=("top",),
        min_points=(15.0, 20.0, 30.0),
        stop_buffer=(5.0,),
        take_profit=("2R",),
        require_external=(False,),
        max_hold_bars=(10_000,),
    )


def _combo(min_points: float) -> StrategyCombo:
    return StrategyCombo(
        entry_price="top",
        min_points=min_points,
        stop_buffer=5.0,
        take_profit="2R",
        require_external=False,
        max_hold_bars=10_000,
    )


def _cell(
    combo: StrategyCombo,
    n: int,
    ev: float | None,
    *,
    split: str = "is",
) -> CellMetrics:
    return CellMetrics(
        combo=combo,
        n_trades=n,
        expected_nt=ev,
        expected_r=ev,
        total_pnl_nt=(ev * n) if ev is not None else 0.0,
        mdd_nt=10.0,
        win_rate=0.5,
        profit_factor=1.2,
        max_margin_nt=10_000.0,
        fill_mode="conservative",
        slippage_ticks=1,
        split=split,  # type: ignore[arg-type]
    )


def _bar(ts: datetime, price: float = 20000.0) -> KBar:
    return KBar(
        timestamp=ts,
        open=price,
        high=price,
        low=price,
        close=price,
        volume=1,
        amount=price,
    )


def test_gridspec_size_is_216() -> None:
    assert len(GridSpec().combos()) == 216


def test_split_70_30_floor() -> None:
    dates = [date(2026, 1, d) for d in range(1, 11)]
    is_dates, oos_dates = split_70_30(dates)
    assert len(is_dates) == 7
    assert len(oos_dates) == 3
    one = [date(2026, 1, 1)]
    is_one, oos_one = split_70_30(one)
    assert is_one == []
    assert oos_one == one


def test_max_hold_24_neighbors_include_10000() -> None:
    spec = GridSpec()
    combo = DEFAULT_COMBO
    held = StrategyCombo(
        entry_price=combo.entry_price,
        min_points=combo.min_points,
        stop_buffer=combo.stop_buffer,
        take_profit=combo.take_profit,
        require_external=combo.require_external,
        max_hold_bars=24,
    )
    holds = {nb.max_hold_bars for nb in neighbors(held, spec) if nb.max_hold_bars != 24}
    assert 12 in holds
    assert 10_000 in holds


def test_neighbor_n_under_30_center_out_of_plateau() -> None:
    spec = _tiny_spec()
    c15, c20, c30 = _combo(15.0), _combo(20.0), _combo(30.0)
    cells = {
        c15: _cell(c15, 10, 5.0),
        c20: _cell(c20, 40, 5.0),
        c30: _cell(c30, 40, 5.0),
    }
    assert c20 not in plateau_combos(cells, spec)


def test_elect_ignores_oos_metrics() -> None:
    spec = _tiny_spec()
    c15, c20, c30 = _combo(15.0), _combo(20.0), _combo(30.0)
    is_cells = {
        c15: _cell(c15, 40, 1.0),
        c20: _cell(c20, 40, 8.0),
        c30: _cell(c30, 50, 2.0),
    }
    plateau = plateau_combos(is_cells, spec)
    assert set(plateau) == {c15, c20, c30}
    winner = elect(plateau, is_cells, spec)
    assert winner == c30
    oos_better_15 = _cell(c15, 40, 99.0, split="oos")
    still = elect(plateau, is_cells, spec)
    assert still == c30
    assert oos_better_15.expected_nt == 99.0


def test_gates_use_elected_oos_not_other_plateau_cell() -> None:
    spec = _tiny_spec()
    c15, c20, c30 = _combo(15.0), _combo(20.0), _combo(30.0)
    is_cells = {
        c15: _cell(c15, 40, 1.0),
        c20: _cell(c20, 40, 8.0),
        c30: _cell(c30, 50, 2.0),
    }
    plateau = plateau_combos(is_cells, spec)
    elected = elect(plateau, is_cells, spec)
    assert elected == c30
    elected_oos = _cell(c30, 5, 3.0, split="oos")
    other_oos = _cell(c15, 40, 9.0, split="oos")
    report = evaluate_gates(
        smoke=False,
        oos_dates_empty=False,
        plateau=plateau,
        elected=elected,
        elected_is=is_cells[c30],
        elected_oos=elected_oos,
        elected_slip2_oos=_cell(c30, 12, 1.0, split="oos"),
        elected_opt_oos=_cell(c30, 8, 1.0, split="oos"),
        full_elected_p90=100.0,
        initial_margin_nt=35_050.0,
    )
    assert report.verdict == "no_go"
    n_check = next(c for c in report.checks if c.name == "elected_oos_n")
    assert n_check.passed is False
    assert other_oos.n_trades >= MIN_OOS_TRADES


def test_empty_oos_dates_no_go() -> None:
    report = evaluate_gates(
        smoke=False,
        oos_dates_empty=True,
        plateau=(),
        elected=None,
        elected_is=None,
        elected_oos=None,
        elected_slip2_oos=None,
        elected_opt_oos=None,
        full_elected_p90=None,
        initial_margin_nt=1.0,
    )
    assert report.verdict == "no_go"
    n_check = next(c for c in report.checks if c.name == "elected_oos_n")
    assert n_check.passed is False


def test_decay_formula_oos_better_passes() -> None:
    assert decay(2.0, 1.2) == 0.4
    assert decay(2.0, 3.0) == -0.5
    c = DEFAULT_COMBO
    report = evaluate_gates(
        smoke=False,
        oos_dates_empty=False,
        plateau=(c,),
        elected=c,
        elected_is=_cell(c, 40, 2.0),
        elected_oos=_cell(c, 12, 3.0, split="oos"),
        elected_slip2_oos=_cell(c, 12, 1.0, split="oos"),
        elected_opt_oos=_cell(c, 12, 3.0, split="oos"),
        full_elected_p90=50.0,
        initial_margin_nt=10.0,
    )
    assert report.decay == -0.5
    decay_check = next(ch for ch in report.checks if ch.name == "elected_decay")
    assert decay_check.passed is True
    assert report.verdict == "go"


def test_decay_fail_when_over_half() -> None:
    c = DEFAULT_COMBO
    report = evaluate_gates(
        smoke=False,
        oos_dates_empty=False,
        plateau=(c,),
        elected=c,
        elected_is=_cell(c, 40, 2.0),
        elected_oos=_cell(c, 12, 0.8, split="oos"),
        elected_slip2_oos=_cell(c, 12, 1.0, split="oos"),
        elected_opt_oos=_cell(c, 12, 1.0, split="oos"),
        full_elected_p90=50.0,
        initial_margin_nt=10.0,
    )
    assert report.decay == 0.6
    assert report.verdict == "no_go"


def test_rolling_calendar_not_observed_adjacency() -> None:
    dates = [
        date(2026, 1, 15),
        date(2026, 2, 15),
        date(2026, 5, 15),
        date(2026, 6, 15),
    ]
    assert calendar_month_buckets(dates) == [
        (2026, 1),
        (2026, 2),
        (2026, 5),
        (2026, 6),
    ]
    folds = rolling_folds(dates)
    april = next(f for f in folds if f.test_month == (2026, 4))
    assert april.train_months == ((2026, 1), (2026, 2), (2026, 3))
    assert date(2026, 5, 15) not in april.train_dates


def test_rolling_no_train_sessions_insufficient_sample() -> None:
    spec = _tiny_spec()
    dates = [
        date(2026, 1, 10),
        date(2026, 5, 10),
        date(2026, 6, 10),
        date(2026, 7, 10),
    ]
    folds = rolling_folds(dates)
    may = next(f for f in folds if f.test_month == (2026, 5))
    assert may.train_dates == ()
    assert fold_status(may, None, spec) == "insufficient_sample"


def test_empty_plateau_distinct_from_insufficient_sample() -> None:
    spec = _tiny_spec()
    dates = [date(2026, 1, 15), date(2026, 2, 15), date(2026, 3, 15), date(2026, 4, 15)]
    fold = rolling_folds(dates)[0]
    c15, c20, c30 = _combo(15.0), _combo(20.0), _combo(30.0)
    isolated = {
        c15: _cell(c15, 10, -1.0),
        c20: _cell(c20, 40, 5.0),
        c30: _cell(c30, 10, -1.0),
    }
    assert fold_status(fold, isolated, spec) == "empty_plateau"
    short = {
        c15: _cell(c15, 5, 1.0),
        c20: _cell(c20, 5, 1.0),
        c30: _cell(c30, 5, 1.0),
    }
    assert fold_status(fold, short, spec) == "insufficient_sample"
    good = {
        c15: _cell(c15, 40, 1.0),
        c20: _cell(c20, 40, 2.0),
        c30: _cell(c30, 40, 1.0),
    }
    assert fold_status(fold, good, spec) == "elected"
    assert elect(plateau_combos(good, spec), good, spec) == c15


def test_rolling_does_not_flip_go() -> None:
    c = DEFAULT_COMBO
    report = evaluate_gates(
        smoke=False,
        oos_dates_empty=False,
        plateau=(c,),
        elected=c,
        elected_is=_cell(c, 40, 2.0),
        elected_oos=_cell(c, 12, 1.5, split="oos"),
        elected_slip2_oos=_cell(c, 12, 1.0, split="oos"),
        elected_opt_oos=_cell(c, 12, 1.5, split="oos"),
        full_elected_p90=80.0,
        initial_margin_nt=10.0,
    )
    assert report.verdict == "go"


def test_smoke_never_go() -> None:
    c = DEFAULT_COMBO
    report = evaluate_gates(
        smoke=True,
        oos_dates_empty=False,
        plateau=(c,),
        elected=c,
        elected_is=_cell(c, 40, 2.0),
        elected_oos=_cell(c, 12, 1.5, split="oos"),
        elected_slip2_oos=_cell(c, 12, 1.0, split="oos"),
        elected_opt_oos=_cell(c, 12, 1.5, split="oos"),
        full_elected_p90=80.0,
        initial_margin_nt=10.0,
    )
    assert report.verdict == "smoke"


def test_monte_carlo_seeded_and_path_in_range() -> None:
    pnls = [10.0, -4.0, 6.0, -8.0, 3.0]
    a = monte_carlo_mdd(pnls, draws=200, seed=42)
    b = monte_carlo_mdd(pnls, draws=200, seed=42)
    assert a == b
    path = sequence_mdd(pnls)
    assert a[0] <= a[1] <= a[2]
    assert path <= a[2] + 1e-9


def test_expected_nt_empty_when_zero_trades() -> None:
    assert expected_nt(0.0, 0) is None
    assert expected_nt(10.0, 2) == 5.0


def test_window_end_includes_flatten_fill_bar() -> None:
    bars = [
        _bar(datetime(2026, 8, 17, 8, 50)),
        _bar(datetime(2026, 8, 17, 13, 40)),
        _bar(datetime(2026, 8, 17, 13, 41)),
    ]
    bounds = window_bounds(bars, [date(2026, 8, 17)])
    assert bounds is not None
    assert bounds.end == datetime(2026, 8, 17, 13, 41)
    assert bounds.start == datetime(2026, 8, 17, 0, 0)


def test_day_session_dates_ignore_night() -> None:
    bars = [
        _bar(datetime(2026, 8, 17, 8, 50)),
        _bar(datetime(2026, 8, 17, 16, 0)),
        _bar(datetime(2026, 8, 18, 8, 50)),
    ]
    assert day_session_dates(bars) == [date(2026, 8, 17), date(2026, 8, 18)]


def test_full_tape_window_starts_before_oos() -> None:
    days = [date(2026, 8, d) for d in range(10, 14)]
    bars = [_bar(datetime(d.year, d.month, d.day, 8, 50)) for d in days]
    bars.append(_bar(datetime(2026, 8, 13, 13, 41)))
    is_dates, oos_dates = split_70_30(days)
    full = window_bounds(bars, days)
    oos = window_bounds(bars, oos_dates)
    assert full is not None and oos is not None
    assert is_dates
    assert full.start == datetime(2026, 8, 10, 0, 0)
    assert oos.start == datetime.combine(oos_dates[0], datetime.min.time())
    assert full.start < oos.start


def test_short_tape_no_rolling_folds() -> None:
    dates = [date(2026, 1, 5), date(2026, 2, 5), date(2026, 3, 5)]
    assert rolling_folds(dates) == []
    assert MIN_IS_TRADES == 30
