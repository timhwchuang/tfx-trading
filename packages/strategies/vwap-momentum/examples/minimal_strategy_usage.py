"""Minimal example: construct and exercise the reference VWAP strategy.

Requires only trading-engine (and this package) to be installed.
No backtest, no live broker, no secrets.
"""

from __future__ import annotations

from trading_engine.core.strategy import StrategySideEffects
from trading_engine.core.types import MarketSnapshot, PositionSnapshot, RiskGate
from trading_engine.testing.defaults import default_runtime_config

from strategy_vwap_momentum import StrategyParams, VWAPMomentumStrategy


def main() -> None:
    cfg = default_runtime_config()
    params = StrategyParams.from_runtime_config(cfg)
    strategy = VWAPMomentumStrategy(params=params)

    print("strategy-vwap-momentum version:", strategy.__module__.split(".")[0])
    print("params entry_band_points example:", params.entry_band_points)

    # simulate a flat position + benign risk gate
    market = MarketSnapshot(
        ts=1_700_000_100,
        price=18010.0,
        dt=...,  # type: ignore[arg-type]
        vwap=18005.0,
        vol_1s=120,
        buy_vol_1s=85,
        sell_vol_1s=35,
        current_atr=8.5,
        trend_dir="Long",
        trend_strength=2.3,
    )
    position = PositionSnapshot(
        has_position=False,
        position_dir="Flat",
        qty=0,
        entry_price=0.0,
        entry_exchange_ts=0,
        trailing_peak=0.0,
        ticks_since_entry=0,
    )
    risk = RiskGate(
        is_pending=False,
        exit_pending=False,
        cooldown_active=False,
        in_trading_session=True,
        after_flatten_time=False,
        block_new_entry=False,
        force_flatten=False,
        api_connected=True,
        daily_pnl=0.0,
        consecutive_loss=0,
    )

    signal, effects = strategy.evaluate(
        market,
        position,
        risk,
        (80.0, 1.5, 120.0),  # example vol_threshold (base, mult, threshold)
        session_force_flatten_time=...,  # type: ignore[arg-type]
        max_daily_loss_points=150.0,
        on_daily_loss_block=None,
    )

    print("evaluate result (flat, should possibly arm momentum):", signal, type(effects))

    # reset between episodes
    strategy.reset()
    print("reset called successfully")

    print("\nStrategy construction and basic Protocol call succeeded.")
    print("For full decision coverage and calibration, run the package tests + your own tick replay.")


if __name__ == "__main__":
    main()
