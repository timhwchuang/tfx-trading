from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Literal

from tfx_trading.backtest.census import _in_arm_window, _live_fvg
from tfx_trading.backtest.ledger import resolve_git_hash
from tfx_trading.bar_reader import BarReader
from tfx_trading.bar_store import BarStore, session_key, session_kind
from tfx_trading.calendar import TradeCalendar
from tfx_trading.indicators.fvg import FvgTracker
from tfx_trading.indicators.smc import SmcTracker
from tfx_trading.kbar import KBar
from tfx_trading.strategy.setup_a import _swept_level, preferred_event
from tfx_trading.trading.costs import POINT_VALUE_NT, TAX_RATE, commission_nt, load_trading_config
from tfx_trading.trading.models import Side

_DEFAULT_KBARS = Path(__file__).resolve().parent.parent / "kbars_data"
_OPEN_END = time(9, 15)
_ARM_END = time(13, 40)


@dataclass
class Pct:
    n: int
    p50: float
    p90: float
    share_ge_3: float
    share_ge_5: float
    share_ge_10: float
    share_ge_15: float


@dataclass
class JoinR:
    n: int
    n_short: int
    n_long: int
    n_short_v1_r_eq_buffer: int
    v1_r_p50: float | None
    a_prime_r_p50: float | None
    a_prime_r_min: float | None
    a_prime_long_p50: float | None
    a_prime_short_p50: float | None
    a_prime_below_min_r15: int


@dataclass
class ScaleCard:
    n_1m: int = 0
    median_day_close: float | None = None
    round_trip_pts: float | None = None
    day_1m: Pct | None = None
    arm_1m: Pct | None = None
    open_1m: Pct | None = None
    day_5m: Pct | None = None
    atr14_day_5m_chained: Pct | None = None
    atr14_day_5m_reset: Pct | None = None
    day_hl_1m: Pct | None = None
    session_1m: dict[str, Pct] = field(default_factory=dict)
    join_r: JoinR | None = None
    notes: dict[str, str] = field(default_factory=dict)


def percentile(xs: list[float], p: float) -> float:
    if not xs:
        raise ValueError("empty sample")
    ordered = sorted(xs)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * p
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    weight = rank - lo
    return ordered[lo] * (1.0 - weight) + ordered[hi] * weight


def _pct(xs: list[float]) -> Pct:
    n = len(xs)
    if n == 0:
        return Pct(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    return Pct(
        n=n,
        p50=round(percentile(xs, 0.5), 2),
        p90=round(percentile(xs, 0.9), 2),
        share_ge_3=round(sum(1 for x in xs if x >= 3.0) / n, 4),
        share_ge_5=round(sum(1 for x in xs if x >= 5.0) / n, 4),
        share_ge_10=round(sum(1 for x in xs if x >= 10.0) / n, 4),
        share_ge_15=round(sum(1 for x in xs if x >= 15.0) / n, 4),
    )


def _ranges(bars: list[KBar]) -> list[float]:
    return [bar.high - bar.low for bar in bars]


def _wilder_atr(bars: list[KBar], period: int = 14) -> list[float]:
    if len(bars) < period + 1:
        return []
    trs: list[float] = []
    for i, bar in enumerate(bars):
        span = bar.high - bar.low
        if i == 0:
            trs.append(span)
            continue
        prev = bars[i - 1].close
        trs.append(max(span, abs(bar.high - prev), abs(bar.low - prev)))
    atr = sum(trs[1 : period + 1]) / period
    out = [atr]
    for tr in trs[period + 1 :]:
        atr = (atr * (period - 1) + tr) / period
        out.append(atr)
    return out


def _session_clock(bars_1m: list[KBar]) -> dict[str, Pct]:
    windows: tuple[tuple[str, time | None, time | None, str], ...] = (
        ("open_0850_0915", time(8, 50), time(9, 15), "day"),
        ("am_0915_1030", time(9, 15), time(10, 30), "day"),
        ("mid_1100_1300", time(11, 0), time(13, 0), "day"),
        ("close_1330_1345", time(13, 30), time(13, 46), "day"),
        ("night", None, None, "night"),
    )
    out: dict[str, Pct] = {}
    for name, start_t, end_t, kind in windows:
        xs: list[float] = []
        for bar in bars_1m:
            if session_kind(bar.timestamp) != kind:
                continue
            clock = bar.timestamp.time()
            if start_t is not None and end_t is not None and not (start_t <= clock < end_t):
                continue
            xs.append(bar.high - bar.low)
        out[name] = _pct(xs)
    return out


def _day_hl(bars_1m: list[KBar]) -> list[float]:
    buckets: dict[date, list[KBar]] = {}
    for bar in bars_1m:
        if session_kind(bar.timestamp) != "day":
            continue
        key = session_key(bar.timestamp)
        if key is None:
            continue
        buckets.setdefault(key[0], []).append(bar)
    out: list[float] = []
    for day_bars in buckets.values():
        high = max(bar.high for bar in day_bars)
        low = min(bar.low for bar in day_bars)
        out.append(high - low)
    return out


def _round_trip_pts(price: float) -> float:
    cfg = load_trading_config()
    tax = price * POINT_VALUE_NT * TAX_RATE * 2.0
    nt = commission_nt(1, cfg) * 2.0 + tax
    return nt / POINT_VALUE_NT


def _atr_reset_each_day(day_5m: list[KBar]) -> list[float]:
    by_day: dict[date, list[KBar]] = {}
    for bar in day_5m:
        key = session_key(bar.timestamp)
        if key is None:
            continue
        by_day.setdefault(key[0], []).append(bar)
    out: list[float] = []
    for bars in by_day.values():
        series = _wilder_atr(bars)
        if series:
            out.append(series[-1])
    return out


def _join_r(bars_5m: list[KBar], calendar: TradeCalendar, buffer: float = 3.0) -> JoinR:
    smc_tr = SmcTracker()
    fvg_tr = FvgTracker(min_points=0.0)
    seen: set[tuple[date, str, str]] = set()
    v1: list[float] = []
    ap: list[float] = []
    ap_long: list[float] = []
    ap_short: list[float] = []
    n_short = 0
    n_eq = 0
    below_15 = 0
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
            if preferred_event(smc.events, direction, swept.interact_ts, False) is None:
                continue
            fvg = _live_fvg(fvgs, direction, swept.interact_ts, 15.0)
            if fvg is None:
                continue
            ident = (key[0], side, swept.interact_ts.isoformat())
            if ident in seen:
                continue
            sweep_bar = next((b for b in prefix if b.timestamp == swept.interact_ts), None)
            if sweep_bar is None:
                continue
            seen.add(ident)
            entry = fvg.top
            if side == "long":
                v1_stop = max(sweep_bar.low - buffer, fvg.bottom - buffer)
                ap_stop = sweep_bar.low - buffer
            else:
                v1_stop = min(sweep_bar.high + buffer, fvg.top + buffer)
                ap_stop = sweep_bar.high + buffer
                n_short += 1
            v1_r = abs(entry - v1_stop)
            ap_r = abs(entry - ap_stop)
            v1.append(v1_r)
            ap.append(ap_r)
            if side == "long":
                ap_long.append(ap_r)
            else:
                ap_short.append(ap_r)
                if abs(v1_r - buffer) < 1e-9:
                    n_eq += 1
            if ap_r < 15.0:
                below_15 += 1
    n = len(v1)
    return JoinR(
        n=n,
        n_short=n_short,
        n_long=n - n_short,
        n_short_v1_r_eq_buffer=n_eq,
        v1_r_p50=round(percentile(v1, 0.5), 2) if v1 else None,
        a_prime_r_p50=round(percentile(ap, 0.5), 2) if ap else None,
        a_prime_r_min=round(min(ap), 2) if ap else None,
        a_prime_long_p50=round(percentile(ap_long, 0.5), 2) if ap_long else None,
        a_prime_short_p50=round(percentile(ap_short, 0.5), 2) if ap_short else None,
        a_prime_below_min_r15=below_15,
    )


def build_scale_card(bars_1m: list[KBar], calendar: TradeCalendar | None = None) -> ScaleCard:
    cal = calendar if calendar is not None else TradeCalendar()
    ordered = sorted(bars_1m, key=lambda bar: bar.timestamp)
    day_1m = [b for b in ordered if session_kind(b.timestamp) == "day"]
    arm_1m = [b for b in day_1m if time(9, 15) <= b.timestamp.time() < _ARM_END]
    open_1m = [b for b in day_1m if time(8, 50) <= b.timestamp.time() < _OPEN_END]
    day_5m = [b for b in BarStore(ordered).resample_5m() if session_kind(b.timestamp) == "day"]
    closes = [b.close for b in day_1m]
    median_close = percentile(closes, 0.5) if closes else None
    atr_chained = _wilder_atr(day_5m)
    atr_reset = _atr_reset_each_day(day_5m)
    all_5m = BarStore(ordered).resample_5m()
    return ScaleCard(
        n_1m=len(ordered),
        median_day_close=round(median_close, 1) if median_close is not None else None,
        round_trip_pts=round(_round_trip_pts(median_close), 2) if median_close is not None else None,
        day_1m=_pct(_ranges(day_1m)),
        arm_1m=_pct(_ranges(arm_1m)),
        open_1m=_pct(_ranges(open_1m)),
        day_5m=_pct(_ranges(day_5m)),
        atr14_day_5m_chained=_pct(atr_chained),
        atr14_day_5m_reset=_pct(atr_reset),
        day_hl_1m=_pct(_day_hl(day_1m)),
        session_1m=_session_clock(ordered),
        join_r=_join_r(all_5m, cal, buffer=3.0),
        notes={
            "atr14_day_5m_chained": "Wilder ATR(14) on concatenated day 5m (overnight gap in TR)",
            "atr14_day_5m_reset": "Wilder ATR(14) last value of each day session (no overnight TR)",
            "join_r": "First (date, side, interact_ts) with bias+sweep+any event+FVG>=15; v1 vs A' sweep-extreme stop, buffer=3",
        },
    )


def write_scale_card(card: ScaleCard, out_dir: Path, meta: dict[str, object]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {"meta": meta, "card": asdict(card)}
    (out_dir / "scale_card.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    assert card.day_1m is not None
    assert card.arm_1m is not None
    assert card.open_1m is not None
    assert card.day_5m is not None
    assert card.atr14_day_5m_chained is not None
    assert card.atr14_day_5m_reset is not None
    assert card.day_hl_1m is not None
    join = card.join_r
    lines = [
        "# TMFR1 IS scale card",
        "",
        "Measured from tape. Numbers are the grid's licence to exist, not a vibe.",
        "Recite before `decide()`: [TMF_DESK_CARD.md](../../TMF_DESK_CARD.md).",
        "",
        f"- git: `{meta.get('git_hash')}`",
        f"- range: `{meta.get('start')}` → `{meta.get('end')}`",
        f"- n_1m: {card.n_1m}; median day close: {card.median_day_close}",
        f"- round-trip at that close: **{card.round_trip_pts} pts**",
        "",
        "## Three layers (do not mix)",
        "",
        "| Layer | Tape measure | P50 | P90 | Role |",
        "|---|---|---:|---:|---|",
        f"| Cost floor | round-trip | {card.round_trip_pts} | — | R below this is not a trade |",
        f"| Noise 1m (day) | high−low | {card.day_1m.p50} | {card.day_1m.p90} | ≥5 pts share {card.day_1m.share_ge_5:.0%} |",
        f"| Noise 1m (09:15–13:40) | high−low | {card.arm_1m.p50} | {card.arm_1m.p90} | arm window |",
        f"| Noise 1m (08:50–09:14) | high−low | {card.open_1m.p50} | {card.open_1m.p90} | no_trade_before is right |",
        f"| Decision 5m | high−low | {card.day_5m.p50} | {card.day_5m.p90} | one decide bar |",
        f"| ATR(14) day 5m chained | Wilder | {card.atr14_day_5m_chained.p50} | {card.atr14_day_5m_chained.p90} | |",
        f"| ATR(14) day 5m reset | Wilder last/day | {card.atr14_day_5m_reset.p50} | {card.atr14_day_5m_reset.p90} | |",
        f"| Session range | day 1m H−L | {card.day_hl_1m.p50} | {card.day_hl_1m.p90} | 2R must fit before 13:40 |",
        "",
        "## Session clock (1m high−low)",
        "",
        "| Window | n | P50 | P90 | Remember |",
        "|---|---:|---:|---:|---|",
    ]
    session_notes = {
        "open_0850_0915": "fattest 1m; no_trade_before",
        "am_0915_1030": "fattest tradable; easiest to stop out",
        "mid_1100_1300": "thin; limits often unfilled",
        "close_1330_1345": "flatten/settlement; do not wait for 2R",
        "night": "thinner 1m; prev_night still feeds day Setup A",
    }
    for name, sample in card.session_1m.items():
        note = session_notes.get(name, "")
        lines.append(f"| {name} | {sample.n} | {sample.p50} | {sample.p90} | {note} |")
    lines.extend(["",])
    if join is not None:
        lines.extend(
            [
                "## v1 vs A′ R on first joined setups (FVG≥15, buffer=3)",
                "",
                f"- unique joins: **{join.n}** (long {join.n_long} / short {join.n_short})",
                f"- shorts with v1 R exactly = 3: **{join.n_short_v1_r_eq_buffer}**",
                f"- v1 R P50: {join.v1_r_p50}",
                f"- A′ sweep-extreme R P50: {join.a_prime_r_p50} (long {join.a_prime_long_p50} / short {join.a_prime_short_p50})",
                f"- A′ R min: {join.a_prime_r_min}; below min_r=15: {join.a_prime_below_min_r15}",
                "",
            ]
        )
    (out_dir / "SCALE_CARD.md").write_text("\n".join(lines), encoding="utf-8")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure TMFR1 noise/structure/cost scale card")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--kbars", type=Path, default=_DEFAULT_KBARS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    if not args.kbars.is_dir():
        print(f"skip: no kbars_data at {args.kbars}", file=sys.stderr)
        return 1
    bars = BarReader(args.kbars).load(start, end)
    if not bars:
        print("skip: no kbars in range", file=sys.stderr)
        return 1
    card = build_scale_card(bars)
    meta: dict[str, object] = {
        "git_hash": resolve_git_hash(None),
        "start": start.isoformat(),
        "end": end.isoformat(),
    }
    write_scale_card(card, args.out, meta)
    print(json.dumps(asdict(card), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
