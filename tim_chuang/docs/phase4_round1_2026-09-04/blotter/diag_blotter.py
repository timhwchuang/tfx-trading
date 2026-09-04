#!/usr/bin/env python3
"""Phase 4 no_go trade blotter diagnosis (read-only; temp script)."""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path

from tfx_trading.backtest.analysis import (
    StrategyCombo,
    day_session_dates,
    expected_nt,
    split_70_30,
    window_bounds,
    bars_through,
)
from tfx_trading.backtest.config import BacktestConfig, FillMode
from tfx_trading.backtest.engine import run
from tfx_trading.backtest.ledger import RunMeta
from tfx_trading.backtest.sweep import CachedSetupA, IndicatorCache
from tfx_trading.bar_reader import BarReader
from tfx_trading.calendar import TradeCalendar
from tfx_trading.strategy.setup_a import (
    SetupAParams,
    _EMPTY_SMC,
    _arm_setup,
    _evaluate,
    _skip_indicators,
    load_setup_a_params,
    preferred_event,
    _select_active_fvg,
    _swept_level,
)
from tfx_trading.strategy.protocol import DecisionContext
from tfx_trading.trading.costs import load_trading_config
from tfx_trading.trading.models import Intent
from tfx_trading.indicators.smc import SmcLevels
from tfx_trading.indicators.fvg import Fvg
from tfx_trading.bar_store import session_kind
from tfx_trading.kbar import KBar

OUT = Path("/tmp/phase4_blotter")
KBARS = Path("/workspace/tfx-trading/tim_chuang/tfx_trading/kbars_data")
START = date(2025, 3, 3)
END = date(2026, 3, 2)


@dataclass
class FunnelCounts:
    decide_calls: int = 0
    skip_indicators: int = 0
    night_or_no_session: int = 0
    settlement: int = 0
    after_flatten: int = 0
    in_position: int = 0
    pending_entry_managed: int = 0
    halted_or_before_open: int = 0
    no_dealing_range: int = 0
    equilibrium: int = 0
    arm_attempts: int = 0  # discount or premium
    no_sweep: int = 0
    no_event: int = 0
    no_fvg: int = 0
    invalid_stop: int = 0
    intents_emitted: int = 0  # times we return a non-empty arm bracket
    place_limit_intents: int = 0


class FunnelCachedSetupA(CachedSetupA):
    """CachedSetupA with lightweight funnel counters (ext False/True)."""

    def __init__(self, *args, funnel: FunnelCounts, **kwargs):
        super().__init__(*args, **kwargs)
        self.funnel = funnel

    def decide(self, ctx: DecisionContext) -> list[Intent]:
        f = self.funnel
        f.decide_calls += 1
        if ctx.bar_1m.timestamp < self._window_start:
            return []
        if _skip_indicators(ctx, self._params, self._calendar):
            f.skip_indicators += 1
            return _evaluate(_EMPTY_SMC, [], ctx, self._params, self._calendar)

        bars = list(ctx.bars_5m)
        key = (bars[-1].timestamp, len(bars)) if bars else (ctx.bar_1m.timestamp, 0)
        if key not in self._cache:
            self._advance(bars)
            smc = replace(self._smc_tracker.snapshot(), swings=[])
            live = [x for x in self._fvg_tracker.snapshot() if x.state != "filled"]
            self._cache[key] = (smc, live)
        smc, fvgs = self._cache[key]
        return self._evaluate_funnel(smc, fvgs, ctx)

    def _evaluate_funnel(
        self, smc: SmcLevels, fvgs: list[Fvg], ctx: DecisionContext
    ) -> list[Intent]:
        from tfx_trading.bar_store import session_key
        from tfx_trading.strategy.setup_a import (
            _hard_exit,
            _time_stop_hit,
            _has_pending_flatten,
            _flatten_intent,
            _pending_entry,
            _is_halted,
            _thesis_live,
            _cancel_intent,
            _bracket_for_side,
            _fvg_limit,
            _round_tick,
            _bar_at,
            _take_profit_price,
        )

        f = self.funnel
        params = self._params
        calendar = self._calendar
        now = ctx.bar_1m.timestamp
        kind = session_kind(now)
        key = session_key(now)
        if kind is None or key is None:
            f.night_or_no_session += 1
            return []
        session_date = key[0]
        clock = now.time()
        if kind != "day":
            f.night_or_no_session += 1
            return _hard_exit(ctx)
        if params.skip_settlement_day and calendar.is_settlement_day(session_date):
            f.settlement += 1
            return _hard_exit(ctx)
        if clock >= params.flatten_time:
            f.after_flatten += 1
            return _hard_exit(ctx)
        if ctx.position.side is not None:
            f.in_position += 1
            if _time_stop_hit(ctx, params) and not _has_pending_flatten(ctx):
                return [_flatten_intent(ctx)]
            return []
        entry = _pending_entry(ctx)
        halted = _is_halted(ctx, params, session_date)
        if entry is not None:
            f.pending_entry_managed += 1
            if halted:
                return [_cancel_intent(ctx, entry)]
            if not _thesis_live(smc, fvgs, ctx, params, entry):
                return [_cancel_intent(ctx, entry)]
            return []
        if any(order.kind in {"limit", "stop"} for order in ctx.pending):
            f.pending_entry_managed += 1
            return []
        if halted or clock < params.no_trade_before:
            f.halted_or_before_open += 1
            return []

        # arm path funnel
        rng = smc.dealing_range
        if rng is None:
            f.no_dealing_range += 1
            return []
        if rng.position == "equilibrium":
            f.equilibrium += 1
            return []
        if rng.position not in ("discount", "premium"):
            return []
        side = "long" if rng.position == "discount" else "short"
        f.arm_attempts += 1

        swept = _swept_level(smc, side)
        if swept is None or swept.interact_ts is None:
            f.no_sweep += 1
            return []
        direction = "bullish" if side == "long" else "bearish"
        if preferred_event(smc.events, direction, swept.interact_ts, params.require_external) is None:
            f.no_event += 1
            return []
        fvg = _select_active_fvg(
            fvgs, direction, swept.interact_ts, params.min_points, params.max_fvg_age_bars, ctx
        )
        if fvg is None:
            f.no_fvg += 1
            return []
        sweep_bar = _bar_at(ctx.bars_5m, swept.interact_ts)
        if sweep_bar is None:
            f.no_sweep += 1
            return []
        entry_px = _round_tick(_fvg_limit(fvg, params))
        extreme = sweep_bar.low if side == "long" else sweep_bar.high
        if side == "long":
            stop = _round_tick(max(extreme - params.stop_buffer, fvg.bottom - params.stop_buffer))
            if stop >= entry_px:
                f.invalid_stop += 1
                return []
        else:
            stop = _round_tick(min(extreme + params.stop_buffer, fvg.top + params.stop_buffer))
            if stop <= entry_px:
                f.invalid_stop += 1
                return []
        intents = _bracket_for_side(side, smc, fvgs, ctx, params, session_date)
        if intents:
            f.intents_emitted += 1
            f.place_limit_intents += sum(1 for i in intents if i.kind == "place_limit")
        return intents


def combo_label(c: StrategyCombo) -> str:
    return (
        f"{c.entry_price}_min{c.min_points:g}_buf{c.stop_buffer:g}_"
        f"tp{c.take_profit}_ext{int(c.require_external)}_hold{c.max_hold_bars}"
    )


def summarize(result, label: str) -> dict:
    reasons = Counter(t.reason for t in result.trades)
    wins = [t for t in result.trades if t.pnl_nt > 0]
    losses = [t for t in result.trades if t.pnl_nt < 0]
    flats = [t for t in result.trades if t.pnl_nt == 0]
    rs = [t.r_multiple for t in result.trades if t.r_multiple is not None]
    return {
        "label": label,
        "n_trades": len(result.trades),
        "total_pnl_nt": result.total_pnl_nt,
        "expected_nt": expected_nt(result.total_pnl_nt, len(result.trades)),
        "expected_r": result.expected_r,
        "win_rate": result.win_rate,
        "profit_factor": result.profit_factor,
        "mdd_nt": result.mdd_nt,
        "exit_reasons": dict(reasons),
        "n_wins": len(wins),
        "n_losses": len(losses),
        "n_flats": len(flats),
        "sum_win_pnl": sum(t.pnl_nt for t in wins),
        "sum_loss_pnl": sum(t.pnl_nt for t in losses),
        "r_min": min(rs) if rs else None,
        "r_max": max(rs) if rs else None,
        "r_mean": (sum(rs) / len(rs)) if rs else None,
        "r_list": rs,
        "fill_mode": result.fill_mode,
        "slippage_ticks": result.slippage_ticks,
        "commission_nt": result.commission_nt,
    }


def run_one(
    bars,
    combo: StrategyCombo,
    base: SetupAParams,
    cost,
    calendar,
    bounds,
    fill_mode: FillMode,
    slip: int,
    cache: IndicatorCache,
    funnel: FunnelCounts | None = None,
):
    params = combo.to_params(base)
    if funnel is None:
        strategy = CachedSetupA(params, calendar, cache, bounds.start)
    else:
        strategy = FunnelCachedSetupA(params, calendar, cache, bounds.start, funnel=funnel)
    cost2 = replace(cost, slippage_ticks=slip)
    t0 = time.time()
    result = run(
        bars_through(bars, bounds.end),
        strategy,
        cost2,
        BacktestConfig(fill_mode=fill_mode),
        meta=RunMeta(source_files="diag"),
    )
    result = replace(result, equity_curve=())
    elapsed = time.time() - t0
    return result, elapsed


def print_trades(result, title: str) -> None:
    print(f"\n=== TRADES: {title} ===")
    print(
        f"{'#':>2} {'side':5} {'entry_ts':19} {'exit_ts':19} {'entry':>8} {'exit':>8} "
        f"{'pnl_nt':>10} {'R':>7} {'reason':12}"
    )
    for i, t in enumerate(result.trades, 1):
        r = "" if t.r_multiple is None else f"{t.r_multiple:.3f}"
        print(
            f"{i:2d} {t.side:5} {t.entry_ts.isoformat(sep=' ', timespec='minutes'):19} "
            f"{t.exit_ts.isoformat(sep=' ', timespec='minutes'):19} "
            f"{t.entry_price:8.1f} {t.exit_price:8.1f} {t.pnl_nt:10.2f} {r:>7} {t.reason}"
        )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print("Loading bars...", flush=True)
    t0 = time.time()
    bars = BarReader(KBARS).load(START, END)
    print(f"Loaded {len(bars)} 1m bars in {time.time()-t0:.1f}s", flush=True)
    day_dates = day_session_dates(bars)
    is_dates, oos_dates = split_70_30(day_dates)
    is_bounds = window_bounds(bars, is_dates)
    assert is_bounds is not None
    print(
        f"IS days={len(is_dates)} ({is_dates[0]}→{is_dates[-1]}) "
        f"OOS days={len(oos_dates)} window={is_bounds.start}→{is_bounds.end}",
        flush=True,
    )

    base = load_setup_a_params()
    cost = load_trading_config()
    calendar = TradeCalendar()
    cache: IndicatorCache = {}

    # Representative combos
    hi_freq = StrategyCombo("top", 15.0, 3.0, "2R", False, 12)
    best_ev = StrategyCombo("top", 30.0, 8.0, "2R", False, 12)
    mid = StrategyCombo("top", 20.0, 5.0, "2R", False, 10000)  # default-ish
    mid_ext = StrategyCombo("top", 20.0, 5.0, "2R", True, 10000)

    combos_cons = [
        ("hi_freq", hi_freq),
        ("best_ev", best_ev),
        ("mid_defaultish", mid),
    ]

    summaries = []
    for name, combo in combos_cons:
        label = f"{name}|{combo_label(combo)}|cons|slip1|IS"
        print(f"\n>>> Running {label}", flush=True)
        result, elapsed = run_one(
            bars, combo, base, cost, calendar, is_bounds, "conservative", 1, cache
        )
        print(f"    done in {elapsed:.1f}s n_trades={len(result.trades)} pnl={result.total_pnl_nt:.2f}", flush=True)
        path = OUT / f"trades_{name}_cons.csv"
        result.write_trade_log(path)
        print_trades(result, label)
        s = summarize(result, label)
        s["elapsed_s"] = elapsed
        s["combo"] = combo_label(combo)
        summaries.append(s)
        print("AGG:", json.dumps({k: v for k, v in s.items() if k != "r_list"}, default=str))

    # Optimistic spot-check on hi_freq
    print("\n>>> Optimistic spot-check hi_freq", flush=True)
    result_opt, elapsed = run_one(
        bars, hi_freq, base, cost, calendar, is_bounds, "optimistic", 1, cache
    )
    print(f"    done in {elapsed:.1f}s n_trades={len(result_opt.trades)} pnl={result_opt.total_pnl_nt:.2f}", flush=True)
    result_opt.write_trade_log(OUT / "trades_hi_freq_opt.csv")
    print_trades(result_opt, "hi_freq|opt|slip1|IS")
    s_opt = summarize(result_opt, "hi_freq|opt")
    s_opt["elapsed_s"] = elapsed
    summaries.append(s_opt)

    # Compare cons vs opt trade-by-trade for hi_freq
    cons_path = OUT / "trades_hi_freq_cons.csv"
    # reload from summaries
    cons_res = None
    for name, combo in combos_cons:
        if name == "hi_freq":
            # re-read from written file is awkward; keep last cons from first run
            pass
    # Re-run not needed — we have result_opt; re-get cons from file
    import csv
    cons_trades = []
    with cons_path.open() as fh:
        # skip comment lines
        lines = [ln for ln in fh if not ln.startswith("#")]
    from io import StringIO
    cons_trades = list(csv.DictReader(StringIO("".join(lines))))
    opt_trades = []
    with (OUT / "trades_hi_freq_opt.csv").open() as fh:
        lines = [ln for ln in fh if not ln.startswith("#")]
    opt_trades = list(csv.DictReader(StringIO("".join(lines))))
    print("\n=== cons vs opt hi_freq ===")
    print(f"n_cons={len(cons_trades)} n_opt={len(opt_trades)}")
    same = cons_trades == opt_trades
    print(f"identical trade rows: {same}")
    if not same and len(cons_trades) == len(opt_trades):
        for i, (a, b) in enumerate(zip(cons_trades, opt_trades), 1):
            diffs = {k: (a[k], b[k]) for k in a if a.get(k) != b.get(k)}
            if diffs:
                print(f"  trade {i} diffs: {diffs}")

    # Signal funnel: mid_defaultish ext=False vs True
    funnel_results = {}
    for name, combo in [("mid_extFalse", mid), ("mid_extTrue", mid_ext)]:
        print(f"\n>>> Funnel {name}", flush=True)
        funnel = FunnelCounts()
        # separate cache so funnel strategy state is clean
        fcache: IndicatorCache = {}
        result, elapsed = run_one(
            bars, combo, base, cost, calendar, is_bounds, "conservative", 1, fcache, funnel=funnel
        )
        print(f"    done in {elapsed:.1f}s n_trades={len(result.trades)}", flush=True)
        fd = {k: getattr(funnel, k) for k in FunnelCounts.__dataclass_fields__}
        fd["n_trades"] = len(result.trades)
        fd["elapsed_s"] = elapsed
        funnel_results[name] = fd
        print("FUNNEL:", json.dumps(fd))

    report = {
        "window": "IS",
        "is_start": str(is_dates[0]),
        "is_end": str(is_dates[-1]),
        "n_is_days": len(is_dates),
        "summaries": summaries,
        "funnel": funnel_results,
        "cons_opt_identical_hi_freq": same,
        "note_cons_opt": (
            "Limit fill differs by 1 tick touch rule (cons needs price+/-TICK beyond limit; "
            "opt fills on touch). Stops identical. If entries are deep limit fills that "
            "trade through by >1 tick, cons≡opt."
        ),
    }
    (OUT / "report.json").write_text(json.dumps(report, indent=2, default=str))
    print("\nWrote", OUT / "report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
