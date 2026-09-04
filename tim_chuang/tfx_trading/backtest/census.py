from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Literal

from tfx_trading.backtest.ledger import resolve_git_hash
from tfx_trading.bar_reader import BarReader
from tfx_trading.bar_store import BarStore, session_key, session_kind
from tfx_trading.calendar import TradeCalendar
from tfx_trading.indicators.fvg import Fvg
from tfx_trading.indicators.fvg import FvgTracker
from tfx_trading.indicators.smc import SessionLevel, SmcLevels, SmcTracker, StructureEvent
from tfx_trading.kbar import KBar
from tfx_trading.strategy.setup_a import _swept_level, preferred_event
from tfx_trading.trading.models import Side

_DEFAULT_KBARS = Path(__file__).resolve().parent.parent / "kbars_data"
_ARM_FROM = time(9, 15)
_FLATTEN = time(13, 40)
_MINS = (15.0, 20.0, 30.0)
LevelName = Literal["pdh", "pdl", "prev_night_high", "prev_night_low"]
_LEVELS: tuple[LevelName, ...] = ("pdh", "pdl", "prev_night_high", "prev_night_low")


@dataclass
class _LevelFp:
    interact: str
    interact_ts: str | None


@dataclass
class CensusTotals:
    n_5m: int = 0
    n_day_5m: int = 0
    n_arm_window_5m: int = 0
    n_settlement_day_5m: int = 0
    n_day_sessions: int = 0
    sweep_onset: dict[str, int] = field(default_factory=dict)
    taken_onset: dict[str, int] = field(default_factory=dict)
    live_swept_bars: dict[str, int] = field(default_factory=dict)
    live_taken_bars: dict[str, int] = field(default_factory=dict)
    events_new: dict[str, int] = field(default_factory=dict)
    fvg_formed: dict[str, int] = field(default_factory=dict)
    arm_window: dict[str, int] = field(default_factory=dict)
    unique_sweeps: dict[str, int] = field(default_factory=dict)


def _fp(level: SessionLevel | None) -> _LevelFp:
    if level is None:
        return _LevelFp("missing", None)
    if level.interact is None:
        return _LevelFp("none", None)
    ts = level.interact_ts.isoformat() if level.interact_ts is not None else None
    return _LevelFp(level.interact, ts)


def _level(smc: SmcLevels, name: LevelName) -> SessionLevel | None:
    return {
        "pdh": smc.pdh,
        "pdl": smc.pdl,
        "prev_night_high": smc.prev_night_high,
        "prev_night_low": smc.prev_night_low,
    }[name]


def _event_key(ev: StructureEvent) -> str:
    return f"{ev.kind}|{ev.direction}|{ev.scope}"


def _live_fvg(
    fvgs: list[Fvg],
    direction: Literal["bullish", "bearish"],
    interact_ts: datetime,
    min_points: float,
) -> Fvg | None:
    chosen: Fvg | None = None
    for fvg in fvgs:
        if fvg.direction != direction:
            continue
        if fvg.state not in ("untouched", "mitigated"):
            continue
        if fvg.size < min_points:
            continue
        if fvg.formed_at < interact_ts:
            continue
        if chosen is None or fvg.formed_at >= chosen.formed_at:
            chosen = fvg
    return chosen


def _in_arm_window(ts: datetime, calendar: TradeCalendar) -> bool:
    if session_kind(ts) != "day":
        return False
    key = session_key(ts)
    if key is None:
        return False
    if calendar.is_settlement_day(key[0]):
        return False
    clock = ts.time()
    return _ARM_FROM <= clock < _FLATTEN


def census_5m_tape(bars_5m: list[KBar], calendar: TradeCalendar | None = None) -> CensusTotals:
    """Walk resampled 5m left-to-right. Does not call SetupA.decide."""
    cal = calendar if calendar is not None else TradeCalendar()
    smc_tr = SmcTracker()
    fvg_tr = FvgTracker(min_points=0.0)
    prev: dict[LevelName, _LevelFp] = {name: _LevelFp("missing", None) for name in _LEVELS}
    seen_events: set[tuple[datetime, str, str, str]] = set()
    seen_fvg: set[tuple[datetime, str, float]] = set()
    day_sessions: set[date] = set()
    unique_sweeps: dict[str, set[tuple[date, str, str]]] = defaultdict(set)
    totals = CensusTotals(
        sweep_onset={name: 0 for name in _LEVELS},
        taken_onset={name: 0 for name in _LEVELS},
        live_swept_bars={name: 0 for name in _LEVELS},
        live_taken_bars={name: 0 for name in _LEVELS},
        events_new={},
        fvg_formed={f"ge_{int(m)}": 0 for m in _MINS} | {"any": 0},
        arm_window={
            "bars": 0,
            "long_swept": 0,
            "short_swept": 0,
            "long_any_event": 0,
            "short_any_event": 0,
            "long_choch": 0,
            "short_choch": 0,
            "long_external": 0,
            "short_external": 0,
            "long_fvg15": 0,
            "short_fvg15": 0,
            "long_fvg20": 0,
            "short_fvg20": 0,
            "long_fvg30": 0,
            "short_fvg30": 0,
        },
        unique_sweeps={},
    )
    for bar in bars_5m:
        smc_tr.push(bar)
        fvg_tr.push(bar)
        kind = session_kind(bar.timestamp)
        if kind is None:
            continue
        totals.n_5m += 1
        key = session_key(bar.timestamp)
        smc = smc_tr.snapshot()
        fvgs = fvg_tr.snapshot()
        if kind == "day" and key is not None:
            totals.n_day_5m += 1
            day_sessions.add(key[0])
            if cal.is_settlement_day(key[0]):
                totals.n_settlement_day_5m += 1
        for name in _LEVELS:
            cur = _fp(_level(smc, name))
            old = prev[name]
            if cur.interact == "swept" and (old.interact != "swept" or old.interact_ts != cur.interact_ts):
                totals.sweep_onset[name] += 1
            if cur.interact == "taken" and (old.interact != "taken" or old.interact_ts != cur.interact_ts):
                totals.taken_onset[name] += 1
            if cur.interact == "swept":
                totals.live_swept_bars[name] += 1
            if cur.interact == "taken":
                totals.live_taken_bars[name] += 1
            prev[name] = cur
        for ev in smc.events:
            ident = (ev.ts, ev.kind, ev.direction, ev.scope)
            if ident in seen_events:
                continue
            seen_events.add(ident)
            ek = _event_key(ev)
            totals.events_new[ek] = totals.events_new.get(ek, 0) + 1
        for fvg in fvgs:
            ident_f = (fvg.formed_at, fvg.direction, round(fvg.size, 4))
            if ident_f in seen_fvg:
                continue
            seen_fvg.add(ident_f)
            totals.fvg_formed["any"] += 1
            for m in _MINS:
                if fvg.size >= m:
                    totals.fvg_formed[f"ge_{int(m)}"] += 1
        if not _in_arm_window(bar.timestamp, cal) or key is None:
            continue
        totals.n_arm_window_5m += 1
        totals.arm_window["bars"] += 1
        session_date = key[0]
        _count_join(totals, unique_sweeps, smc, fvgs, session_date, "long")
        _count_join(totals, unique_sweeps, smc, fvgs, session_date, "short")
    totals.n_day_sessions = len(day_sessions)
    totals.unique_sweeps = {k: len(v) for k, v in unique_sweeps.items()}
    return totals


def _count_join(
    totals: CensusTotals,
    unique_sweeps: dict[str, set[tuple[date, str, str]]],
    smc: SmcLevels,
    fvgs: list[Fvg],
    session_date: date,
    side: Side,
) -> None:
    swept = _swept_level(smc, side)
    prefix = "long" if side == "long" else "short"
    rng = smc.dealing_range
    if rng is None:
        return
    if side == "long" and rng.position != "discount":
        return
    if side == "short" and rng.position != "premium":
        return
    if swept is None or swept.interact_ts is None:
        return
    totals.arm_window[f"{prefix}_swept"] += 1
    direction: Literal["bullish", "bearish"] = "bullish" if side == "long" else "bearish"
    ident = (session_date, prefix, swept.interact_ts.isoformat())
    unique_sweeps[f"{prefix}_swept"].add(ident)
    if preferred_event(smc.events, direction, swept.interact_ts, False) is not None:
        totals.arm_window[f"{prefix}_any_event"] += 1
        unique_sweeps[f"{prefix}_any_event"].add(ident)
    choch_only = [ev for ev in smc.events if ev.kind == "choch"]
    if preferred_event(choch_only, direction, swept.interact_ts, False) is not None:
        totals.arm_window[f"{prefix}_choch"] += 1
        unique_sweeps[f"{prefix}_choch"].add(ident)
    if preferred_event(smc.events, direction, swept.interact_ts, True) is not None:
        totals.arm_window[f"{prefix}_external"] += 1
        unique_sweeps[f"{prefix}_external"].add(ident)
    for m in _MINS:
        if _live_fvg(fvgs, direction, swept.interact_ts, m) is not None:
            totals.arm_window[f"{prefix}_fvg{int(m)}"] += 1
            unique_sweeps[f"{prefix}_fvg{int(m)}"].add(ident)


def write_census(totals: CensusTotals, out_dir: Path, meta: dict[str, object]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {"meta": meta, "totals": asdict(totals)}
    (out_dir / "census.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Phase 4 round-2 indicator census",
        "",
        "Detector-only. Does not call `SetupA.decide`. Same IS window as round-1 blotter.",
        "Join counts apply Setup A bias (`discount` long / `premium` short).",
        "Interpretation: [FINDINGS.md](FINDINGS.md).",
        "",
        f"- git: `{meta.get('git_hash')}`",
        f"- range: `{meta.get('start')}` → `{meta.get('end')}`",
        f"- day 5m: {totals.n_day_5m} across {totals.n_day_sessions} sessions",
        f"- arm window (09:15–13:40, skip settlement): {totals.n_arm_window_5m}",
        "",
        "## Onsets (state first becomes swept/taken)",
        "",
        "| level | sweep_onset | taken_onset | live_swept_bars | live_taken_bars |",
        "|---|---:|---:|---:|---:|",
    ]
    for name in _LEVELS:
        lines.append(
            f"| {name} | {totals.sweep_onset[name]} | {totals.taken_onset[name]} | "
            f"{totals.live_swept_bars[name]} | {totals.live_taken_bars[name]} |"
        )
    lines.extend(["", "## Structure events (unique prints)", "", "```json", json.dumps(totals.events_new, indent=2), "```", ""])
    lines.extend(["## FVG formed (unique)", "", "```json", json.dumps(totals.fvg_formed, indent=2), "```", ""])
    lines.extend(
        [
            "## Setup A join in arm window (bar counts / unique sweeps)",
            "",
            "Bar counts are 5m closes where the live swept level still qualifies. Unique is `(date, side, interact_ts)`.",
            "",
            "```json",
            json.dumps({"bars": totals.arm_window, "unique_sweeps": totals.unique_sweeps}, indent=2),
            "```",
            "",
        ]
    )
    (out_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Setup A detector census (no strategy)")
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    parser.add_argument("--out", required=True, type=Path)
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
    bars_1m = BarReader(kbars).load(start, end)
    if not bars_1m:
        print("skip: no kbars in range", file=sys.stderr)
        return 1
    bars_5m = BarStore(sorted(bars_1m, key=lambda bar: bar.timestamp)).resample_5m()
    totals = census_5m_tape(bars_5m)
    meta: dict[str, object] = {
        "git_hash": resolve_git_hash(None),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "n_1m": len(bars_1m),
        "n_5m": len(bars_5m),
    }
    write_census(totals, args.out, meta)
    print(json.dumps({"out": str(args.out), **asdict(totals)["arm_window"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
