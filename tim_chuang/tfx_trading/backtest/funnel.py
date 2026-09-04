from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Literal

from tfx_trading.backtest.census import _in_arm_window, _live_fvg
from tfx_trading.backtest.config import BacktestConfig
from tfx_trading.backtest.engine import run
from tfx_trading.backtest.ledger import RunMeta, resolve_git_hash
from tfx_trading.backtest.smoke import is_arm_bracket, smoke_params
from tfx_trading.backtest.sweep import CachedSetupA, IndicatorCache
from tfx_trading.bar_reader import BarReader
from tfx_trading.bar_store import BarStore, session_key
from tfx_trading.calendar import TradeCalendar
from tfx_trading.indicators.fvg import Fvg, FvgTracker
from tfx_trading.indicators.smc import SmcTracker
from tfx_trading.kbar import KBar
from tfx_trading.strategy.protocol import DecisionContext
from tfx_trading.strategy.setup_a import (
    SetupAParams,
    _swept_level,
    load_setup_a_params,
    preferred_event,
)
from tfx_trading.trading.costs import load_trading_config
from tfx_trading.trading.models import Intent, Side

_DEFAULT_KBARS = Path(__file__).resolve().parent.parent / "kbars_data"
_DEFAULT_OUT = Path(__file__).resolve().parents[2] / "docs" / "phase4_round2_2026-09-04" / "funnel"
_DEFAULT_START = date(2025, 3, 3)
_DEFAULT_END = date(2025, 11, 6)
ImpulseBucket = Literal["same", "next", "later"]


def next_5m_after(bars_5m: list[KBar], ts: datetime) -> datetime | None:
    """Next 5m close in the same session_key after ts.

    Not +1 calendar day, not ts+5m, and not the next tape bar across a
    session gap (day 13:45 → night 15:05 is a different session; then None).
    """
    key = session_key(ts)
    if key is None:
        return None
    for bar in bars_5m:
        if bar.timestamp > ts and session_key(bar.timestamp) == key:
            return bar.timestamp
    return None


def impulse_bucket(
    formed_at: datetime,
    interact_ts: datetime,
    next_ts: datetime | None,
) -> ImpulseBucket:
    if formed_at == interact_ts:
        return "same"
    if next_ts is not None and formed_at == next_ts:
        return "next"
    return "later"


def fill_rate(n_fills: int, n_spells: int) -> float | None:
    if n_spells == 0:
        return None
    return n_fills / n_spells


def _has_working_entry(ctx: DecisionContext) -> bool:
    return any(order.kind in {"limit", "stop"} for order in ctx.pending)


@dataclass
class SpellCounts:
    n_spells: int = 0
    n_fills: int = 0
    n_cancel_thesis: int = 0
    n_unfilled_flatten: int = 0
    n_still_open: int = 0
    raw_arm_closes: int = 0

    @property
    def fill_rate(self) -> float | None:
        return fill_rate(self.n_fills, self.n_spells)


@dataclass
class SpellTracker:
    """Classify arm spells from ctx at 5m closes. 13:40 unfilled is expire, not cancel."""

    flatten_time: time = time(13, 40)
    counts: SpellCounts = field(default_factory=SpellCounts)
    _open: bool = False
    _n_closed: int = 0

    def on_close(self, ctx: DecisionContext, intents: list[Intent]) -> None:
        n_closed = len(ctx.closed_trades)
        clock = ctx.bar_1m.timestamp.time()
        if self._open:
            if n_closed > self._n_closed:
                self.counts.n_fills += 1
                self._open = False
            elif any(item.kind == "cancel" for item in intents) and clock < self.flatten_time:
                self.counts.n_cancel_thesis += 1
                self._open = False
            elif (
                ctx.position.side is None
                and not _has_working_entry(ctx)
                and n_closed == self._n_closed
                and clock >= self.flatten_time
            ):
                self.counts.n_unfilled_flatten += 1
                self._open = False
        if is_arm_bracket(intents):
            self.counts.raw_arm_closes += 1
            if not self._open:
                self.counts.n_spells += 1
                self._open = True
        self._n_closed = n_closed

    def finish(self) -> None:
        if self._open:
            self.counts.n_still_open += 1
            self._open = False


class FunnelSetupA:
    def __init__(self, inner: CachedSetupA, tracker: SpellTracker) -> None:
        self._inner = inner
        self.tracker = tracker

    def decide(self, ctx: DecisionContext) -> list[Intent]:
        intents = self._inner.decide(ctx)
        self.tracker.on_close(ctx, intents)
        return intents


@dataclass
class DetectorReport:
    n_nested_any: int = 0
    n_nested_choch: int = 0
    n_long_any: int = 0
    n_short_any: int = 0
    n_long_choch: int = 0
    n_short_choch: int = 0
    fvg_same: int = 0
    fvg_next: int = 0
    fvg_later: int = 0
    shadowed_impulse: int = 0


def _impulse_live(
    fvgs: list[Fvg],
    direction: Literal["bullish", "bearish"],
    interact_ts: datetime,
    next_ts: datetime | None,
) -> bool:
    for fvg in fvgs:
        if fvg.direction != direction:
            continue
        if fvg.state not in ("untouched", "mitigated"):
            continue
        if fvg.size < 15.0:
            continue
        if fvg.formed_at == interact_ts:
            return True
        if next_ts is not None and fvg.formed_at == next_ts:
            return True
    return False


def scan_nested_joins(bars_5m: list[KBar], calendar: TradeCalendar) -> DetectorReport:
    """Bias + sweep + event + FVG≥15. Same unique ident as the scale card's 17."""
    smc_tr = SmcTracker()
    fvg_tr = FvgTracker(min_points=0.0)
    seen_any: set[tuple[date, str, str]] = set()
    seen_choch: set[tuple[date, str, str]] = set()
    report = DetectorReport()
    prefix: list[KBar] = []
    for bar in bars_5m:
        smc_tr.push(bar)
        fvg_tr.push(bar)
        prefix.append(bar)
        if not _in_arm_window(bar.timestamp, calendar):
            continue
        key = session_key(bar.timestamp)
        if key is None:
            continue
        smc = smc_tr.snapshot()
        fvgs = fvg_tr.snapshot()
        rng = smc.dealing_range
        if rng is None:
            continue
        sides: tuple[tuple[Side, Literal["bullish", "bearish"]], ...]
        if rng.position == "discount":
            sides = (("long", "bullish"),)
        elif rng.position == "premium":
            sides = (("short", "bearish"),)
        else:
            continue
        for side, direction in sides:
            swept = _swept_level(smc, side)
            if swept is None or swept.interact_ts is None:
                continue
            sweep_bar = next((b for b in prefix if b.timestamp == swept.interact_ts), None)
            if sweep_bar is None:
                continue
            fvg = _live_fvg(fvgs, direction, swept.interact_ts, 15.0)
            if fvg is None:
                continue
            ident = (key[0], side, swept.interact_ts.isoformat())
            choch_only = [ev for ev in smc.events if ev.kind == "choch"]
            has_any = preferred_event(smc.events, direction, swept.interact_ts, False) is not None
            has_choch = preferred_event(choch_only, direction, swept.interact_ts, False) is not None
            if has_any and ident not in seen_any:
                seen_any.add(ident)
                report.n_nested_any += 1
                if side == "long":
                    report.n_long_any += 1
                else:
                    report.n_short_any += 1
                next_ts = next_5m_after(bars_5m, swept.interact_ts)
                bucket = impulse_bucket(fvg.formed_at, swept.interact_ts, next_ts)
                if bucket == "same":
                    report.fvg_same += 1
                elif bucket == "next":
                    report.fvg_next += 1
                else:
                    report.fvg_later += 1
                    if _impulse_live(fvgs, direction, swept.interact_ts, next_ts):
                        report.shadowed_impulse += 1
            if has_choch and ident not in seen_choch:
                seen_choch.add(ident)
                report.n_nested_choch += 1
                if side == "long":
                    report.n_long_choch += 1
                else:
                    report.n_short_choch += 1
    return report


def _fmt_rate(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.3f}"


def render_funnel_md(payload: dict[str, object]) -> str:
    cell = payload["cell"]
    assert isinstance(cell, dict)
    detector = payload["detector"]
    assert isinstance(detector, dict)
    spells = payload["spells"]
    assert isinstance(spells, dict)
    reasons = payload.get("fill_reasons", {})
    assert isinstance(reasons, dict)
    lines = [
        "# A′ funnel + limit fill rate (not go/no-go)",
        "",
        "Measurement only. One conservative hi-freq cell on the IS tape.",
        "This does **not** elect parameters and is **not** a go/no-go.",
        "Detector unique joins (layer A) are not the fill-rate denominator.",
        "Headline is **n_spells / n_fills**. Round-1's 38 was every-5m `intents_emitted`.",
        "",
        "v1 hi-freq `entry_stopped`×4 / stop×3 / target×1 / flatten×0 is **not** an A′ target.",
        "That cell used nearer-stop + `max_hold=12`. A′ smoke on the same eight dates is",
        "already stop×3 / flatten×5 / no `entry_stopped`. Wider structural R (scale card",
        "min 29, P50 119) and `max_hold=10000` push deaths to 13:40.",
        "**flatten≠0 is not a broker bug.**",
        "",
        f"- git: `{payload.get('git_hash')}`",
        f"- range: `{payload.get('start')}` → `{payload.get('end')}`",
        f"- n_1m: {payload.get('n_1m')}",
        f"- fill_mode: `{payload.get('fill_mode')}`",
        "",
        "## Cell",
        "",
        f"- entry_price: `{cell['entry_price']}`",
        f"- min_points: {cell['min_points']}",
        f"- stop_buffer: {cell['stop_buffer']} (pad)",
        f"- take_profit: `{cell['take_profit']}`",
        f"- require_external: {cell['require_external']}",
        f"- min_r_points: {cell['min_r_points']}",
        "",
        "## Layer A — detector unique `(date, side, interact_ts)`",
        "",
        "Nested join: bias + sweep + event + FVG≥15 (same rule as the scale card's 17).",
        "Census FVG rows are not nested under event; those extra longs are not here.",
        "Nested CHoCH+FVG≥15 is computed on this tape, not assumed from the event layer.",
        "",
        f"- nested any-event + FVG≥15: **{detector['n_nested_any']}** "
        f"(long {detector['n_long_any']} / short {detector['n_short_any']})",
        f"- nested CHoCH + FVG≥15: **{detector['n_nested_choch']}** "
        f"(long {detector['n_long_choch']} / short {detector['n_short_choch']})",
        f"- chosen FVG vs sweep: same 5m {detector['fvg_same']} / "
        f"next 5m bar {detector['fvg_next']} / later {detector['fvg_later']}",
        f"- shadowed impulse (same/next existed, latest-wins picked later): "
        f"{detector['shadowed_impulse']}",
        "",
        "CHoCH barely moves unique "
        f"({detector['n_nested_any']}→{detector['n_nested_choch']}). "
        f"same+next = {detector['fvg_same']}+{detector['fvg_next']}, "
        f"shadowed = {detector['shadowed_impulse']}.",
        "That is the 3b number: latest-wins FVG on the sweep bar or the next 5m",
        "in the **same session**. Hard-cutting impulse to same/next would keep",
        "only those buckets; later joins drop out first — not CHoCH.",
        "Night 15:05 is not the day session's next 5m.",
        "",
        "## Layer B — decide() spells + conservative fill",
        "",
        "A spell is one arm until fill or death. Re-arm after cancel is a second spell.",
        "13:40 unfilled is broker **expire** (no cancel intent). `fill_rate = n_fills / n_spells`.",
        "Nested unique joins are not `n_spells`: occupancy, invalid stop, tick rounding,",
        "and a missing sweep bar sit between detector and arm. Scale-card `min_r=15` kills 0",
        "on this geometry, so that drop is not the cost floor.",
        "",
        f"- n_spells: **{spells['n_spells']}**",
        f"- n_fills: **{spells['n_fills']}** "
        f"(n_fills == n_result_trades == {payload.get('n_result_trades')})",
        f"- fill_rate: **{_fmt_rate(spells['fill_rate'])}**",
        f"- cancel_thesis: {spells['n_cancel_thesis']}",
        f"- unfilled_flatten (expire at flatten, no cancel): {spells['n_unfilled_flatten']}",
        f"- still_open: {spells['n_still_open']}",
        f"- raw 5m arm-closes (appendix; round-1 38 was this kind of count): "
        f"{spells['raw_arm_closes']}",
        "",
        "Fill exit reasons (A′ trades, not v1):",
        "",
        f"- entry_stopped: {reasons.get('entry_stopped', 0)}",
        f"- stop: {reasons.get('stop', 0)}",
        f"- target: {reasons.get('target', 0)}",
        f"- flatten: {reasons.get('flatten', 0)}",
        "",
        "Do not read n or fill rate as edge. CHoCH / impulse FVG are **not** in `decide()`.",
        "A′ day-session elect on this geometry is **closed**. Do not implement 3b",
        "to keep sample, and do not open a second-round grid.",
        "",
    ]
    return "\n".join(lines)


def write_funnel(out_dir: Path, payload: dict[str, object]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "funnel.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (out_dir / "FUNNEL.md").write_text(render_funnel_md(payload), encoding="utf-8")


def _cell_dict(cell: SetupAParams) -> dict[str, object]:
    return {
        "entry_price": cell.entry_price,
        "min_points": cell.min_points,
        "stop_buffer": cell.stop_buffer,
        "take_profit": cell.take_profit,
        "require_external": cell.require_external,
        "min_r_points": cell.min_r_points,
        "max_hold_bars": cell.max_hold_bars,
    }


def _detector_dict(report: DetectorReport) -> dict[str, object]:
    return {
        "n_nested_any": report.n_nested_any,
        "n_nested_choch": report.n_nested_choch,
        "n_long_any": report.n_long_any,
        "n_short_any": report.n_short_any,
        "n_long_choch": report.n_long_choch,
        "n_short_choch": report.n_short_choch,
        "fvg_same": report.fvg_same,
        "fvg_next": report.fvg_next,
        "fvg_later": report.fvg_later,
        "shadowed_impulse": report.shadowed_impulse,
    }


def _spells_dict(counts: SpellCounts) -> dict[str, object]:
    return {
        "n_spells": counts.n_spells,
        "n_fills": counts.n_fills,
        "fill_rate": counts.fill_rate,
        "n_cancel_thesis": counts.n_cancel_thesis,
        "n_unfilled_flatten": counts.n_unfilled_flatten,
        "n_still_open": counts.n_still_open,
        "raw_arm_closes": counts.raw_arm_closes,
    }


def run_funnel(
    bars_1m: list[KBar],
    *,
    params: SetupAParams | None = None,
    out_dir: Path | None = None,
    git_hash: str | None = None,
) -> dict[str, object]:
    ordered = sorted(bars_1m, key=lambda bar: bar.timestamp)
    bars_5m = BarStore(ordered).resample_5m()
    calendar = TradeCalendar()
    detector = scan_nested_joins(bars_5m, calendar)
    cell = smoke_params(params if params is not None else load_setup_a_params())
    cache: IndicatorCache = {}
    tracker = SpellTracker(flatten_time=cell.flatten_time)
    inner = CachedSetupA(cell, calendar, cache, ordered[0].timestamp)
    strategy = FunnelSetupA(inner, tracker)
    result = run(
        ordered,
        strategy,
        load_trading_config(),
        BacktestConfig(fill_mode="conservative"),
        meta=RunMeta(git_hash=git_hash, source_files="funnel"),
    )
    tracker.finish()
    reasons = Counter(trade.reason for trade in result.trades)
    payload: dict[str, object] = {
        "git_hash": resolve_git_hash(RunMeta(git_hash=git_hash)),
        "start": ordered[0].timestamp.isoformat(),
        "end": ordered[-1].timestamp.isoformat(),
        "n_1m": len(ordered),
        "fill_mode": "conservative",
        "cell": _cell_dict(cell),
        "detector": _detector_dict(detector),
        "spells": _spells_dict(tracker.counts),
        "fill_reasons": {
            "entry_stopped": reasons.get("entry_stopped", 0),
            "stop": reasons.get("stop", 0),
            "target": reasons.get("target", 0),
            "flatten": reasons.get("flatten", 0),
        },
        "n_result_trades": len(result.trades),
    }
    if out_dir is not None:
        write_funnel(out_dir, payload)
    return payload


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "A′ funnel + conservative fill rate (closed elect; not go/no-go). "
            "Do not treat output as a license to implement 3b or open a grid."
        )
    )
    parser.add_argument("--start", default=_DEFAULT_START.isoformat())
    parser.add_argument("--end", default=_DEFAULT_END.isoformat())
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUT)
    parser.add_argument("--kbars", type=Path, default=_DEFAULT_KBARS)
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
    payload = run_funnel(bars, out_dir=args.out)
    spells = payload["spells"]
    detector = payload["detector"]
    assert isinstance(spells, dict) and isinstance(detector, dict)
    print(
        json.dumps(
            {
                "out": str(args.out),
                "n_nested_any": detector["n_nested_any"],
                "n_nested_choch": detector["n_nested_choch"],
                "n_spells": spells["n_spells"],
                "n_fills": spells["n_fills"],
                "fill_rate": spells["fill_rate"],
                "n_unfilled_flatten": spells["n_unfilled_flatten"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DetectorReport",
    "FunnelSetupA",
    "SpellCounts",
    "SpellTracker",
    "fill_rate",
    "impulse_bucket",
    "next_5m_after",
    "render_funnel_md",
    "run_funnel",
    "scan_nested_joins",
    "write_funnel",
]
