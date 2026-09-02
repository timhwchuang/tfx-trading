from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

from tfx_trading.backtest.config import load_backtest_config
from tfx_trading.backtest.engine import run
from tfx_trading.backtest.ledger import RunMeta
from tfx_trading.bar_reader import BarReader
from tfx_trading.indicators.fvg import compute as fvg_compute
from tfx_trading.indicators.smc import SessionLevel
from tfx_trading.indicators.smc import compute as smc_compute
from tfx_trading.kbar import KBar
from tfx_trading.strategy.protocol import DecisionContext
from tfx_trading.strategy.setup_a import (
    SetupA,
    SetupAParams,
    _select_active_fvg,
    _swept_level,
    load_setup_a_params,
    preferred_event,
)
from tfx_trading.trading.costs import load_trading_config
from tfx_trading.trading.models import Intent, Side, TradeRecord

_KBARS_PATH = Path(__file__).resolve().parent / "kbars_data"
# 2026-08-11 has a complete Setup A round trip (entry 11:56, flatten 13:41).
# Prior days are for PDL / prev_night_low on that session prefix, not demo_smc's as_of.
_START = date(2026, 8, 7)
_END = date(2026, 8, 11)


class _LoggingSetupA(SetupA):
    def __init__(self, params: SetupAParams) -> None:
        super().__init__(params)
        self.n_signals = 0

    def decide(self, ctx: DecisionContext) -> list[Intent]:
        intents = super().decide(ctx)
        entry = _entry_intent(intents)
        if entry is not None and entry.side is not None:
            self.n_signals += 1
            _print_chain(ctx, intents, entry.side, self._params)
        return intents


def _entry_intent(intents: list[Intent]) -> Intent | None:
    for intent in intents:
        if intent.kind == "place_limit" and intent.intent_id.endswith("-entry"):
            return intent
    return None


def _fmt_swept(name: str, level: SessionLevel | None) -> str:
    if level is None or level.interact != "swept" or level.interact_ts is None:
        return f"{name:<16}  -"
    return f"{name:<16}  {level.price:<8.1f}  {level.interact_ts:%Y-%m-%d %H:%M}"


def _print_as_of(bar: KBar) -> None:
    print(f"========= as_of {bar.timestamp:%Y-%m-%d %H:%M} =========")
    print(f"{'timestamp':<19}  {'open':<8}  {'high':<8}  {'low':<8}  {'close':<8}")
    print(
        f"{bar.timestamp:%Y-%m-%d %H:%M:%S}  "
        f"{bar.open:<8.1f}  "
        f"{bar.high:<8.1f}  "
        f"{bar.low:<8.1f}  "
        f"{bar.close:<8.1f}"
    )
    print()


def _print_chain(
    ctx: DecisionContext,
    intents: list[Intent],
    side: Side,
    params: SetupAParams,
) -> None:
    bars = list(ctx.bars_5m)
    levels = smc_compute(bars)
    fvgs = fvg_compute(bars, min_points=0.0)
    _print_as_of(bars[-1])
    print("========= Setup A chain =========")
    if side == "long":
        print(f"swept  {_fmt_swept('pdl', levels.pdl)}")
        print(f"swept  {_fmt_swept('prev_night_low', levels.prev_night_low)}")
    else:
        print(f"swept  {_fmt_swept('pdh', levels.pdh)}")
        print(f"swept  {_fmt_swept('prev_night_high', levels.prev_night_high)}")
    swept = _swept_level(levels, side)
    direction: Literal["bullish", "bearish"] = "bullish" if side == "long" else "bearish"
    if swept is not None and swept.interact_ts is not None:
        ev = preferred_event(levels.events, direction, swept.interact_ts, params.require_external)
        if ev is None:
            print("event  -")
        else:
            print(f"event  {ev.ts:%Y-%m-%d %H:%M}  {ev.kind:<5}  {ev.direction:<8}  {ev.scope}")
        fvg = _select_active_fvg(
            fvgs, direction, swept.interact_ts, params.min_points, params.max_fvg_age_bars, ctx
        )
        if fvg is None:
            print("fvg    -")
        else:
            print(
                f"fvg    {fvg.formed_at:%Y-%m-%d %H:%M}  {fvg.direction:<8}  "
                f"{fvg.bottom:.1f}-{fvg.top:.1f}  {fvg.state}"
            )
    print("intents")
    for intent in intents:
        print(f"  {intent.kind:<12}  {intent.side}  {intent.price}  {intent.intent_id}")
    print()


def _print_trades(trades: tuple[TradeRecord, ...]) -> None:
    print("========= trade log (run) =========")
    if not trades:
        print("-")
        print()
        return
    print(
        f"{'side':<6}  {'entry':<16}  {'exit':<16}  {'entry_px':<9}  "
        f"{'exit_px':<9}  {'pnl_nt':<10}  {'reason'}"
    )
    for trade in trades:
        print(
            f"{trade.side:<6}  "
            f"{trade.entry_ts:%Y-%m-%d %H:%M}  "
            f"{trade.exit_ts:%Y-%m-%d %H:%M}  "
            f"{trade.entry_price:<9.1f}  "
            f"{trade.exit_price:<9.1f}  "
            f"{trade.pnl_nt:<10.1f}  "
            f"{trade.reason}"
        )
    print(f"({len(trades)} trades)\n")


def main() -> None:
    if not _KBARS_PATH.is_dir():
        print("skip: no kbars_data")
        return
    kbars = BarReader(_KBARS_PATH).load(_START, _END)
    if not kbars:
        print("skip: no kbars_data")
        return
    strategy = _LoggingSetupA(load_setup_a_params())
    result = run(
        kbars,
        strategy,
        load_trading_config(),
        load_backtest_config(),
        meta=RunMeta(source_files=str(_KBARS_PATH)),
    )
    if not strategy.n_signals:
        print("========= Setup A chain =========")
        print("-")
        print()
    print(f"run {result.start} .. {result.end}  n_1m={result.n_1m}  trades={len(result.trades)}")
    print()
    _print_trades(result.trades)


if __name__ == "__main__":
    main()
