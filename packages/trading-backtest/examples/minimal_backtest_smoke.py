"""Minimal example: run a deterministic backtest smoke with StubStrategy.

Requires only trading-engine (and this package) to be installed.
No real strategy plugin or tick cache needed (uses patches for demo).
"""

from __future__ import annotations

import _bootstrap  # noqa: F401 — adds src/ to sys.path when not installed

import datetime
from unittest.mock import patch

from trading_engine.testing.defaults import default_runtime_config
from trading_engine.testing.helpers import StubStrategy
from trading_backtest import BacktestEngine, __version__
from trading_backtest.loader import ReplayTick


def main() -> None:
    cfg = default_runtime_config()
    strategy = StubStrategy()
    dates = [datetime.date(2026, 6, 12)]

    engine = BacktestEngine(
        code="TXFR1",
        dates=dates,
        strategy=strategy,
        runtime_config=cfg,
    )

    demo_ticks = [
        ReplayTick(datetime.datetime(2026, 6, 12, 9, 0, 0), 18000.0, 10, 0),
        ReplayTick(datetime.datetime(2026, 6, 12, 9, 0, 1), 18001.0, 5, 0),
    ]

    with patch("trading_backtest.loader.iter_replay_ticks", return_value=iter(demo_ticks)):
        engine.run()

    last_tick = demo_ticks[-1]
    print(f"trading-backtest {__version__}")
    print(f"ticks replayed: {len(demo_ticks)}")
    print(f"last tick: {last_tick.datetime.isoformat()} close={last_tick.close}")
    print(f"host: {type(engine.host).__name__}")
    print("done — deterministic replay with same kernel as live")


if __name__ == "__main__":
    main()