"""Thin live entry: assemble Shioaji API + TradingEngine."""

from __future__ import annotations

import argparse
import sys

_LIVE_EPILOG = """\
Examples:
  python -m live

Environment (see apps/trading-app/README.md):
  SJ_API_KEY, SJ_SEC_KEY          Shioaji credentials
  CONFIG_PATH                     config.yaml path
  LOG_FILE, LOG_LEVEL             logging
  TICK_ARCHIVE=1, KBARS_ARCHIVE=1 archive under monorepo tick_cache/
  SJ_CA_PATH, SJ_CA_PASSWD        required when simulation: false

Config: config/config.yaml — simulation: true for UAT (default).
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Start VWAP momentum live/simulation session (Shioaji + TradingEngine).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_LIVE_EPILOG,
    )
    parser.parse_args(argv)

    import shioaji as sj

    from config import SIMULATION
    from integrations.engine_wiring import default_strategy, trading_app_engine_ports
    from trading_engine.engine import TradingEngine

    api = sj.Shioaji(simulation=SIMULATION)
    ports = trading_app_engine_ports(
        api=api,
        use_mock_adapter=False,
        with_alerts=True,
        with_archive=True,
    )
    TradingEngine(
        api=api,
        strategy=default_strategy(ports["runtime_config"], ports["obs"]),
        **{k: v for k, v in ports.items() if k != "obs"},
    ).start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))