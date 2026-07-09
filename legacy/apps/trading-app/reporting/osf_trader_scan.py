"""Discretionary trader-style signal scan on OSF timeline + 5m replay."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any, Literal

from pathlib import Path

from reporting.osf_liquidity import compute_liquidity_levels
from reporting.osf_session_context import OsfDayContext, OsfBarStore
from storage.cache_paths import DEFAULT_TICK_CACHE_DIR
from storage.kbar_loader import KBarRecord, iter_kbars_in_range
from storage.session_bar_cache import DAY_ANCHOR, DAY_END, yuanta_resample

SetupWindow = Literal["day_open", "midday", "late_morning"]


@dataclass(frozen=True)
class TraderSignal:
    day: str
    ts: str
    playbook: str
    side: Literal["long"]
    entry_ref: float
    stop_ref: float
    rationale: str
    confidence: Literal["A", "B", "C"]


def _session_window(ts: datetime.datetime) -> SetupWindow | None:
    t = ts.time()
    if datetime.time(9, 30) <= t <= datetime.time(10, 30):
        return "day_open"
    if datetime.time(10, 30) < t <= datetime.time(12, 0):
        return "midday"
    if datetime.time(12, 0) < t <= datetime.time(13, 30):
        return "late_morning"
    return None


def _stack_bullish(row: dict[str, Any]) -> bool:
    pvm = row.get("price_vs_ma") or {}
    return (
        pvm.get("h4_ma20") == "above"
        and pvm.get("h4_ma60") == "above"
        and pvm.get("h1_ma20") in ("above", "at")
    )


def _scan_sweep_reclaim_breakout(
    day: datetime.date,
    bars_15m: list[KBarRecord],
    pools: list[tuple[str, float]],
    bars_5m: list[KBarRecord],
) -> TraderSignal | None:
    """After 15m sweep+reclaim, enter on 5m close above sweep-bar high (no FVG retest)."""
    m5_ts = [b.ts for b in bars_5m]
    for bar in bars_15m:
        if bar.ts.time() < datetime.time(9, 30) or bar.ts.time() > datetime.time(13, 30):
            continue
        low, close, high = float(bar.Low), float(bar.Close), float(bar.High)
        if close < float(bar.Open):
            continue
        hit = [(n, px) for n, px in pools if low < px < close]
        if not hit:
            continue
        pool_name = min(hit, key=lambda x: x[1])[0]
        import bisect

        i5 = bisect.bisect_right(m5_ts, bar.ts)
        for b5 in bars_5m[i5:]:
            if b5.ts.time() > datetime.time(13, 30):
                break
            if float(b5.Close) > high and float(b5.Close) > float(b5.Open):
                return TraderSignal(
                    day=day.isoformat(),
                    ts=b5.ts.isoformat(),
                    playbook="sweep_reclaim_5m_breakout",
                    side="long",
                    entry_ref=round(float(b5.Close), 1),
                    stop_ref=round(low, 1),
                    rationale=(
                        f"15m swept {pool_name} (L{low:.0f}) reclaimed; "
                        f"5m closed above sweep high {high:.0f} — momentum continuation without FVG retest"
                    ),
                    confidence="B",
                )
    return None


def _scan_or_breakout_hold(
    day: datetime.date,
    bars_15m: list[KBarRecord],
    or_high: float,
    bars_5m: list[KBarRecord],
) -> TraderSignal | None:
    """OR high break + first 5m hold above OR (trend-day open drive)."""
    import bisect

    m5_ts = [b.ts for b in bars_5m]
    broke = False
    for bar in bars_15m:
        if bar.ts.time() < datetime.time(9, 30) or bar.ts.time() > datetime.time(11, 0):
            continue
        if float(bar.Close) <= or_high:
            continue
        if not broke:
            broke = True
            i5 = bisect.bisect_right(m5_ts, bar.ts)
            for b5 in bars_5m[i5 : i5 + 3]:
                if float(b5.Low) >= or_high and float(b5.Close) > float(b5.Open):
                    return TraderSignal(
                        day=day.isoformat(),
                        ts=b5.ts.isoformat(),
                        playbook="or_breakout_hold",
                        side="long",
                        entry_ref=round(float(b5.Close), 1),
                        stop_ref=round(or_high - 30, 1),
                        rationale=f"Price held above OR high {or_high:.0f} on 5m after breakout",
                        confidence="B",
                    )
    return None


def _scan_gap_down_reversal(
    day: datetime.date,
    gap_cohort: str,
    bars_15m: list[KBarRecord],
    overnight_low: float | None,
    bars_5m: list[KBarRecord],
) -> TraderSignal | None:
    """Gap down session: V-reversal after tag of overnight low + 5m BOS."""
    if gap_cohort != "gap_down" or overnight_low is None:
        return None
    import bisect

    m5_ts = [b.ts for b in bars_5m]
    tagged = False
    for bar in bars_15m:
        if bar.ts.time() < datetime.time(9, 30):
            continue
        if float(bar.Low) <= overnight_low:
            tagged = True
        if not tagged:
            continue
        if float(bar.Close) < float(bar.Open):
            continue
        swing_hi = max(float(b.High) for b in bars_15m if b.ts <= bar.ts)
        i5 = bisect.bisect_right(m5_ts, bar.ts)
        for b5 in bars_5m[i5:]:
            if b5.ts.time() > datetime.time(13, 30):
                break
            if float(b5.Close) > swing_hi and float(b5.Close) > float(b5.Open):
                return TraderSignal(
                    day=day.isoformat(),
                    ts=b5.ts.isoformat(),
                    playbook="gap_down_v_reversal",
                    side="long",
                    entry_ref=round(float(b5.Close), 1),
                    stop_ref=round(float(bar.Low), 1),
                    rationale=(
                        f"Gap-down tagged overnight {overnight_low:.0f}, "
                        f"15m reclaim + 5m BOS above {swing_hi:.0f}"
                    ),
                    confidence="A",
                )
    return None


def _scan_pullback_ma20(
    day: datetime.date,
    rows: list[dict[str, Any]],
) -> TraderSignal | None:
    """Gap-up day: first 15m touch of 1h MA20 then bullish close (buy dip in trend)."""
    touched = False
    for row in rows:
        if row["m15"]["ts"][:10] != day.isoformat():
            continue
        ts = datetime.datetime.fromisoformat(row["m15"]["ts"])
        if ts.time() < datetime.time(9, 30) or ts.time() > datetime.time(11, 30):
            continue
        ma20 = row["h1"].get("ma20")
        if ma20 is None:
            continue
        m = row["m15"]
        if float(m["L"]) <= ma20 <= float(m["H"]):
            touched = True
        if touched and float(m["C"]) > float(m["O"]) and float(m["C"]) > ma20:
            return TraderSignal(
                day=day.isoformat(),
                ts=row["m15"]["ts"],
                playbook="pullback_h1_ma20",
                side="long",
                entry_ref=float(m["C"]),
                stop_ref=round(ma20 - 40, 1),
                rationale=f"Trend day: first 15m bounce off 1h MA20 ({ma20:.0f})",
                confidence="B",
            )
    return None


def _day_bars_from_disk(
    code: str,
    day: datetime.date,
    minutes: int,
    scope: Literal["day", "both"],
    *,
    cache_dir: Path,
) -> list[KBarRecord]:
    pad = day - datetime.timedelta(days=3)
    end = datetime.datetime.combine(day, DAY_END)
    bars_1m = iter_kbars_in_range(code, pad, day, cache_dir=cache_dir)
    bars_1m = [b for b in bars_1m if b.ts <= end]
    closed, _ = yuanta_resample(bars_1m, minutes, scope, end)
    return [b for b in closed if b.ts.date() == day]


def scan_day_trader_signals(
    code: str,
    day: datetime.date,
    *,
    timeline_rows: list[dict[str, Any]],
    store: OsfBarStore | None = None,
    cache_dir: Path = DEFAULT_TICK_CACHE_DIR,
) -> list[TraderSignal]:
    """Scan one day for discretionary long setups (research only)."""
    if store is None:
        store = OsfBarStore.load_range(code, [day, day + datetime.timedelta(days=1)])
    if store is None:
        return []
    ctx = OsfDayContext.load(code, day, store=store)
    or_end = datetime.datetime.combine(day, DAY_ANCHOR) + datetime.timedelta(minutes=30)
    levels = compute_liquidity_levels(
        ctx.snapshot(or_end).bars_1m, day, or_minutes=30
    )
    bars_15m = _day_bars_from_disk(code, day, 15, "both", cache_dir=cache_dir)
    bars_15m = [b for b in bars_15m if datetime.time(8, 45) <= b.ts.time() <= datetime.time(13, 45)]
    bars_5m = _day_bars_from_disk(code, day, 5, "day", cache_dir=cache_dir)
    bars_5m = [b for b in bars_5m if b.ts.time() <= datetime.time(13, 30)]
    day_rows = [r for r in timeline_rows if r["m15"]["ts"].startswith(day.isoformat())]
    pools: list[tuple[str, float]] = []
    if levels.or_range.valid:
        pools.append(("or_low", levels.or_range.low))
    if levels.dawn_low is not None:
        pools.append(("dawn_low", levels.dawn_low))
    if levels.overnight_low is not None:
        pools.append(("overnight_low", levels.overnight_low))

    out: list[TraderSignal] = []
    for fn, args in (
        (_scan_gap_down_reversal, (day, levels.gap_cohort, bars_15m, levels.overnight_low, bars_5m)),
        (_scan_sweep_reclaim_breakout, (day, bars_15m, pools, bars_5m)),
        (_scan_or_breakout_hold, (day, bars_15m, levels.or_range.high, bars_5m)),
        (_scan_pullback_ma20, (day, day_rows)),
    ):
        sig = fn(*args)  # type: ignore[operator]
        if sig is not None:
            out.append(sig)
    return out


def scan_timeline_trader_signals(
    code: str,
    timeline: dict[str, Any],
    *,
    from_date: datetime.date | None = None,
    to_date: datetime.date | None = None,
) -> dict[str, Any]:
    """Run trader scan across all days in a timeline payload."""
    days = sorted({r["m15"]["ts"][:10] for r in timeline["rows"]})
    if from_date:
        days = [d for d in days if d >= from_date.isoformat()]
    if to_date:
        days = [d for d in days if d <= to_date.isoformat()]
    signals: list[dict[str, Any]] = []
    for d in days:
        day = datetime.date.fromisoformat(d)
        if day.weekday() >= 5:
            continue
        for sig in scan_day_trader_signals(
            code, day, timeline_rows=timeline["rows"]
        ):
            signals.append(
                {
                    "day": sig.day,
                    "ts": sig.ts,
                    "playbook": sig.playbook,
                    "entry_ref": sig.entry_ref,
                    "stop_ref": sig.stop_ref,
                    "rationale": sig.rationale,
                    "confidence": sig.confidence,
                }
            )
    playbooks = sorted({s["playbook"] for s in signals})
    return {
        "n_signals": len(signals),
        "playbooks_seen": playbooks,
        "signals": signals,
        "notes": (
            "Discretionary research signals — not OSF rules. "
            "5m from day-session store; late setups may need extended 5m lookback."
        ),
    }