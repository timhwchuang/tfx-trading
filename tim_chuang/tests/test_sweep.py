from __future__ import annotations

import csv
import json
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from io import StringIO
from pathlib import Path

from pytest import MonkeyPatch
from test_setup_a import NOW, _ctx, _long_fvg, _long_smc

from tfx_trading.backtest.analysis import GridSpec, day_session_dates, split_70_30, window_bounds
from tfx_trading.backtest.config import BacktestConfig
from tfx_trading.backtest.ledger import BacktestResult, RunMeta
from tfx_trading.backtest.sweep import CachedSetupA, IndicatorCache, main, run_sweep
from tfx_trading.calendar import TradeCalendar
from tfx_trading.indicators.smc import Swing
from tfx_trading.kbar import KBar
from tfx_trading.strategy.setup_a import SetupA, SetupAParams, _evaluate
from tfx_trading.trading.costs import CostConfig
from tfx_trading.trading.models import Position, TradeRecord


def _cfg() -> CostConfig:
    return CostConfig(
        commission_nt=20,
        slippage_ticks=1,
        flatten_slippage_ticks=2,
        initial_margin_nt=10_000,
        maintenance_margin_nt=8_000,
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


def _day_minutes(day: datetime) -> list[KBar]:
    start = day.replace(hour=8, minute=46, second=0, microsecond=0)
    bars = [_bar(start + timedelta(minutes=i)) for i in range(15)]
    bars.append(_bar(day.replace(hour=13, minute=40)))
    bars.append(_bar(day.replace(hour=13, minute=41)))
    return bars


def _tiny_spec() -> GridSpec:
    return GridSpec(
        entry_price=("top", "ce"),
        min_points=(20.0,),
        stop_buffer=(5.0,),
        take_profit=("2R",),
        require_external=(False,),
        max_hold_bars=(10_000,),
    )


def test_warmup_returns_empty_even_if_flatten_would_fire() -> None:
    cal = TradeCalendar()
    cache: dict[tuple[datetime, int], object] = {}
    params = SetupAParams()
    ts = datetime(2026, 8, 17, 13, 40)
    ctx = _ctx(
        ts,
        position=Position(side="long", qty=1, avg_price=20000.0),
        bars_5m=(_bar(ts),),
    )
    wrapper = CachedSetupA(
        params,
        cal,
        cache,  # type: ignore[arg-type]
        window_start=datetime(2026, 8, 18, 0, 0),
    )
    assert wrapper.decide(ctx) == []
    live = SetupA(params, cal).decide(ctx)
    assert any(item.kind == "flatten" for item in live)


def test_in_window_flatten_still_fires() -> None:
    cal = TradeCalendar()
    cache: dict[tuple[datetime, int], object] = {}
    params = SetupAParams()
    ts = datetime(2026, 8, 17, 13, 40)
    ctx = _ctx(
        ts,
        position=Position(side="long", qty=1, avg_price=20000.0),
        bars_5m=(_bar(ts),),
    )
    wrapper = CachedSetupA(
        params,
        cal,
        cache,  # type: ignore[arg-type]
        window_start=datetime(2026, 8, 17, 0, 0),
    )
    intents = wrapper.decide(ctx)
    assert any(item.kind == "flatten" for item in intents)


def test_cache_hit_and_entry_price_changes_intent(monkeypatch: MonkeyPatch) -> None:
    from tfx_trading.backtest import sweep as sweep_mod

    smc = _long_smc()
    fvgs = [_long_fvg()]
    monkeypatch.setattr(sweep_mod, "smc_compute", lambda bars: smc)
    monkeypatch.setattr(sweep_mod, "fvg_compute", lambda bars, min_points=0.0: fvgs)
    cal = TradeCalendar()
    cache: dict[tuple[datetime, int], tuple[object, list[object]]] = {}
    ctx = _ctx()
    top = CachedSetupA(
        SetupAParams(entry_price="top"),
        cal,
        cache,  # type: ignore[arg-type]
        datetime(2026, 8, 17, 0, 0),
    )
    ce = CachedSetupA(
        SetupAParams(entry_price="ce"),
        cal,
        cache,  # type: ignore[arg-type]
        datetime(2026, 8, 17, 0, 0),
    )
    first = top.decide(ctx)
    size = len(cache)
    second = ce.decide(ctx)
    assert len(cache) == size
    assert first
    assert second
    assert first[0].price != second[0].price


def test_max_combos_is_2n_runs_and_smoke(tmp_path: Path) -> None:
    bars: list[KBar] = []
    for day in range(10, 14):
        bars.extend(_day_minutes(datetime(2026, 8, day, 0, 0)))
    log = StringIO()
    report = run_sweep(
        bars,
        tmp_path,
        spec=_tiny_spec(),
        max_combos=1,
        seed=1,
        log=log,
        cost=_cfg(),
        params=SetupAParams(),
        start=date(2026, 8, 1),
        end=date(2026, 9, 1),
    )
    assert report.verdict == "smoke"
    with (tmp_path / "grid.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    is_rows = [r for r in rows if r["split"] == "is"]
    assert len(is_rows) == 2
    assert "smoke" in (tmp_path / "gates.md").read_text(encoding="utf-8")
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["start"] == "2026-08-01"
    assert manifest["end"] == "2026-09-01"
    assert manifest["max_combos"] == 1
    with (tmp_path / "walk_forward.csv").open(encoding="utf-8") as handle:
        wf_rows = list(csv.DictReader(handle))
    assert [r["status"] for r in wf_rows] == ["partial_grid"]


def test_full_elected_window_not_oos_warmup(tmp_path: Path) -> None:
    bars: list[KBar] = []
    for day in range(10, 14):
        bars.extend(_day_minutes(datetime(2026, 8, day, 0, 0)))
    days = [datetime(2026, 8, d).date() for d in range(10, 14)]
    _is_dates, oos_dates = split_70_30(days)
    full = window_bounds(bars, days)
    oos = window_bounds(bars, oos_dates)
    assert full is not None and oos is not None
    assert full.start < oos.start
    run_sweep(
        bars,
        tmp_path,
        spec=_tiny_spec(),
        max_combos=1,
        seed=1,
        log=StringIO(),
        cost=_cfg(),
        params=SetupAParams(),
    )
    with (tmp_path / "mc_mdd.csv").open(encoding="utf-8") as handle:
        labels = {row["label"] for row in csv.DictReader(handle)}
    assert labels == {"oos", "full_elected"}


def test_cli_no_kbars(tmp_path: Path) -> None:
    code = main(
        [
            "--start",
            "2026-01-01",
            "--end",
            "2026-01-02",
            "--out",
            str(tmp_path / "out"),
            "--kbars",
            str(tmp_path / "missing"),
        ]
    )
    assert code == 1


def test_cached_matches_setup_a_after_warmup() -> None:
    cal = TradeCalendar()
    cache: dict[tuple[datetime, int], object] = {}
    params = SetupAParams()
    ctx = _ctx(NOW)
    wrapper = CachedSetupA(params, cal, cache, datetime(2026, 8, 17, 0, 0))  # type: ignore[arg-type]
    assert wrapper.decide(ctx) == SetupA(params, cal).decide(ctx)


def _single_spec() -> GridSpec:
    return GridSpec(
        entry_price=("top",),
        min_points=(20.0,),
        stop_buffer=(5.0,),
        take_profit=("2R",),
        require_external=(False,),
        max_hold_bars=(10_000,),
    )


def _fake_result(
    trades: list[TradeRecord],
    fill_mode: str,
    cost: CostConfig,
) -> BacktestResult:
    total = sum(t.pnl_nt for t in trades)
    return BacktestResult(
        trades=tuple(trades),
        equity_curve=(),
        total_pnl_nt=total,
        mdd_nt=100.0,
        win_rate=0.5,
        profit_factor=2.0,
        expected_r=0.5,
        avg_hold=30.0,
        day_pnl_nt=total,
        night_pnl_nt=0.0,
        max_margin_nt=10_000.0,
        min_account_nt=10_100.0,
        fill_mode=fill_mode,  # type: ignore[arg-type]
        git_hash="test",
        source_files="synthetic",
        n_1m=len(trades),
        start=None,
        end=None,
        commission_nt=cost.commission_nt,
        slippage_ticks=cost.slippage_ticks,
        flatten_slippage_ticks=cost.flatten_slippage_ticks,
        initial_margin_nt=cost.initial_margin_nt,
        maintenance_margin_nt=cost.maintenance_margin_nt,
    )


def _fake_run(
    bars: list[KBar],
    strategy: CachedSetupA,
    cost_cfg: CostConfig,
    backtest_cfg: BacktestConfig,
    *,
    meta: RunMeta | None = None,
) -> BacktestResult:
    """10 trades per day-session date inside the strategy window, EV +50/trade."""
    trades: list[TradeRecord] = []
    for d in day_session_dates(bars):
        if datetime.combine(d, time(9, 0)) < strategy._window_start:
            continue
        for k in range(10):
            pnl = 200.0 if k % 2 == 0 else -100.0
            trades.append(
                TradeRecord(
                    side="long",
                    entry_ts=datetime.combine(d, time(9, 0)) + timedelta(minutes=k),
                    entry_price=20000.0,
                    exit_ts=datetime.combine(d, time(10, 0)) + timedelta(minutes=k),
                    exit_price=20000.0 + pnl / 10.0,
                    qty=1,
                    pnl_nt=pnl,
                    r_multiple=1.0,
                    reason="target",
                )
            )
    return _fake_result(trades, backtest_cfg.fill_mode, cost_cfg)


def test_mc_full_elected_row_differs_from_oos_with_trades(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Plan test: MC `full_elected` row ≠ `oos` row when IS trades exist.

    The full-tape window (6 dates) and the 70/30 OOS window (2 dates) feed
    different PnL sequences into the seeded Monte Carlo.
    """
    from tfx_trading.backtest import sweep as sweep_mod

    monkeypatch.setattr(sweep_mod, "run", _fake_run)
    bars: list[KBar] = []
    for day in range(10, 16):
        bars.extend(_day_minutes(datetime(2026, 8, day, 0, 0)))
    report = run_sweep(
        bars,
        tmp_path,
        spec=_single_spec(),
        seed=7,
        log=StringIO(),
        cost=_cfg(),
        params=SetupAParams(),
    )
    # 4 IS dates x 10 = 40 >= 30 and 2 OOS dates x 10 = 20 >= 10; positive EV
    # everywhere, so the single-combo plateau elects and all hard gates pass.
    assert report.verdict == "go"
    with (tmp_path / "mc_mdd.csv").open(encoding="utf-8") as handle:
        rows = {row["label"]: row for row in csv.DictReader(handle)}
    assert set(rows) == {"oos", "full_elected"}
    assert rows["oos"]["n_trades"] == "20"
    assert rows["full_elected"]["n_trades"] == "60"
    assert float(rows["full_elected"]["p90"]) > 0.0
    assert rows["full_elected"]["p90"] != rows["oos"]["p90"]


def test_fold_empty_test_month_is_noted(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """A calendar test month with no day-session keeps the train status but is
    flagged `empty_test_month`; its test metric columns are not an OOS score."""
    from tfx_trading.backtest import sweep as sweep_mod

    monkeypatch.setattr(sweep_mod, "run", _fake_run)
    bars: list[KBar] = []
    for d in (date(2026, 1, 15), date(2026, 2, 16), date(2026, 3, 16), date(2026, 5, 15)):
        bars.extend(_day_minutes(datetime(d.year, d.month, d.day, 0, 0)))
    run_sweep(
        bars,
        tmp_path,
        spec=_single_spec(),
        seed=3,
        log=StringIO(),
        cost=_cfg(),
        params=SetupAParams(),
    )
    with (tmp_path / "walk_forward.csv").open(encoding="utf-8") as handle:
        rows = {row["test_month"]: row for row in csv.DictReader(handle)}
    april = rows["2026-04"]
    assert april["status"] == "elected"
    assert april["note"] == "empty_test_month"
    assert april["fold_test_n_trades"] == ""
    assert april["frozen_test_n_trades"] == ""
    may = rows["2026-05"]
    assert may["status"] == "insufficient_sample"
    assert may["note"] == ""


def test_cache_strips_swings_and_filled_fvgs(monkeypatch: MonkeyPatch) -> None:
    """Stripping is behavior-preserving: `_evaluate` never reads `smc.swings`
    and filters FVGs to untouched/mitigated, so decisions match the unstripped
    inputs while the cache stays O(active) per entry."""
    from tfx_trading.backtest import sweep as sweep_mod

    swing = Swing(
        timestamp=NOW,
        confirmed_at=NOW,
        side="high",
        price=20040.0,
        significant=True,
        session="day",
    )
    smc = replace(_long_smc(), swings=[swing])
    fvgs = [_long_fvg(), _long_fvg(state="filled", top=19910.0, bottom=19840.0)]
    monkeypatch.setattr(sweep_mod, "smc_compute", lambda bars: smc)
    monkeypatch.setattr(sweep_mod, "fvg_compute", lambda bars, min_points=0.0: fvgs)
    cal = TradeCalendar()
    cache: IndicatorCache = {}
    params = SetupAParams()
    ctx = _ctx()
    wrapper = CachedSetupA(params, cal, cache, datetime(2026, 8, 17, 0, 0))
    intents = wrapper.decide(ctx)
    assert intents == _evaluate(smc, fvgs, ctx, params, cal)
    assert intents
    ((cached_smc, cached_fvgs),) = cache.values()
    assert cached_smc.swings == []
    assert [f.state for f in cached_fvgs] == ["untouched"]
