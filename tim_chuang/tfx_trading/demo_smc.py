from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from tfx_trading.bar_reader import BarReader
from tfx_trading.bar_store import BarStore
from tfx_trading.indicators.smc import SessionLevel, SmcLevels, Swing, compute

_KBARS_PATH = Path(__file__).resolve().parent / "kbars_data"
_AS_OF = datetime(2026, 8, 17, 13, 45)


def _fmt_level(level: SessionLevel | None) -> str:
    if level is None:
        return "-"
    flag = "dev" if level.developing else "done"
    return f"{level.price:<8.1f}  {level.source_ts:%Y-%m-%d %H:%M}  {flag}"


def _print_swings(swings: list[Swing]) -> None:
    print("========= 5m swings  2026-08-17 day =========")
    print(f"{'timestamp':<19}  {'side':<4}  {'price':<8}  {'confirmed':<19}  {'sig'}")
    n_sig = 0
    for swing in swings:
        mark = "Y" if swing.significant else "-"
        if swing.significant:
            n_sig += 1
        print(
            f"{swing.timestamp:%Y-%m-%d %H:%M:%S}  "
            f"{swing.side:<4}  "
            f"{swing.price:<8.1f}  "
            f"{swing.confirmed_at:%Y-%m-%d %H:%M:%S}  "
            f"{mark}"
        )
    print(f"({len(swings)} swings, {n_sig} significant)\n")


def _print_levels(levels: SmcLevels) -> None:
    print("========= session liquidity  as_of 2026-08-17 13:45 =========")
    print(f"{'kind':<16}  {'price':<8}  {'source':<16}  {'state'}")
    rows = [
        ("pdh", levels.pdh),
        ("pdl", levels.pdl),
        ("prev_night_high", levels.prev_night_high),
        ("prev_night_low", levels.prev_night_low),
        ("session_high", levels.session_high),
        ("session_low", levels.session_low),
    ]
    for kind, level in rows:
        print(f"{kind:<16}  {_fmt_level(level)}")
    print()


def main() -> None:
    kbars = BarReader(_KBARS_PATH).load(date(2026, 8, 14), date(2026, 8, 17))
    bars_5m = [b for b in BarStore(kbars).resample_5m() if b.timestamp <= _AS_OF]
    levels = compute(bars_5m)
    day_swings = [
        s
        for s in levels.swings
        if s.session == "day" and datetime(2026, 8, 17, 8, 50) <= s.timestamp <= _AS_OF
    ]
    _print_swings(day_swings)
    _print_levels(levels)


if __name__ == "__main__":
    main()
