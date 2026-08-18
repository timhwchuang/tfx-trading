from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from tfx_trading.bar_reader import BarReader
from tfx_trading.bar_store import BarStore
from tfx_trading.indicators.sma import SMASnapshot, compute

_KBARS_PATH = Path(__file__).resolve().parent / "kbars_data"
_DAY = date(2026, 8, 17)


def _fmt(value: float | None) -> str:
    return f"{value:<8.1f}" if value is not None else f"{'-':<8}"


def _print_snaps(title: str, snaps: list[SMASnapshot], start: datetime, end: datetime) -> None:
    print(title)
    print(f"{'timestamp':<19}  {'close':<8}  {'ma5':<8}  {'ma20':<8}  {'ma60':<8}")
    n = 0
    for snap in snaps:
        if start <= snap.timestamp <= end:
            print(
                f"{snap.timestamp:%Y-%m-%d %H:%M:%S}  "
                f"{snap.close:<8.1f}  "
                f"{_fmt(snap.ma5)}  "
                f"{_fmt(snap.ma20)}  "
                f"{_fmt(snap.ma60)}"
            )
            n += 1
    print(f"({n} bars)\n")


def main() -> None:
    # 8/14、8/15 當 rolling 熱身，讓 8/17 開盤就有 ma60。
    kbars = BarReader(_KBARS_PATH).load(date(2026, 8, 14), _DAY)
    store = BarStore(kbars)

    day_open = datetime(2026, 8, 17, 8, 46)
    _print_snaps(
        "========= 1m SMA  2026-08-17 08:46–09:15 =========",
        compute(store.resample_1m()),
        day_open,
        datetime(2026, 8, 17, 9, 15),
    )
    _print_snaps(
        "========= 5m SMA  2026-08-17 08:50–13:45 =========",
        compute(store.resample_5m()),
        datetime(2026, 8, 17, 8, 50),
        datetime(2026, 8, 17, 13, 45),
    )


if __name__ == "__main__":
    main()
