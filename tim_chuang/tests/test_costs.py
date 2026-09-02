from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from tfx_trading.trading.costs import (
    POINT_VALUE_NT,
    CostConfig,
    apply_slippage,
    close_trade,
    load_trading_config,
    margin_required_nt,
    round_trip_pnl_nt,
)


@pytest.fixture
def cfg() -> CostConfig:
    return CostConfig(
        commission_nt=20,
        slippage_ticks=1,
        flatten_slippage_ticks=2,
        initial_margin_nt=10_000,
        maintenance_margin_nt=8_000,
    )


def test_round_trip_long_loss(cfg: CostConfig) -> None:
    pnl = round_trip_pnl_nt("long", 20000.0, 19980.0, 1, cfg)
    assert pnl == pytest.approx(-247.996)


def test_round_trip_short_win(cfg: CostConfig) -> None:
    pnl = round_trip_pnl_nt("short", 20000.0, 19980.0, 1, cfg)
    assert pnl == pytest.approx(200 - 7.996 - 40)


def test_gross_uses_point_value(cfg: CostConfig) -> None:
    pnl = round_trip_pnl_nt("long", 20000.0, 19980.0, 1, cfg)
    tax = (20000.0 + 19980.0) * POINT_VALUE_NT * 0.00002
    assert pnl == pytest.approx(-20 * POINT_VALUE_NT - tax - 40)


def test_apply_slippage_limit_is_identity(cfg: CostConfig) -> None:
    assert apply_slippage("limit", "long", 20000.0, cfg) == 20000.0
    assert apply_slippage("limit", "short", 20000.0, cfg) == 20000.0


def test_apply_slippage_stop_one_tick(cfg: CostConfig) -> None:
    assert apply_slippage("stop", "long", 20000.0, cfg) == 20001.0
    assert apply_slippage("stop", "short", 20000.0, cfg) == 19999.0


def test_apply_slippage_flatten_two_ticks(cfg: CostConfig) -> None:
    assert apply_slippage("flatten", "long", 20000.0, cfg) == 20002.0
    assert apply_slippage("flatten", "short", 20000.0, cfg) == 19998.0


def test_close_trade_without_risk_has_no_r(cfg: CostConfig) -> None:
    ts = datetime(2026, 6, 15, 9, 5)
    record = close_trade(
        "long",
        ts,
        20000.0,
        ts,
        19980.0,
        1,
        "stop",
        cfg,
    )
    assert record.r_multiple is None
    assert record.pnl_nt == pytest.approx(-247.996)


def test_load_trading_config_defaults_without_trading_section(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("simulation: true\n", encoding="utf-8")
    loaded = load_trading_config(path)
    assert loaded.commission_nt == 20
    assert loaded.slippage_ticks == 1
    assert loaded.flatten_slippage_ticks == 2
    assert loaded.initial_margin_nt == 35050
    assert loaded.maintenance_margin_nt == 26900


def test_load_trading_config_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="找不到設定檔"):
        load_trading_config(tmp_path / "missing.yaml")


def test_margin_required_uses_fixture(cfg: CostConfig) -> None:
    assert margin_required_nt(2, cfg, kind="initial") == 20_000
    assert margin_required_nt(2, cfg, kind="maintenance") == 16_000
