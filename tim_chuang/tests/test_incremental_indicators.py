from __future__ import annotations

from datetime import datetime, timedelta

from tfx_trading.indicators.fvg import compute as fvg_compute
from tfx_trading.indicators.fvg import compute_from_scratch as fvg_compute_from_scratch
from tfx_trading.indicators.smc import compute as smc_compute
from tfx_trading.indicators.smc import compute_from_scratch as smc_compute_from_scratch
from tfx_trading.kbar import KBar


def _bar(ts: datetime, open_: float, high: float, low: float, close: float) -> KBar:
    return KBar(timestamp=ts, open=open_, high=high, low=low, close=close, volume=1, amount=close)


def _build_tape() -> list[KBar]:
    base = datetime(2026, 8, 17, 8, 50)
    bars: list[KBar] = []
    for i in range(24):
        ts = base + timedelta(minutes=5 * i)
        # deterministic zig-zag with varying ranges to trigger both swings and FVG states
        pivot = 20000.0 + ((i % 6) - 3) * 20.0 + (i // 6) * 5.0
        high = pivot + (40.0 if i % 4 == 0 else 18.0)
        low = pivot - (35.0 if i % 5 == 0 else 16.0)
        close = pivot + (10.0 if i % 2 == 0 else -8.0)
        open_ = pivot - (6.0 if i % 3 == 0 else -4.0)
        bars.append(_bar(ts, open_, high, low, close))
    # add a night segment so session transitions are included.
    nbase = datetime(2026, 8, 17, 15, 5)
    for i in range(18):
        ts = nbase + timedelta(minutes=5 * i)
        pivot = 20100.0 + ((i % 7) - 3) * 15.0
        high = pivot + (30.0 if i % 3 == 0 else 14.0)
        low = pivot - (28.0 if i % 4 == 0 else 12.0)
        close = pivot + (6.0 if i % 2 == 0 else -5.0)
        open_ = pivot - (3.0 if i % 2 == 0 else -2.0)
        bars.append(_bar(ts, open_, high, low, close))
    return bars


def test_incremental_fvg_matches_from_scratch_each_prefix() -> None:
    bars = _build_tape()
    for i in range(1, len(bars) + 1):
        prefix = bars[:i]
        assert fvg_compute(prefix, min_points=0.0) == fvg_compute_from_scratch(
            prefix, min_points=0.0
        )


def test_incremental_smc_matches_from_scratch_each_prefix() -> None:
    bars = _build_tape()
    for i in range(1, len(bars) + 1):
        prefix = bars[:i]
        assert smc_compute(prefix, min_points=20.0) == smc_compute_from_scratch(
            prefix, min_points=20.0
        )
