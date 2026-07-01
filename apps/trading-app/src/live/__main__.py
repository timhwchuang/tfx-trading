"""Thin live entry: assemble Shioaji API + TradingEngine."""

from __future__ import annotations

import argparse
import datetime
import os
import sys
from pathlib import Path

_LIVE_EPILOG = """\
Examples:
  python -m live
  CONFIG_PATH=workspaces/gudt-route-a-baseline/config/config.yaml python -m live

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
        description="Start live/simulation session (Shioaji + TradingEngine).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_LIVE_EPILOG,
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        metavar="PATH",
        help="Workspace config.yaml (default: CONFIG_PATH or apps/trading-app/config/config.yaml)",
    )
    args = parser.parse_args(argv)

    import shioaji as sj

    from config import DEFAULT_CONFIG_PATH, load_config
    from core.runtime_config import TradingAppRuntimeConfig, _to_engine_settings
    from integrations.engine_wiring import build_strategy_session, trading_app_engine_ports
    from integrations.gudt_live_bootstrap import attach_gudt_live_coordinator, start_live_session
    from observability import DailyObservability
    from storage.tick_loader import DEFAULT_CACHE_DIR
    from trading_engine.engine import TradingEngine

    config_path = Path(
        args.config or os.environ.get("CONFIG_PATH", DEFAULT_CONFIG_PATH)
    ).expanduser()
    os.environ["CONFIG_PATH"] = str(config_path.resolve())
    app_settings = load_config(config_path)
    import config as config_module

    config_module.LOG_LEVEL = app_settings.log_level
    config_module.LOG_FILE = app_settings.log_file

    from integrations import engine_wiring
    from trading_engine.logging_setup import setup_async_logging

    engine_wiring._logging_configured = False
    setup_async_logging(
        level=app_settings.log_level,
        log_file=app_settings.log_file or None,
    )
    engine_wiring._logging_configured = True

    cfg = TradingAppRuntimeConfig(_to_engine_settings(app_settings))
    code = app_settings.product_code
    today = datetime.date.today()
    cache_dir = DEFAULT_CACHE_DIR
    obs = DailyObservability()

    api = sj.Shioaji(simulation=app_settings.simulation)
    ports = trading_app_engine_ports(
        api=api,
        use_mock_adapter=False,
        runtime_config=cfg,
        with_alerts=True,
        with_archive=True,
        obs=obs,
    )
    strategy = build_strategy_session(
        cfg,
        obs,
        code=code,
        dates=[today],
        cache_dir=cache_dir,
        mode="live",
    )
    coordinator = attach_gudt_live_coordinator(
        strategy,
        cfg,
        code=code,
        cache_dir=cache_dir,
        trade_day=today,
    )
    engine = TradingEngine(
        api=api,
        strategy=strategy,
        **{k: v for k, v in ports.items() if k != "obs"},
    )
    start_live_session(engine, coordinator=coordinator)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
