"""載入 config.yaml；密鑰與敏感路徑僅來自環境變數。"""

from __future__ import annotations

import datetime
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "config" / "config.yaml"
# Fallback when config.yaml omits product_code (UAT/Pilot default: 微台近月).
DEFAULT_PRODUCT_CODE = "TMFR1"


def _parse_time(value: str) -> datetime.time:
    hour, minute = value.strip().split(":")
    return datetime.time(int(hour), int(minute))


def _section(data: Mapping[str, Any], name: str) -> dict[str, Any]:
    block = data.get(name)
    return dict(block) if isinstance(block, dict) else {}


def resolve_capital_state_path(
    raw: str | Path | None,
    *,
    base_dir: Path | None = None,
) -> str:
    """Resolve capital JSON path to an absolute string (or empty if disabled).

    Relative paths are anchored at ``base_dir`` (default: trading-app root),
    not process CWD — so ``cd …/src; python -m live`` still writes
    ``apps/trading-app/var/capital_risk.json``.
    """
    if raw is None:
        return ""
    text = str(raw).strip()
    if not text:
        return ""
    path = Path(text).expanduser()
    if not path.is_absolute():
        root = base_dir if base_dir is not None else _PROJECT_ROOT
        path = (root / path).resolve()
    else:
        path = path.resolve()
    return str(path)


@dataclass(frozen=True)
class Settings:
    simulation: bool
    product_code: str
    strategy_name: str

    cooldown_sec: int
    max_daily_loss_points: int
    max_consecutive_loss: int
    max_mdd_points: float
    capital_state_path: str
    pending_timeout_sec: int
    ioc_slippage_points: int
    no_tick_timeout_sec: int
    no_tick_resubscribe_escalate_after: int
    clock_skew_warn_sec: float

    session_start: datetime.time
    session_end: datetime.time
    session_flatten_time: datetime.time
    session_force_flatten_time: datetime.time
    flatten_slippage_points: int
    night_enabled: bool
    night_session_start: datetime.time
    night_session_end: datetime.time
    night_session_flatten_time: datetime.time
    night_session_force_flatten_time: datetime.time
    simple_entry_delay_sec: int
    simple_flip_interval_sec: int

    log_level: str
    log_file: str

    friction_enabled: bool
    friction_mode: str
    round_trip_friction_points: float
    commission_per_side_points: float
    tax_per_exit_points: float
    commission_per_side_ntd: float
    friction_tax_rate: float
    point_value_ntd: float
    sharpe_period: str
    sweep_score_metric: str
    sweep_dd_penalty: float
    sweep_sl_penalty: float
    sweep_max_grid_combos: int
    sweep_max_grid_keys: int
    initial_capital_points: float
    max_acceptable_mdd_points: float

    exit_order_max_retries: int
    exit_order_retry_delay_sec: float
    session_watchdog_sec: float
    session_relogin_max_attempts: int
    session_relogin_backoff_base_sec: float
    reconnect_warmup_sec: int
    max_disconnects_per_day: int
    alert_on_disconnect_with_position: bool
    position_reconcile_sec: int
    max_position_qty: int
    settle_timeout_sec: int
    reconcile_fast_sec: int
    reconcile_confirm_reads: int
    emergency_market_orders: bool
    entry_miss_confirm_sec: int
    exit_miss_confirm_sec: int
    post_exit_reconcile_sec: int
    cleared_order_registry_sec: int
    max_consecutive_missed_entries: int

    config_path: Path


def load_config(path: str | Path | None = None) -> Settings:
    config_path = Path(
        path or os.environ.get("CONFIG_PATH", DEFAULT_CONFIG_PATH)
    ).expanduser()
    if not config_path.is_file():
        raise FileNotFoundError(f"找不到設定檔: {config_path}")

    with config_path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    strategy = _section(raw, "strategy")
    session = _section(raw, "session")
    logging_cfg = _section(raw, "logging")
    friction = _section(raw, "friction")
    performance = _section(raw, "performance")
    operations = _section(raw, "operations")

    log_level = os.environ.get("LOG_LEVEL", logging_cfg.get("level", "INFO"))
    log_file = os.environ.get("LOG_FILE", logging_cfg.get("file", ""))

    return Settings(
        simulation=bool(raw.get("simulation", True)),
        product_code=str(raw.get("product_code", DEFAULT_PRODUCT_CODE)),
        strategy_name=str(strategy.get("name", "simple")),
        cooldown_sec=int(strategy.get("cooldown_sec", 10)),
        max_daily_loss_points=int(strategy.get("max_daily_loss_points", 120)),
        max_consecutive_loss=int(strategy.get("max_consecutive_loss", 4)),
        max_mdd_points=float(strategy.get("max_mdd_points", 0)),
        capital_state_path=resolve_capital_state_path(
            strategy.get("capital_state_path")
            or _section(raw, "risk").get("capital_state_path")
            or ""
        ),
        pending_timeout_sec=int(strategy.get("pending_timeout_sec", 1)),
        ioc_slippage_points=int(strategy.get("ioc_slippage_points", 3)),
        no_tick_timeout_sec=int(strategy.get("no_tick_timeout_sec", 45)),
        no_tick_resubscribe_escalate_after=int(
            operations.get("no_tick_resubscribe_escalate_after", 3)
        ),
        clock_skew_warn_sec=float(strategy.get("clock_skew_warn_sec", 1.0)),
        session_start=_parse_time(session.get("start", "08:45")),
        session_end=_parse_time(session.get("end", "13:45")),
        session_flatten_time=_parse_time(session.get("flatten_time", "13:40")),
        session_force_flatten_time=_parse_time(
            session.get("force_flatten_time", "13:44")
        ),
        flatten_slippage_points=int(session.get("flatten_slippage_points", 8)),
        night_enabled=bool(session.get("night_enabled", False)),
        night_session_start=_parse_time(session.get("night_start", "15:00")),
        night_session_end=_parse_time(session.get("night_end", "05:00")),
        night_session_flatten_time=_parse_time(
            session.get("night_flatten_time", "04:50")
        ),
        night_session_force_flatten_time=_parse_time(
            session.get("night_force_flatten_time", "04:55")
        ),
        simple_entry_delay_sec=int(strategy.get("entry_delay_sec", 60)),
        simple_flip_interval_sec=int(strategy.get("flip_interval_sec", 300)),
        log_level=str(log_level).upper(),
        log_file=str(log_file or ""),
        friction_enabled=bool(friction.get("enabled", False)),
        friction_mode=str(friction.get("mode", "flat_round_trip")),
        round_trip_friction_points=float(
            friction.get("round_trip_friction_points", 2.0)
        ),
        commission_per_side_points=float(
            friction.get("commission_per_side_points", 0.5)
        ),
        tax_per_exit_points=float(friction.get("tax_per_exit_points", 1.0)),
        commission_per_side_ntd=float(friction.get("commission_per_side_ntd", 0.0)),
        friction_tax_rate=float(friction.get("tax_rate", 0.0)),
        point_value_ntd=float(friction.get("point_value_ntd", 10.0)),
        sharpe_period=str(performance.get("sharpe_period", "per_trade")),
        sweep_score_metric=str(performance.get("sweep_score_metric", "expectancy_net")),
        sweep_dd_penalty=float(performance.get("sweep_dd_penalty", 0.0)),
        sweep_sl_penalty=float(performance.get("sweep_sl_penalty", 50.0)),
        sweep_max_grid_combos=int(performance.get("sweep_max_grid_combos", 36)),
        sweep_max_grid_keys=int(performance.get("sweep_max_grid_keys", 4)),
        initial_capital_points=float(performance.get("initial_capital_points", 0.0)),
        max_acceptable_mdd_points=float(
            performance.get("max_acceptable_mdd_points", 120.0)
        ),
        exit_order_max_retries=int(operations.get("exit_order_max_retries", 3)),
        exit_order_retry_delay_sec=float(
            operations.get("exit_order_retry_delay_sec", 1.0)
        ),
        session_watchdog_sec=float(operations.get("session_watchdog_sec", 30.0)),
        session_relogin_max_attempts=int(
            operations.get("session_relogin_max_attempts", 5)
        ),
        session_relogin_backoff_base_sec=float(
            operations.get("session_relogin_backoff_base_sec", 5.0)
        ),
        reconnect_warmup_sec=int(operations.get("reconnect_warmup_sec", 300)),
        max_disconnects_per_day=int(operations.get("max_disconnects_per_day", 3)),
        alert_on_disconnect_with_position=bool(
            operations.get("alert_on_disconnect_with_position", True)
        ),
        position_reconcile_sec=int(operations.get("position_reconcile_sec", 60)),
        max_position_qty=int(operations.get("max_position_qty", 1)),
        settle_timeout_sec=int(operations.get("settle_timeout_sec", 45)),
        reconcile_fast_sec=int(operations.get("reconcile_fast_sec", 1)),
        reconcile_confirm_reads=int(operations.get("reconcile_confirm_reads", 3)),
        emergency_market_orders=bool(operations.get("emergency_market_orders", True)),
        entry_miss_confirm_sec=int(operations.get("entry_miss_confirm_sec", 5)),
        exit_miss_confirm_sec=int(operations.get("exit_miss_confirm_sec", 5)),
        post_exit_reconcile_sec=int(operations.get("post_exit_reconcile_sec", 15)),
        cleared_order_registry_sec=int(
            operations.get("cleared_order_registry_sec", 120)
        ),
        max_consecutive_missed_entries=int(
            operations.get("max_consecutive_missed_entries", 3)
        ),
        config_path=config_path.resolve(),
    )


# 模組載入時讀取一次；runtime 以同名常數使用
settings = load_config()

SIMULATION = settings.simulation
PRODUCT_CODE = settings.product_code
COOLDOWN_SEC = settings.cooldown_sec
MAX_DAILY_LOSS_POINTS = settings.max_daily_loss_points
MAX_CONSECUTIVE_LOSS = settings.max_consecutive_loss
MAX_MDD_POINTS = settings.max_mdd_points
PENDING_TIMEOUT_SEC = settings.pending_timeout_sec
IOC_SLIPPAGE_POINTS = settings.ioc_slippage_points
NO_TICK_TIMEOUT_SEC = settings.no_tick_timeout_sec
CLOCK_SKEW_WARN_SEC = settings.clock_skew_warn_sec
SESSION_START = settings.session_start
SESSION_END = settings.session_end
SESSION_FLATTEN_TIME = settings.session_flatten_time
SESSION_FORCE_FLATTEN_TIME = settings.session_force_flatten_time
FLATTEN_SLIPPAGE_POINTS = settings.flatten_slippage_points
LOG_LEVEL = settings.log_level
LOG_FILE = settings.log_file

FRICTION_ENABLED = settings.friction_enabled
FRICTION_MODE = settings.friction_mode
ROUND_TRIP_FRICTION_POINTS = settings.round_trip_friction_points
COMMISSION_PER_SIDE_POINTS = settings.commission_per_side_points
TAX_PER_EXIT_POINTS = settings.tax_per_exit_points
COMMISSION_PER_SIDE_NTD = settings.commission_per_side_ntd
FRICTION_TAX_RATE = settings.friction_tax_rate
POINT_VALUE_NTD = settings.point_value_ntd
SHARPE_PERIOD = settings.sharpe_period
SWEEP_SCORE_METRIC = settings.sweep_score_metric
SWEEP_DD_PENALTY = settings.sweep_dd_penalty
SWEEP_SL_PENALTY = settings.sweep_sl_penalty
SWEEP_MAX_GRID_COMBOS = settings.sweep_max_grid_combos
SWEEP_MAX_GRID_KEYS = settings.sweep_max_grid_keys
INITIAL_CAPITAL_POINTS = settings.initial_capital_points
MAX_ACCEPTABLE_MDD_POINTS = settings.max_acceptable_mdd_points
EXIT_ORDER_MAX_RETRIES = settings.exit_order_max_retries
EXIT_ORDER_RETRY_DELAY_SEC = settings.exit_order_retry_delay_sec
SESSION_WATCHDOG_SEC = settings.session_watchdog_sec
SESSION_RELOGIN_MAX_ATTEMPTS = settings.session_relogin_max_attempts
SESSION_RELOGIN_BACKOFF_BASE_SEC = settings.session_relogin_backoff_base_sec

# 密鑰僅來自環境變數，不寫入 YAML
API_KEY = os.environ.get("SJ_API_KEY", "YOUR_API_KEY")
SECRET_KEY = os.environ.get("SJ_SEC_KEY", "YOUR_SECRET_KEY")
CA_PATH = os.environ.get("SJ_CA_PATH", "")
CA_PASSWD = os.environ.get("SJ_CA_PASSWD", "")

_DUMP_ORDER_EVENTS = os.environ.get("DUMP_ORDER_EVENTS", "").strip().lower()
DUMP_ORDER_EVENTS = _DUMP_ORDER_EVENTS in ("1", "true", "yes")

_TICK_ARCHIVE = os.environ.get("TICK_ARCHIVE", "").strip().lower()
TICK_ARCHIVE = _TICK_ARCHIVE in ("1", "true", "yes")

_KBARS_ARCHIVE = os.environ.get("KBARS_ARCHIVE", "").strip().lower()
KBARS_ARCHIVE = _KBARS_ARCHIVE in ("1", "true", "yes")

_LIVE_BARS = os.environ.get("LIVE_BARS", "").strip().lower()
LIVE_BARS = _LIVE_BARS in ("1", "true", "yes")

_LIVE_KBAR_PERSIST = os.environ.get("LIVE_KBAR_PERSIST", "").strip().lower()
LIVE_KBAR_PERSIST = _LIVE_KBAR_PERSIST in ("1", "true", "yes")

__all__ = [
    "DEFAULT_CONFIG_PATH",
    "DEFAULT_PRODUCT_CODE",
    "KBARS_ARCHIVE",
    "LIVE_BARS",
    "LIVE_KBAR_PERSIST",
    "Settings",
    "TICK_ARCHIVE",
    "load_config",
    "settings",
    "PRODUCT_CODE",
    "SIMULATION",
]
