from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from pathlib import Path

from tfx_trading.backtest.config import BacktestConfig
from tfx_trading.backtest.engine import run
from tfx_trading.backtest.ledger import RunMeta, resolve_git_hash
from tfx_trading.backtest.scale_card import percentile
from tfx_trading.backtest.sweep import CachedSetupA, IndicatorCache
from tfx_trading.bar_reader import BarReader
from tfx_trading.bar_store import session_key, session_kind
from tfx_trading.calendar import TradeCalendar
from tfx_trading.kbar import KBar
from tfx_trading.strategy.protocol import DecisionContext
from tfx_trading.strategy.setup_a import SetupAParams, load_setup_a_params
from tfx_trading.trading.costs import POINT_VALUE_NT, load_trading_config
from tfx_trading.trading.models import Intent, Side, TradeRecord

_DEFAULT_KBARS = Path(__file__).resolve().parent.parent / "kbars_data"
_DEFAULT_OUT = Path(__file__).resolve().parents[2] / "docs" / "phase4_round2_2026-09-04" / "smoke"
_DEFAULT_START = date(2025, 5, 7)
_DEFAULT_END = date(2025, 9, 16)
SCORECARD_DATES: tuple[date, ...] = (
    date(2025, 5, 14),
    date(2025, 5, 15),
    date(2025, 5, 26),
    date(2025, 7, 9),
    date(2025, 7, 15),
    date(2025, 7, 21),
    date(2025, 8, 15),
    date(2025, 9, 15),
)


@dataclass
class FloorCounts:
    raw_closes: int = 0
    unique: set[tuple[date, Side]] = field(default_factory=set)


class FloorProbe:
    """CachedSetupA pair: engine sees min_r=15; probe counts arms killed by the floor."""

    def __init__(self, live: CachedSetupA, open_floor: CachedSetupA) -> None:
        self._live = live
        self._open = open_floor
        self.counts = FloorCounts()

    def decide(self, ctx: DecisionContext) -> list[Intent]:
        open_intents = self._open.decide(ctx)
        live_intents = self._live.decide(ctx)
        if is_arm_bracket(open_intents) and live_intents == []:
            self.counts.raw_closes += 1
            key = session_key(ctx.bar_1m.timestamp)
            side = open_intents[0].side
            if key is not None and side is not None:
                self.counts.unique.add((key[0], side))
        return live_intents


def is_arm_bracket(intents: list[Intent]) -> bool:
    return [item.kind for item in intents] == ["place_limit", "place_stop", "place_limit"]


def r_points_from_trade(trade: TradeRecord) -> float | None:
    if trade.r_multiple is None or trade.r_multiple == 0 or trade.qty == 0:
        return None
    return abs(trade.pnl_nt / trade.r_multiple) / (POINT_VALUE_NT * trade.qty)


def trade_day(ts: datetime) -> date:
    key = session_key(ts)
    if key is not None:
        return key[0]
    return ts.date()


def day_hl_by_date(bars_1m: list[KBar]) -> dict[date, float]:
    buckets: dict[date, list[KBar]] = {}
    for bar in bars_1m:
        if session_kind(bar.timestamp) != "day":
            continue
        key = session_key(bar.timestamp)
        if key is None:
            continue
        buckets.setdefault(key[0], []).append(bar)
    return {
        day: max(bar.high for bar in day_bars) - min(bar.low for bar in day_bars)
        for day, day_bars in buckets.items()
    }


def smoke_params(base: SetupAParams) -> SetupAParams:
    return replace(
        base,
        entry_price="top",
        min_points=15.0,
        stop_buffer=3.0,
        take_profit="2R",
        require_external=False,
        min_r_points=15.0,
    )


def _r_summary(values: list[float]) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    return min(values), percentile(values, 0.5)


def _fill_row(trade: TradeRecord, day_hl: dict[date, float]) -> dict[str, object]:
    session = trade_day(trade.entry_ts)
    raw_r = r_points_from_trade(trade)
    r_points = None if raw_r is None else round(raw_r, 2)
    two_r = None if r_points is None else round(2.0 * r_points, 2)
    hl = day_hl.get(session)
    gt: bool | None
    if two_r is None or hl is None:
        gt = None
    else:
        gt = two_r > hl
    return {
        "side": trade.side,
        "entry_ts": trade.entry_ts.isoformat(),
        "entry_price": trade.entry_price,
        "exit_ts": trade.exit_ts.isoformat(),
        "exit_price": trade.exit_price,
        "r_points": r_points,
        "two_r_points": two_r,
        "day_hl": hl,
        "two_r_gt_day_hl": gt,
        "reason": trade.reason,
        "session_date": session.isoformat(),
        "on_scorecard": session in SCORECARD_DATES,
    }


def _fmt(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}"


def _unique_payload(unique: set[tuple[date, Side]]) -> list[dict[str, str]]:
    return [
        {"date": day.isoformat(), "side": side}
        for day, side in sorted(unique, key=lambda item: (item[0], item[1]))
    ]


def _scorecard_lines(fills: list[dict[str, object]]) -> list[str]:
    by_day: dict[date, list[dict[str, object]]] = {day: [] for day in SCORECARD_DATES}
    for row in fills:
        if not row["on_scorecard"]:
            continue
        day = date.fromisoformat(str(row["session_date"]))
        by_day[day].append(row)
    lines = [
        "| date | n | side | reason | R | 2R | day H−L | 2R > H−L |",
        "|---|---:|---|---|---:|---:|---:|---|",
    ]
    for day in SCORECARD_DATES:
        rows = by_day[day]
        if not rows:
            lines.append(f"| {day.isoformat()} | 0 | — | no_trade | — | — | — | — |")
            continue
        for row in rows:
            gt = row["two_r_gt_day_hl"]
            gt_txt = "—" if gt is None else ("yes" if gt else "no")
            r_raw = row["r_points"]
            two_raw = row["two_r_points"]
            hl_raw = row["day_hl"]
            r_val = float(r_raw) if isinstance(r_raw, (int, float)) else None
            two_val = float(two_raw) if isinstance(two_raw, (int, float)) else None
            hl_val = float(hl_raw) if isinstance(hl_raw, (int, float)) else None
            lines.append(
                f"| {day.isoformat()} | 1 | {row['side']} | {row['reason']} | "
                f"{_fmt(r_val)} | {_fmt(two_val)} | {_fmt(hl_val)} | {gt_txt} |"
            )
    return lines


def _appendix_lines(fills: list[dict[str, object]]) -> list[str]:
    extra = [row for row in fills if not row["on_scorecard"]]
    if not extra:
        return ["No other fills in the load window.", ""]
    lines = [
        "| date | side | reason | R | 2R | day H−L | 2R > H−L |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for row in extra:
        gt = row["two_r_gt_day_hl"]
        gt_txt = "—" if gt is None else ("yes" if gt else "no")
        r_raw = row["r_points"]
        two_raw = row["two_r_points"]
        hl_raw = row["day_hl"]
        r_val = float(r_raw) if isinstance(r_raw, (int, float)) else None
        two_val = float(two_raw) if isinstance(two_raw, (int, float)) else None
        hl_val = float(hl_raw) if isinstance(hl_raw, (int, float)) else None
        lines.append(
            f"| {row['session_date']} | {row['side']} | {row['reason']} | "
            f"{_fmt(r_val)} | {_fmt(two_val)} | {_fmt(hl_val)} | {gt_txt} |"
        )
    lines.append("")
    return lines


def render_smoke_md(payload: dict[str, object]) -> str:
    cell = payload["cell"]
    assert isinstance(cell, dict)
    agg = payload["aggregates"]
    assert isinstance(agg, dict)
    fills_raw = payload["fills"]
    assert isinstance(fills_raw, list)
    fills = [row for row in fills_raw if isinstance(row, dict)]
    lines = [
        "# A′ cost-floor smoke (not go/no-go)",
        "",
        "Measurement only. One conservative cell, eight v1 hi-freq **calendar** dates.",
        "This does **not** elect parameters and is **not** a go/no-go. n≪30 is expected.",
        "If many trades flatten at 13:40 before 2R, that is the scale card "
        "(2R ≈ day-range P50 243), not a cost-floor bug.",
        "",
        f"- git: `{payload.get('git_hash')}`",
        f"- range: `{payload.get('start')}` → `{payload.get('end')}`",
        f"- n_1m: {payload.get('n_1m')}",
        f"- fill_mode: `{payload.get('fill_mode')}`",
        "",
        "## Cell (hi-freq blotter alignment; stop is A′)",
        "",
        f"- entry_price: `{cell['entry_price']}`",
        f"- min_points: {cell['min_points']} (not config default 20)",
        f"- stop_buffer: {cell['stop_buffer']} (pad, not R)",
        f"- take_profit: `{cell['take_profit']}`",
        f"- require_external: {cell['require_external']}",
        f"- min_r_points: {cell['min_r_points']} (3× round-trip, not noise)",
        "",
        "## Aggregates",
        "",
        f"- n_trades (window): {agg['n_trades']}",
        f"- n_trades on 8 dates: {agg['n_scorecard']}",
        f"- flatten share (window): {_fmt(agg['flatten_share'], 3)}",
        f"- R min / P50 (window): {_fmt(agg['r_min'])} / {_fmt(agg['r_p50'])}",
        f"- r_below_floor unique `(date, side)`: {agg['r_below_floor_unique']}",
        f"- r_below_floor raw 5m closes: {agg['r_below_floor_raw']}",
        "",
        "## Scorecard (8 v1 fill dates)",
        "",
        "A′ stops will not replay the v1 blotter rows. `no_trade` is a valid outcome.",
        "",
        *_scorecard_lines(fills),
        "",
        "## Appendix (other fills in the load window)",
        "",
        *_appendix_lines(fills),
        "Do not read n or flatten share as edge.",
        "A′ day-session elect is a dead end; this smoke is not a license to grid.",
        "",
    ]
    return "\n".join(lines)


def write_smoke(out_dir: Path, payload: dict[str, object]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "smoke.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (out_dir / "SMOKE.md").write_text(render_smoke_md(payload), encoding="utf-8")


def run_smoke(
    bars_1m: list[KBar],
    *,
    params: SetupAParams | None = None,
    out_dir: Path | None = None,
    git_hash: str | None = None,
) -> dict[str, object]:
    ordered = sorted(bars_1m, key=lambda bar: bar.timestamp)
    cell = smoke_params(params if params is not None else load_setup_a_params())
    cache: IndicatorCache = {}
    calendar = TradeCalendar()
    window_start = ordered[0].timestamp
    live = CachedSetupA(cell, calendar, cache, window_start)
    opened = CachedSetupA(replace(cell, min_r_points=0.0), calendar, cache, window_start)
    probe = FloorProbe(live, opened)
    cost = load_trading_config()
    result = run(
        ordered,
        probe,
        cost,
        BacktestConfig(fill_mode="conservative"),
        meta=RunMeta(git_hash=git_hash, source_files="smoke"),
    )
    day_hl = day_hl_by_date(ordered)
    fills = [_fill_row(trade, day_hl) for trade in result.trades]
    r_values = [
        float(row["r_points"]) for row in fills if isinstance(row["r_points"], (int, float))
    ]
    r_min, r_p50 = _r_summary(r_values)
    n_trades = len(fills)
    n_flat = sum(1 for row in fills if row["reason"] == "flatten")
    n_score = sum(1 for row in fills if row["on_scorecard"])
    payload: dict[str, object] = {
        "git_hash": resolve_git_hash(RunMeta(git_hash=git_hash)),
        "start": ordered[0].timestamp.isoformat(),
        "end": ordered[-1].timestamp.isoformat(),
        "n_1m": len(ordered),
        "fill_mode": "conservative",
        "cell": {
            "entry_price": cell.entry_price,
            "min_points": cell.min_points,
            "stop_buffer": cell.stop_buffer,
            "take_profit": cell.take_profit,
            "require_external": cell.require_external,
            "min_r_points": cell.min_r_points,
        },
        "aggregates": {
            "n_trades": n_trades,
            "n_scorecard": n_score,
            "flatten_share": None if n_trades == 0 else n_flat / n_trades,
            "r_min": r_min,
            "r_p50": r_p50,
            "r_below_floor_unique": len(probe.counts.unique),
            "r_below_floor_raw": probe.counts.raw_closes,
            "r_below_floor": _unique_payload(probe.counts.unique),
        },
        "fills": fills,
        "scorecard_dates": [day.isoformat() for day in SCORECARD_DATES],
    }
    if out_dir is not None:
        write_smoke(out_dir, payload)
    return payload


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "A′ cost-floor smoke (one conservative cell; not elect). "
            "Day-session A′ elect is closed; see docs/phase4_round2_2026-09-04/CLOSED.md"
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
    payload = run_smoke(bars, out_dir=args.out)
    agg = payload["aggregates"]
    assert isinstance(agg, dict)
    print(
        json.dumps(
            {
                "out": str(args.out),
                "n_trades": agg["n_trades"],
                "r_below_floor_unique": agg["r_below_floor_unique"],
                "r_below_floor_raw": agg["r_below_floor_raw"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "FloorProbe",
    "SCORECARD_DATES",
    "day_hl_by_date",
    "is_arm_bracket",
    "r_points_from_trade",
    "render_smoke_md",
    "run_smoke",
    "smoke_params",
    "trade_day",
    "write_smoke",
]
