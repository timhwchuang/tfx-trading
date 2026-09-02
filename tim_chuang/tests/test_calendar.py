from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from tfx_trading.calendar import (
    TradeCalendar,
    expected_day_1m,
    expected_day_5m,
    expected_night_1m,
    expected_night_5m,
)


def test_settlement_third_wednesday() -> None:
    cal = TradeCalendar()
    assert cal.is_settlement_day(date(2026, 4, 15))
    assert not cal.is_settlement_day(date(2026, 4, 8))


def test_settlement_postpones_past_cny() -> None:
    cal = TradeCalendar()
    assert not cal.is_settlement_day(date(2026, 2, 18))
    assert cal.is_settlement_day(date(2026, 2, 23))
    assert cal.settlement_day(2026, 2) == date(2026, 2, 23)


def test_should_have_file_weekend_and_qingming() -> None:
    cal = TradeCalendar()
    assert cal.should_have_file(date(2026, 4, 11))  # Saturday dawn
    assert not cal.should_have_file(date(2026, 4, 12))  # Sunday
    assert cal.should_have_file(date(2026, 4, 3))  # 清明週五假日, 週四有市
    assert cal.should_have_file(date(2026, 1, 1))  # needs 2025-12-31


def test_missing_year_json_raises(tmp_path: Path) -> None:
    cal = TradeCalendar(tmp_path)
    with pytest.raises(FileNotFoundError, match="找不到交易日曆"):
        cal.is_holiday(date(2024, 1, 2))


def test_should_have_file_new_year_without_previous_year_json(tmp_path: Path) -> None:
    (tmp_path / "2025.json").write_text(
        json.dumps([{"date": "20250101", "isHoliday": True}]),
        encoding="utf-8",
    )
    cal = TradeCalendar(tmp_path)
    assert cal.is_holiday(date(2025, 1, 1))
    assert not cal.should_have_file(date(2025, 1, 1))
    with pytest.raises(FileNotFoundError, match="找不到交易日曆"):
        cal.is_holiday(date(2024, 12, 31))


def test_expected_session_sizes() -> None:
    day = date(2026, 4, 10)
    assert len(expected_day_1m(day)) == 300
    assert len(expected_night_1m(day)) == 840
    assert len(expected_day_5m(day)) == 60
    assert len(expected_night_5m(day)) == 168
    assert datetime(2026, 4, 10, 8, 46) in expected_day_1m(day)
    assert datetime(2026, 4, 10, 13, 45) in expected_day_1m(day)
    assert datetime(2026, 4, 10, 13, 46) not in expected_day_1m(day)
    assert datetime(2026, 4, 10, 15, 1) in expected_night_1m(day)
    assert datetime(2026, 4, 11, 5, 0) in expected_night_1m(day)
    assert datetime(2026, 4, 11, 5, 1) not in expected_night_1m(day)
    assert datetime(2026, 4, 11, 0, 0) in expected_night_5m(day)
    assert datetime(2026, 4, 11, 5, 0) in expected_night_5m(day)
