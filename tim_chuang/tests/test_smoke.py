from __future__ import annotations

from datetime import datetime

from tfx_trading.backtest.smoke import (
    SCORECARD_DATES,
    day_hl_by_date,
    is_arm_bracket,
    r_points_from_trade,
    render_smoke_md,
    smoke_params,
    trade_day,
)
from tfx_trading.kbar import KBar
from tfx_trading.strategy.setup_a import SetupAParams
from tfx_trading.trading.models import Intent, TradeRecord


def _trade(
    *,
    pnl_nt: float,
    r_multiple: float | None,
    reason: str = "stop",
    qty: int = 1,
    entry_ts: datetime | None = None,
) -> TradeRecord:
    ts = entry_ts if entry_ts is not None else datetime(2025, 5, 14, 11, 26)
    return TradeRecord(
        side="short",
        entry_ts=ts,
        entry_price=21662.0,
        exit_ts=ts,
        exit_price=21666.0,
        qty=qty,
        pnl_nt=pnl_nt,
        r_multiple=r_multiple,
        reason=reason,  # type: ignore[arg-type]
    )


def test_r_points_inverts_broker_risk_nt() -> None:
    # risk_nt = 50 pts * 10 NT * 1 lot = 500; pnl/r_multiple = risk_nt
    trade = _trade(pnl_nt=-500.0, r_multiple=-1.0)
    assert r_points_from_trade(trade) == 50.0


def test_r_points_none_without_r_multiple() -> None:
    assert r_points_from_trade(_trade(pnl_nt=-88.0, r_multiple=None)) is None


def test_day_hl_by_date_day_session_only() -> None:
    bars = [
        KBar(datetime(2025, 5, 14, 9, 0), 100, 110, 90, 100, 1, 100),
        KBar(datetime(2025, 5, 14, 10, 0), 100, 120, 95, 100, 1, 100),
        KBar(datetime(2025, 5, 14, 15, 5), 100, 200, 50, 100, 1, 100),
    ]
    hl = day_hl_by_date(bars)
    assert hl[datetime(2025, 5, 14).date()] == 30.0


def test_trade_day_uses_session_key() -> None:
    assert trade_day(datetime(2025, 5, 14, 11, 26)) == datetime(2025, 5, 14).date()


def test_is_arm_bracket() -> None:
    stamp = "202505141000"
    arm = [
        Intent(f"{stamp}-entry", "place_limit", "short", 20050.0, 1, None, None),
        Intent(f"{stamp}-stop", "place_stop", "long", 20055.0, 1, None, None),
        Intent(f"{stamp}-tp", "place_limit", "long", 20040.0, 1, None, None),
    ]
    assert is_arm_bracket(arm) is True
    assert is_arm_bracket([]) is False
    flatten = [Intent(f"{stamp}-flatten", "flatten", "long", None, 1, None, None)]
    assert is_arm_bracket(flatten) is False


def test_smoke_params_hi_freq_cell() -> None:
    params = smoke_params(SetupAParams())
    assert params.entry_price == "top"
    assert params.min_points == 15.0
    assert params.stop_buffer == 3.0
    assert params.take_profit == "2R"
    assert params.require_external is False
    assert params.min_r_points == 15.0


def test_render_smoke_md_not_go_nogo() -> None:
    payload: dict[str, object] = {
        "git_hash": "abc",
        "start": "2025-05-07T08:46:00",
        "end": "2025-09-16T13:45:00",
        "n_1m": 10,
        "fill_mode": "conservative",
        "cell": {
            "entry_price": "top",
            "min_points": 15.0,
            "stop_buffer": 3.0,
            "take_profit": "2R",
            "require_external": False,
            "min_r_points": 15.0,
        },
        "aggregates": {
            "n_trades": 0,
            "n_scorecard": 0,
            "flatten_share": None,
            "r_min": None,
            "r_p50": None,
            "r_below_floor_unique": 0,
            "r_below_floor_raw": 0,
            "r_below_floor": [],
        },
        "fills": [],
        "scorecard_dates": [d.isoformat() for d in SCORECARD_DATES],
    }
    text = render_smoke_md(payload)
    assert "not go/no-go" in text
    assert "no_trade" in text
    assert "Do not read n or flatten share as edge." in text
