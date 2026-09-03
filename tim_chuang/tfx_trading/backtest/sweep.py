from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from typing import TextIO

from tfx_trading.backtest.analysis import (
    CellMetrics,
    FillModeName,
    GateReport,
    GridSpec,
    RollingFold,
    SplitName,
    StrategyCombo,
    WindowBounds,
    bars_through,
    calendar_month_buckets,
    day_session_dates,
    elect,
    evaluate_gates,
    expected_nt,
    fold_status,
    format_month,
    format_profit_factor,
    monte_carlo_mdd,
    plateau_combos,
    rolling_folds,
    source_files,
    split_70_30,
    window_bounds,
)
from tfx_trading.backtest.config import BacktestConfig, FillMode
from tfx_trading.backtest.engine import run
from tfx_trading.backtest.ledger import BacktestResult, RunMeta, resolve_git_hash
from tfx_trading.bar_reader import BarReader
from tfx_trading.calendar import TradeCalendar
from tfx_trading.indicators.fvg import Fvg
from tfx_trading.indicators.fvg import compute as fvg_compute
from tfx_trading.indicators.smc import SmcLevels
from tfx_trading.indicators.smc import compute as smc_compute
from tfx_trading.kbar import KBar
from tfx_trading.strategy.protocol import DecisionContext
from tfx_trading.strategy.setup_a import (
    _EMPTY_SMC,
    SetupAParams,
    _evaluate,
    _skip_indicators,
    load_setup_a_params,
)
from tfx_trading.trading.costs import CostConfig, load_trading_config
from tfx_trading.trading.models import Intent

_DEFAULT_KBARS = Path(__file__).resolve().parent.parent / "kbars_data"
_FILL_MODES: tuple[FillMode, ...] = ("conservative", "optimistic")
_SLIPPAGE_TICKS: tuple[int, ...] = (0, 1, 2, 3)
IndicatorCache = dict[tuple[datetime, int], tuple[SmcLevels, list[Fvg]]]


class CachedSetupA:
    """SetupA.decide with shared SMC/FVG cache and option-A warmup.

    Cache values are stripped to what ``_evaluate`` actually reads: ``swings``
    is emptied and filled FVGs are dropped. Both grow O(prefix) per entry
    (O(K²) across a tape-wide cache) while ``_evaluate`` never consumes them —
    ``_select_active_fvg`` / ``_matching_live_fvg`` filter to
    untouched/mitigated and nothing reads ``smc.swings``. If ``_evaluate``
    starts reading either, this strip must be removed.
    """

    def __init__(
        self,
        params: SetupAParams,
        calendar: TradeCalendar,
        cache: IndicatorCache,
        window_start: datetime,
    ) -> None:
        self._params = params
        self._calendar = calendar
        self._cache = cache
        self._window_start = window_start

    def decide(self, ctx: DecisionContext) -> list[Intent]:
        if ctx.bar_1m.timestamp < self._window_start:
            return []
        if _skip_indicators(ctx, self._params, self._calendar):
            return _evaluate(_EMPTY_SMC, [], ctx, self._params, self._calendar)
        bars = list(ctx.bars_5m)
        key = (bars[-1].timestamp, len(bars)) if bars else (ctx.bar_1m.timestamp, 0)
        if key not in self._cache:
            smc = replace(smc_compute(bars), swings=[])
            live = [f for f in fvg_compute(bars, min_points=0.0) if f.state != "filled"]
            self._cache[key] = (smc, live)
        smc, fvgs = self._cache[key]
        return _evaluate(smc, fvgs, ctx, self._params, self._calendar)


def metrics_from_result(
    combo: StrategyCombo,
    fill_mode: FillModeName,
    slippage_ticks: int,
    split: SplitName | None,
    result: BacktestResult,
) -> CellMetrics:
    n_trades = len(result.trades)
    return CellMetrics(
        combo=combo,
        n_trades=n_trades,
        expected_nt=expected_nt(result.total_pnl_nt, n_trades),
        expected_r=result.expected_r,
        total_pnl_nt=result.total_pnl_nt,
        mdd_nt=result.mdd_nt,
        win_rate=result.win_rate,
        profit_factor=result.profit_factor,
        max_margin_nt=result.max_margin_nt,
        fill_mode=fill_mode,
        slippage_ticks=slippage_ticks,
        split=split,
    )


def _combo_fields(combo: StrategyCombo) -> dict[str, object]:
    return {
        "entry_price": combo.entry_price,
        "min_points": combo.min_points,
        "stop_buffer": combo.stop_buffer,
        "take_profit": combo.take_profit,
        "require_external": combo.require_external,
        "max_hold_bars": combo.max_hold_bars,
    }


def _row(metrics: CellMetrics) -> dict[str, object]:
    ev = "" if metrics.expected_nt is None else metrics.expected_nt
    er = "" if metrics.expected_r is None else metrics.expected_r
    return {
        **_combo_fields(metrics.combo),
        "fill_mode": metrics.fill_mode,
        "slippage_ticks": metrics.slippage_ticks,
        "split": metrics.split if metrics.split is not None else "",
        "n_trades": metrics.n_trades,
        "expected_nt": ev,
        "expected_r": er,
        "total_pnl_nt": metrics.total_pnl_nt,
        "mdd_nt": metrics.mdd_nt,
        "win_rate": metrics.win_rate,
        "profit_factor": format_profit_factor(metrics.profit_factor),
        "max_margin_nt": metrics.max_margin_nt,
    }


_GRID_FIELDS = [
    "entry_price",
    "min_points",
    "stop_buffer",
    "take_profit",
    "require_external",
    "max_hold_bars",
    "fill_mode",
    "slippage_ticks",
    "split",
    "n_trades",
    "expected_nt",
    "expected_r",
    "total_pnl_nt",
    "mdd_nt",
    "win_rate",
    "profit_factor",
    "max_margin_nt",
]


def _write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_trade_log(result: BacktestResult, path: Path, combo: StrategyCombo) -> None:
    result.write_trade_log(path)
    body = path.read_text(encoding="utf-8")
    lines = [f"# {key}: {value}" for key, value in _combo_fields(combo).items()]
    path.write_text("\n".join(lines) + "\n" + body, encoding="utf-8")


def _gates_md(report: GateReport, rolling_lines: list[str]) -> str:
    lines = [
        f"# Phase 4 gates: {report.verdict}",
        "",
        "## Hard (70/30 elected only)",
        "",
    ]
    for check in report.checks:
        if not check.hard:
            continue
        mark = "x" if check.passed else " "
        lines.append(f"- [{mark}] `{check.name}` — {check.detail}")
    lines.extend(["", "## Diagnostic (does not flip go/no_go)", ""])
    for check in report.checks:
        if check.hard:
            continue
        mark = "x" if check.passed else " "
        lines.append(f"- [{mark}] `{check.name}` — {check.detail}")
    lines.extend(["", "## Rolling", ""])
    if rolling_lines:
        lines.extend(f"- {line}" for line in rolling_lines)
    else:
        lines.append("- (none)")
    if report.capital_nt is not None:
        capital_line = (
            "Phase 5 funding uses `full_elected` P90: "
            f"`capital_nt ≈ initial_margin_nt + P90` = {report.capital_nt}."
        )
    else:
        capital_line = "No elected combo / full_elected MC — capital estimate not available."
    lines.extend(
        [
            "",
            "## Capital",
            "",
            capital_line,
            "OOS MC is robustness only.",
            "",
            f"decay = {report.decay}",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


class SweepRunner:
    def __init__(
        self,
        bars: list[KBar],
        *,
        spec: GridSpec,
        base_params: SetupAParams,
        cost: CostConfig,
        calendar: TradeCalendar,
        source: str,
        seed: int,
        max_combos: int | None,
        combos: tuple[StrategyCombo, ...],
        log: TextIO,
        start: date | None = None,
        end: date | None = None,
    ) -> None:
        self._bars = bars
        self._spec = spec
        self._base = base_params
        self._cost = cost
        self._calendar = calendar
        self._source = source
        self._seed = seed
        self._max_combos = max_combos
        self._smoke = max_combos is not None
        self._combos = combos
        self._log = log
        self._start = start
        self._end = end
        self._cache: IndicatorCache = {}
        self._day_dates = day_session_dates(bars)
        self._meta = RunMeta(source_files=source)

    def _run(
        self,
        combo: StrategyCombo,
        fill_mode: FillMode,
        slippage_ticks: int,
        bounds: WindowBounds,
        split: SplitName | None,
        label: str,
    ) -> tuple[CellMetrics, BacktestResult]:
        print(
            f"{label} {combo.entry_price} min={combo.min_points} "
            f"buf={combo.stop_buffer} tp={combo.take_profit} "
            f"ext={combo.require_external} hold={combo.max_hold_bars} "
            f"{fill_mode} slip={slippage_ticks}",
            file=self._log,
        )
        params = combo.to_params(self._base)
        strategy = CachedSetupA(params, self._calendar, self._cache, bounds.start)
        cost = replace(self._cost, slippage_ticks=slippage_ticks)
        result = run(
            bars_through(self._bars, bounds.end),
            strategy,
            cost,
            BacktestConfig(fill_mode=fill_mode),
            meta=self._meta,
        )
        # The equity curve has one point per 1m bar; retaining it across hundreds
        # of grid cells costs GBs on a multi-month tape and nothing downstream
        # (metrics, MC, trade logs) reads it.
        result = replace(result, equity_curve=())
        metrics = metrics_from_result(combo, fill_mode, slippage_ticks, split, result)
        return metrics, result

    def execute(self, out_dir: Path) -> GateReport:
        out_dir.mkdir(parents=True, exist_ok=True)
        is_dates, oos_dates = split_70_30(self._day_dates)
        is_bounds = window_bounds(self._bars, is_dates)
        oos_bounds = window_bounds(self._bars, oos_dates)
        full_bounds = window_bounds(self._bars, self._day_dates)
        oos_empty = not oos_dates or oos_bounds is None

        is_cons: dict[StrategyCombo, CellMetrics] = {}
        is_cons_results: dict[StrategyCombo, BacktestResult] = {}
        is_rows: list[CellMetrics] = []
        if is_bounds is None:
            report = evaluate_gates(
                smoke=self._smoke,
                oos_dates_empty=oos_empty,
                plateau=(),
                elected=None,
                elected_is=None,
                elected_oos=None,
                elected_slip2_oos=None,
                elected_opt_oos=None,
                full_elected_p90=None,
                initial_margin_nt=self._cost.initial_margin_nt,
            )
            self._write_outputs(
                out_dir,
                is_rows=[],
                oos_rows=[],
                isoos_rows=[],
                slip_rows=[],
                wf_rows=[],
                report=report,
                rolling_lines=["no day-session dates"],
                elected=None,
                mc_rows=[],
                is_dates=is_dates,
                oos_dates=oos_dates,
            )
            return report

        n_runs = len(self._combos) * len(_FILL_MODES)
        i = 0
        for combo in self._combos:
            for fill_mode in _FILL_MODES:
                i += 1
                print(f"IS {i}/{n_runs}", file=self._log)
                metrics, result = self._run(combo, fill_mode, 1, is_bounds, "is", "IS")
                is_rows.append(metrics)
                if fill_mode == "conservative":
                    is_cons[combo] = metrics
                    is_cons_results[combo] = result

        plateau = plateau_combos(is_cons, self._spec)
        elected = elect(plateau, is_cons, self._spec)

        oos_cons: dict[StrategyCombo, tuple[CellMetrics, BacktestResult]] = {}
        oos_rows: list[CellMetrics] = []
        elected_opt: CellMetrics | None = None
        elected_oos_result: BacktestResult | None = None
        if oos_bounds is not None and plateau:
            for combo in plateau:
                metrics, result = self._run(combo, "conservative", 1, oos_bounds, "oos", "OOS")
                oos_cons[combo] = (metrics, result)
                oos_rows.append(metrics)
                if elected is not None and combo == elected:
                    elected_oos_result = result
            if elected is not None:
                elected_opt, _opt_result = self._run(
                    elected, "optimistic", 1, oos_bounds, "oos", "OOS-opt"
                )

        slip_rows: list[CellMetrics] = []
        slip2: CellMetrics | None = None
        slip2_result: BacktestResult | None = None
        if elected is not None and oos_bounds is not None:
            reused: dict[tuple[FillMode, int], CellMetrics] = {}
            if elected in oos_cons:
                reused[("conservative", 1)] = oos_cons[elected][0]
            if elected_opt is not None:
                reused[("optimistic", 1)] = elected_opt
            for fill_mode in _FILL_MODES:
                for ticks in _SLIPPAGE_TICKS:
                    cached = reused.get((fill_mode, ticks))
                    if cached is not None:
                        slip_rows.append(cached)
                        if fill_mode == "conservative" and ticks == 2:
                            slip2 = cached
                        continue
                    metrics, result = self._run(
                        elected, fill_mode, ticks, oos_bounds, "oos", "SLIP"
                    )
                    slip_rows.append(metrics)
                    if fill_mode == "conservative" and ticks == 2:
                        slip2 = metrics
                        slip2_result = result

        full_result: BacktestResult | None = None
        if elected is not None and full_bounds is not None:
            _full_metrics, full_result = self._run(
                elected, "conservative", 1, full_bounds, None, "FULL"
            )

        oos_pnls = (
            [t.pnl_nt for t in elected_oos_result.trades] if elected_oos_result is not None else []
        )
        full_pnls = [t.pnl_nt for t in full_result.trades] if full_result is not None else []
        oos_mc = monte_carlo_mdd(oos_pnls, seed=self._seed)
        full_mc = monte_carlo_mdd(full_pnls, seed=self._seed)
        mc_rows = [
            {
                "label": "oos",
                "p50": oos_mc[0],
                "p90": oos_mc[1],
                "p99": oos_mc[2],
                "n_trades": len(oos_pnls),
            },
            {
                "label": "full_elected",
                "p50": full_mc[0],
                "p90": full_mc[1],
                "p99": full_mc[2],
                "n_trades": len(full_pnls),
            },
        ]

        elected_is = is_cons.get(elected) if elected is not None else None
        elected_oos = oos_cons[elected][0] if elected is not None and elected in oos_cons else None
        report = evaluate_gates(
            smoke=self._smoke,
            oos_dates_empty=oos_empty,
            plateau=plateau,
            elected=elected,
            elected_is=elected_is,
            elected_oos=elected_oos,
            elected_slip2_oos=slip2,
            elected_opt_oos=elected_opt,
            full_elected_p90=full_mc[1] if full_result is not None else None,
            initial_margin_nt=self._cost.initial_margin_nt,
        )
        wf_rows, rolling_lines = self._rolling(elected, oos_bounds is not None)
        isoos_rows = self._isoos_rows(plateau, is_cons, oos_cons, elected_opt)
        self._write_outputs(
            out_dir,
            is_rows=is_rows,
            oos_rows=oos_rows,
            isoos_rows=isoos_rows,
            slip_rows=slip_rows,
            wf_rows=wf_rows,
            report=report,
            rolling_lines=rolling_lines,
            elected=elected,
            mc_rows=mc_rows,
            is_dates=is_dates,
            oos_dates=oos_dates,
        )
        if elected is not None and elected in is_cons_results:
            _write_trade_log(is_cons_results[elected], out_dir / "trades_elected_is.csv", elected)
        if elected is not None and elected_oos_result is not None:
            _write_trade_log(elected_oos_result, out_dir / "trades_elected_oos.csv", elected)
        if elected is not None and slip2_result is not None:
            _write_trade_log(slip2_result, out_dir / "trades_elected_slip2_oos.csv", elected)
        return report

    def _isoos_rows(
        self,
        plateau: tuple[StrategyCombo, ...],
        is_cons: dict[StrategyCombo, CellMetrics],
        oos_cons: dict[StrategyCombo, tuple[CellMetrics, BacktestResult]],
        elected_opt: CellMetrics | None,
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for combo in plateau:
            is_cell = is_cons[combo]
            row = {f"is_{k}": v for k, v in _row(is_cell).items()}
            if combo in oos_cons:
                oos_cell = oos_cons[combo][0]
                row.update({f"oos_{k}": v for k, v in _row(oos_cell).items()})
            rows.append(row)
        if elected_opt is not None:
            rows.append({f"opt_oos_{k}": v for k, v in _row(elected_opt).items()})
        return rows

    def _rolling(
        self,
        frozen: StrategyCombo | None,
        _has_oos: bool,
    ) -> tuple[list[dict[str, object]], list[str]]:
        rows: list[dict[str, object]] = []
        lines: list[str] = []
        if self._smoke:
            rows.append(
                {
                    "test_month": "",
                    "train_months": "",
                    "status": "partial_grid",
                    "note": "--max-combos smoke run",
                }
            )
            lines.append("partial_grid (--max-combos smoke run)")
            return rows, lines
        buckets = calendar_month_buckets(self._day_dates)
        if len(buckets) < 4:
            rows.append(
                {
                    "test_month": "",
                    "train_months": "",
                    "status": "skipped",
                    "note": "fewer than 4 calendar month buckets",
                }
            )
            lines.append("skipped: fewer than 4 calendar month buckets")
            return rows, lines
        for fold in rolling_folds(self._day_dates):
            rows.append(self._one_fold(fold, frozen))
            last = rows[-1]
            lines.append(
                f"{last.get('test_month')} status={last.get('status')} "
                f"frozen_n={last.get('frozen_test_n_trades')}"
            )
        return rows, lines

    def _one_fold(
        self,
        fold: RollingFold,
        frozen: StrategyCombo | None,
    ) -> dict[str, object]:
        train_label = ",".join(format_month(m) for m in fold.train_months)
        test_label = format_month(fold.test_month)
        row: dict[str, object] = {
            "test_month": test_label,
            "train_months": train_label,
            "status": "",
            "note": "",
            "fold_entry_price": "",
            "fold_min_points": "",
            "fold_stop_buffer": "",
            "fold_take_profit": "",
            "fold_require_external": "",
            "fold_max_hold_bars": "",
            "fold_test_n_trades": "",
            "fold_test_expected_nt": "",
            "fold_test_mdd_nt": "",
            "frozen_test_n_trades": "",
            "frozen_test_expected_nt": "",
            "frozen_test_mdd_nt": "",
        }
        train_cells: dict[StrategyCombo, CellMetrics] | None
        if not fold.train_dates:
            train_cells = None
        else:
            train_bounds = window_bounds(self._bars, list(fold.train_dates))
            if train_bounds is None:
                train_cells = None
            else:
                # Fold plateau/elect only ever reads conservative cells; nothing
                # diagnostic consumes fold optimistic, so skip that half.
                train_cells = {}
                n = len(self._combos)
                for i, combo in enumerate(self._combos, start=1):
                    print(
                        f"FOLD {test_label} train {i}/{n}",
                        file=self._log,
                    )
                    metrics, _result = self._run(
                        combo, "conservative", 1, train_bounds, "is", f"WF-{test_label}"
                    )
                    train_cells[combo] = metrics
        status = fold_status(fold, train_cells, self._spec)
        row["status"] = status
        fold_winner: StrategyCombo | None = None
        if status == "elected" and train_cells is not None:
            plateau = plateau_combos(train_cells, self._spec)
            fold_winner = elect(plateau, train_cells, self._spec)
        if fold_winner is not None:
            row.update(
                {
                    "fold_entry_price": fold_winner.entry_price,
                    "fold_min_points": fold_winner.min_points,
                    "fold_stop_buffer": fold_winner.stop_buffer,
                    "fold_take_profit": fold_winner.take_profit,
                    "fold_require_external": fold_winner.require_external,
                    "fold_max_hold_bars": fold_winner.max_hold_bars,
                }
            )
        test_bounds = window_bounds(self._bars, list(fold.test_dates)) if fold.test_dates else None
        if test_bounds is None:
            # Train status stands (e.g. "elected"), but there is no OOS score
            # for this month; do not read the empty test columns as one.
            row["note"] = "empty_test_month"
        if fold_winner is not None and test_bounds is not None:
            metrics, _r = self._run(
                fold_winner, "conservative", 1, test_bounds, None, f"WF-TEST-{test_label}"
            )
            row["fold_test_n_trades"] = metrics.n_trades
            row["fold_test_expected_nt"] = (
                "" if metrics.expected_nt is None else metrics.expected_nt
            )
            row["fold_test_mdd_nt"] = metrics.mdd_nt
        if frozen is not None and test_bounds is not None:
            metrics, _r = self._run(
                frozen, "conservative", 1, test_bounds, None, f"WF-FROZEN-{test_label}"
            )
            row["frozen_test_n_trades"] = metrics.n_trades
            row["frozen_test_expected_nt"] = (
                "" if metrics.expected_nt is None else metrics.expected_nt
            )
            row["frozen_test_mdd_nt"] = metrics.mdd_nt
        return row

    def _write_outputs(
        self,
        out_dir: Path,
        *,
        is_rows: list[CellMetrics],
        oos_rows: list[CellMetrics],
        isoos_rows: list[dict[str, object]],
        slip_rows: list[CellMetrics],
        wf_rows: list[dict[str, object]],
        report: GateReport,
        rolling_lines: list[str],
        elected: StrategyCombo | None,
        mc_rows: list[dict[str, object]],
        is_dates: list[date],
        oos_dates: list[date],
    ) -> None:
        grid_rows = [_row(m) for m in is_rows] + [_row(m) for m in oos_rows]
        _write_csv(out_dir / "grid.csv", grid_rows, _GRID_FIELDS)
        isoos_fields: list[str] = []
        for row in isoos_rows:
            for key in row:
                if key not in isoos_fields:
                    isoos_fields.append(key)
        if isoos_fields:
            _write_csv(out_dir / "is_oos.csv", isoos_rows, isoos_fields)
        else:
            _write_csv(out_dir / "is_oos.csv", [], ["combo"])
        _write_csv(out_dir / "slippage.csv", [_row(m) for m in slip_rows], _GRID_FIELDS)
        wf_fields = [
            "test_month",
            "train_months",
            "status",
            "note",
            "fold_entry_price",
            "fold_min_points",
            "fold_stop_buffer",
            "fold_take_profit",
            "fold_require_external",
            "fold_max_hold_bars",
            "fold_test_n_trades",
            "fold_test_expected_nt",
            "fold_test_mdd_nt",
            "frozen_test_n_trades",
            "frozen_test_expected_nt",
            "frozen_test_mdd_nt",
        ]
        _write_csv(out_dir / "walk_forward.csv", wf_rows, wf_fields)
        _write_csv(
            out_dir / "mc_mdd.csv",
            mc_rows,
            ["label", "p50", "p90", "p99", "n_trades"],
        )
        (out_dir / "gates.md").write_text(_gates_md(report, rolling_lines), encoding="utf-8")
        first_day = is_dates[0] if is_dates else (oos_dates[0] if oos_dates else None)
        last_day = oos_dates[-1] if oos_dates else (is_dates[-1] if is_dates else None)
        start = self._start if self._start is not None else first_day
        end = self._end if self._end is not None else last_day
        manifest = {
            "git_hash": resolve_git_hash(self._meta),
            "start": start.isoformat() if start is not None else None,
            "end": end.isoformat() if end is not None else None,
            "is_dates": [d.isoformat() for d in is_dates],
            "oos_dates": [d.isoformat() for d in oos_dates],
            "source_files": self._source,
            "grid_spec": {
                "entry_price": list(self._spec.entry_price),
                "min_points": list(self._spec.min_points),
                "stop_buffer": list(self._spec.stop_buffer),
                "take_profit": list(self._spec.take_profit),
                "require_external": list(self._spec.require_external),
                "max_hold_bars": list(self._spec.max_hold_bars),
                "n_combos": len(self._combos),
            },
            "seed": self._seed,
            "max_combos": self._max_combos,
            "elected": _combo_fields(elected) if elected is not None else None,
            "verdict": report.verdict,
        }
        (out_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )


def run_sweep(
    bars: list[KBar],
    out_dir: Path,
    *,
    spec: GridSpec | None = None,
    max_combos: int | None = None,
    seed: int = 42,
    log: TextIO | None = None,
    cost: CostConfig | None = None,
    params: SetupAParams | None = None,
    source: str = "in-memory",
    start: date | None = None,
    end: date | None = None,
) -> GateReport:
    spec = spec if spec is not None else GridSpec()
    combos = spec.combos()
    if max_combos is not None:
        combos = combos[:max_combos]
    runner = SweepRunner(
        bars,
        spec=spec,
        base_params=params if params is not None else SetupAParams(),
        cost=cost if cost is not None else load_trading_config(),
        calendar=TradeCalendar(),
        source=source,
        seed=seed,
        max_combos=max_combos,
        combos=combos,
        log=log if log is not None else sys.stdout,
        start=start,
        end=end,
    )
    return runner.execute(out_dir)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Setup A Phase 4 parameter sweep")
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--kbars", type=Path, default=_DEFAULT_KBARS)
    parser.add_argument("--max-combos", type=int, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    kbars: Path = args.kbars
    if not kbars.is_dir():
        print(f"skip: no kbars_data at {kbars}", file=sys.stderr)
        return 1
    bars = BarReader(kbars).load(start, end)
    if not bars:
        print("skip: no kbars in range", file=sys.stderr)
        return 1
    files = source_files(kbars, start, end)
    report = run_sweep(
        bars,
        args.out,
        max_combos=args.max_combos,
        seed=args.seed,
        source=",".join(files),
        params=load_setup_a_params(),
        cost=load_trading_config(),
        start=start,
        end=end,
    )
    print(f"verdict {report.verdict}", file=sys.stdout)
    return 0 if report.verdict != "no_go" else 2


if __name__ == "__main__":
    raise SystemExit(main())
