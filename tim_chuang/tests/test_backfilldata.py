from __future__ import annotations

import pytest
from unittest.mock import MagicMock, create_autospec,call
from tfx_trading.backfilldata import BackfillData
from tfx_trading.shioaji_api import ShioajiAPI
from tfx_trading.backfilldata import parse_ymd, parse_date
from typing import cast
from datetime import datetime
from pathlib import Path
from shioaji import KBars, Contract

@pytest.fixture
def api_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock_sj = create_autospec(
        ShioajiAPI,
        instance=True,
    )

    def tmp_kbars_path() -> Path:
        tests_kbars_path = Path("test_kbars")
        tests_kbars_path.mkdir(parents=True, exist_ok=True)
        return tests_kbars_path

    def get_contract() -> Contract:
        return "TMFR1"

    monkeypatch.setattr(mock_sj, "kbars_path", tmp_kbars_path)
    monkeypatch.setattr(mock_sj, "get_contract", get_contract)
    return cast(MagicMock, mock_sj)

@pytest.fixture
def backfill_data() -> BackfillData:
    return BackfillData()

@pytest.fixture
def args() -> tuple[datetime, datetime]:
    return datetime(2026, 1, 1), datetime(2026, 1, 2)

def test_parse_ymd() -> None:
    assert parse_ymd("2026-01-01") == datetime(2026, 1, 1)

def test_parse_ymd_raises_valueerror() -> None:
    with pytest.raises(ValueError):
        parse_ymd("not a date")

@pytest.mark.parametrize("start_date, end_date, expected_error", [
    (datetime(2026, 1, 2), datetime(2026, 1, 1), ValueError),
    (datetime(2026, 1, 1), datetime(2026, 1, 1), None),
])
def test_parse_date_raises_valueerror(start_date: datetime, end_date: datetime, expected_error: type[Exception] | None) -> None:
    cmd = ["--start_date", start_date.strftime("%Y-%m-%d"), "--end_date", end_date.strftime("%Y-%m-%d")]
    if expected_error is None:
        start_dt, end_dt = parse_date(cmd)
        assert start_dt == start_date
        assert end_dt == end_date
    else:
        with pytest.raises(expected_error):
            parse_date(cmd)

def test_run_rasie_vendor_error(backfill_data: BackfillData, api_client: MagicMock, args: tuple[datetime, datetime]) -> None:
    api_client.kbars.side_effect = RuntimeError("connection failed")
    with pytest.raises(RuntimeError):
        backfill_data.run(api_client, *args)

def test_run(backfill_data: BackfillData, api_client: MagicMock, args: tuple[datetime, datetime]) -> None:
    mock_kbars_day1 = MagicMock()
    mock_kbars_day1.ts = [1767225600000000000]
    mock_kbars_day1.Open = [100.0]
    mock_kbars_day1.High = [105.0]
    mock_kbars_day1.Low = [99.0]
    mock_kbars_day1.Close = [102.0]
    mock_kbars_day1.Volume = [10]
    mock_kbars_day1.Amount = [1000]

    mock_kbars_day2 = MagicMock()
    mock_kbars_day2.ts = [1767312000000000000]
    mock_kbars_day2.Open = [102.0]
    mock_kbars_day2.High = [106.0]
    mock_kbars_day2.Low = [101.0]
    mock_kbars_day2.Close = [105.0]
    mock_kbars_day2.Volume = [15]
    mock_kbars_day2.Amount = [1575]
    api_client.kbars.side_effect = [mock_kbars_day1, mock_kbars_day2]

    backfill_data.run(api_client, *args)

    api_client.kbars.assert_has_calls([call(contract="TMFR1", start="2026-01-01", end="2026-01-01"), call(contract="TMFR1", start="2026-01-02", end="2026-01-02")], any_order=True)

    target_filename = api_client.kbars_path() / "TMFR1_kbars_2026-01-01.csv"
    assert target_filename.exists()
    with target_filename.open() as f:
        assert f.read() == "timestamp,open,high,low,close,volume,amount\n2026-01-01 00:00:00.000000,100.0,105.0,99.0,102.0,10,1000\n"

    target_filename = api_client.kbars_path() / "TMFR1_kbars_2026-01-02.csv"
    assert target_filename.exists()
    with target_filename.open() as f:
        assert f.read() == "timestamp,open,high,low,close,volume,amount\n2026-01-02 00:00:00.000000,102.0,106.0,101.0,105.0,15,1575\n"