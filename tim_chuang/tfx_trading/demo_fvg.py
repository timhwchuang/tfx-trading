from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from tfx_trading.bar_reader import BarReader
from tfx_trading.bar_store import BarStore
from tfx_trading.indicators.fvg import Fvg, compute
from tfx_trading.kbar import KBar

_KBARS_PATH = Path(__file__).resolve().parent / "kbars_data"
_AS_OF = datetime(2026, 8, 17, 13, 45)
_DAY = date(2026, 8, 17)


def _print_as_of(bar: KBar | None) -> None:
    if bar is None:
        print("========= as_of - =========")
        print("-")
        print()
        return
    print(f"========= as_of {bar.timestamp:%Y-%m-%d %H:%M} =========")
    print(f"{'timestamp':<19}  {'open':<8}  {'high':<8}  {'low':<8}  {'close':<8}  {'volume'}")
    print(
        f"{bar.timestamp:%Y-%m-%d %H:%M:%S}  "
        f"{bar.open:<8.1f}  "
        f"{bar.high:<8.1f}  "
        f"{bar.low:<8.1f}  "
        f"{bar.close:<8.1f}  "
        f"{bar.volume}"
    )
    print()


def _print_fvgs(fvgs: list[Fvg]) -> None:
    print("========= 5m FVG  2026-08-17 day =========")
    print(
        f"{'formed':<16}  {'dir':<8}  {'bottom':<8}  {'top':<8}  "
        f"{'ce':<8}  {'size':<8}  {'state':<10}  {'mitigated':<16}  {'filled'}"
    )
    for fvg in fvgs:
        mitigated = f"{fvg.mitigated_ts:%Y-%m-%d %H:%M}" if fvg.mitigated_ts else "-"
        filled = f"{fvg.filled_ts:%Y-%m-%d %H:%M}" if fvg.filled_ts else "-"
        print(
            f"{fvg.formed_at:%Y-%m-%d %H:%M}  "
            f"{fvg.direction:<8}  "
            f"{fvg.bottom:<8.1f}  "
            f"{fvg.top:<8.1f}  "
            f"{fvg.ce:<8.1f}  "
            f"{fvg.size:<8.1f}  "
            f"{fvg.state:<10}  "
            f"{mitigated:<16}  "
            f"{filled}"
        )
    print(f"({len(fvgs)} fvgs)\n")


def main() -> None:
    kbars = BarReader(_KBARS_PATH).load(date(2026, 8, 14), _DAY)
    bars_5m = [b for b in BarStore(kbars).resample_5m() if b.timestamp <= _AS_OF]
    last = bars_5m[-1] if bars_5m else None
    fvgs = [
        fvg
        for fvg in compute(bars_5m)
        if fvg.session == "day" and fvg.formed_at.date() == _DAY
    ]
    _print_as_of(last)
    _print_fvgs(fvgs)


if __name__ == "__main__":
    main()
