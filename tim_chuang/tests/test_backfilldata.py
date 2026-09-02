from __future__ import annotations

from argparse import Namespace
from datetime import datetime
from pathlib import Path
from typing import Callable, cast
from unittest.mock import MagicMock, call, create_autospec, patch

import pytest
from shioaji import KBars

import tfx_trading.backfilldata
from tfx_trading.backfilldata import BackfillData, parse_date, parse_ymd
from tfx_trading.shioaji_api import ShioajiAPI


@pytest.fixture
def api_client(
    tmp_path: Path,
) -> MagicMock:
    mock_sj = create_autospec(
        ShioajiAPI,
        instance=True,
    )

    mock_sj.kbars_path.side_effect = lambda: tmp_path / "kbars"
    mock_sj.get_contract.side_effect = lambda: "TMFR1"

    return cast(MagicMock, mock_sj)


@pytest.fixture
def backfill_data() -> BackfillData:
    return BackfillData()


@pytest.fixture
def args() -> tuple[datetime, datetime]:
    return datetime(2026, 1, 1), datetime(2026, 1, 3)


@pytest.fixture
def make_kbars() -> Callable[..., MagicMock]:
    def factory(
        *,
        ts: list[int],
        Open: list[float],
        High: list[float],
        Low: list[float],
        Close: list[float],
        Volume: list[int],
        Amount: list[int],
    ) -> MagicMock:
        kbars = cast(MagicMock, create_autospec(KBars, instance=True))
        kbars.ts = ts
        kbars.Open = Open
        kbars.High = High
        kbars.Low = Low
        kbars.Close = Close
        kbars.Volume = Volume
        kbars.Amount = Amount
        return kbars

    return factory


def test_parse_ymd() -> None:
    assert parse_ymd("2026-01-01") == datetime(2026, 1, 1)


def test_parse_ymd_raises_valueerror() -> None:
    with pytest.raises(ValueError):
        parse_ymd("not a date")


@pytest.mark.parametrize(
    "start_date, end_date, expected_error",
    [
        (datetime(2026, 1, 2), datetime(2026, 1, 1), ValueError),
        (datetime(2026, 1, 1), datetime(2026, 1, 1), None),
    ],
)
def test_parse_date_raises_valueerror(
    start_date: datetime, end_date: datetime, expected_error: type[Exception] | None
) -> None:
    cmd = [
        "--start_date",
        start_date.strftime("%Y-%m-%d"),
        "--end_date",
        end_date.strftime("%Y-%m-%d"),
    ]
    if expected_error is None:
        start_dt, end_dt = parse_date(cmd)
        assert start_dt == start_date
        assert end_dt == end_date
    else:
        with pytest.raises(expected_error):
            parse_date(cmd)


def test_run_raise_vendor_error(
    backfill_data: BackfillData, api_client: MagicMock, args: tuple[datetime, datetime]
) -> None:
    api_client.kbars.side_effect = RuntimeError("connection failed")
    with pytest.raises(RuntimeError):
        backfill_data.run(api_client, *args)


def test_run(
    backfill_data: BackfillData,
    api_client: MagicMock,
    args: tuple[datetime, datetime],
    make_kbars: Callable[..., MagicMock],
) -> None:
    kbars_day1 = make_kbars(
        ts=[1767225600000000000],
        Open=[100.0],
        High=[105.0],
        Low=[99.0],
        Close=[102.0],
        Volume=[10],
        Amount=[1000],
    )

    kbars_day2 = make_kbars(
        ts=[1767312000000000000],
        Open=[102.0],
        High=[106.0],
        Low=[101.0],
        Close=[105.0],
        Volume=[15],
        Amount=[1575],
    )
    empty_kbars = make_kbars(ts=[], Open=[], High=[], Low=[], Close=[], Volume=[], Amount=[])
    api_client.kbars.side_effect = [kbars_day1, kbars_day2, empty_kbars]

    backfill_data.run(api_client, *args, sleep=lambda _: None)

    api_client.kbars.assert_has_calls(
        [
            call(
                contract="TMFR1",
                start="2026-01-01",
                end="2026-01-01",
            ),
            call(
                contract="TMFR1",
                start="2026-01-02",
                end="2026-01-02",
            ),
            call(
                contract="TMFR1",
                start="2026-01-03",
                end="2026-01-03",
            ),
        ],
        any_order=False,
    )

    target_filename = api_client.kbars_path() / "TMFR1_kbars_2026-01-01.csv"
    assert target_filename.exists()
    with target_filename.open() as f:
        expected_content = "timestamp,open,high,low,close,volume,amount\n"
        expected_content += "2026-01-01 00:00:00.000000,100.0,105.0,99.0,102.0,10,1000\n"
        assert f.read() == expected_content

    target_filename = api_client.kbars_path() / "TMFR1_kbars_2026-01-02.csv"
    assert target_filename.exists()
    with target_filename.open() as f:
        expected_content = "timestamp,open,high,low,close,volume,amount\n"
        expected_content += "2026-01-02 00:00:00.000000,102.0,106.0,101.0,105.0,15,1575\n"
        assert f.read() == expected_content

    target_filename = api_client.kbars_path() / "TMFR1_kbars_2026-01-03.csv"
    assert not target_filename.exists()


def test_run_write_csv_error(
    backfill_data: BackfillData,
    api_client: MagicMock,
    args: tuple[datetime, datetime],
    make_kbars: Callable[..., MagicMock],
) -> None:
    kbars_day1 = make_kbars(
        ts=[1767225600000000000],
        Open=[100.0],
        High=[105.0],
        Low=[99.0],
        Close=[102.0],
        Volume=[10],
        Amount=[1000],
    )
    empty_kbars = make_kbars(ts=[], Open=[], High=[], Low=[], Close=[], Volume=[], Amount=[])
    api_client.kbars.side_effect = [kbars_day1, empty_kbars, empty_kbars]
    with patch("pathlib.Path.open", side_effect=OSError):
        with pytest.raises(OSError):
            backfill_data.run(api_client, *args, sleep=lambda _: None)


def test_run_data_not_zippable(
    backfill_data: BackfillData,
    api_client: MagicMock,
    args: tuple[datetime, datetime],
    make_kbars: Callable[..., MagicMock],
) -> None:
    kbars_day1 = make_kbars(
        ts=[1767225600000000000, 1767225600000000001],
        Open=[100.0],
        High=[105.0],
        Low=[99.0],
        Close=[102.0],
        Volume=[10],
        Amount=[1000],
    )
    empty_kbars = make_kbars(ts=[], Open=[], High=[], Low=[], Close=[], Volume=[], Amount=[])
    api_client.kbars.side_effect = [kbars_day1, empty_kbars, empty_kbars]
    with pytest.raises(ValueError):
        backfill_data.run(api_client, *args, sleep=lambda _: None)


def test_main() -> None:
    mock_api = MagicMock()
    mock_backfill = MagicMock()
    mock_shioaji_api = MagicMock()
    mock_shioaji_api.__enter__.return_value = mock_api

    with (
        patch("tfx_trading.backfilldata.load_config"),
        patch("tfx_trading.backfilldata.Shioaji"),
        patch("tfx_trading.backfilldata.ShioajiAPI", return_value=mock_shioaji_api),
        patch(
            "tfx_trading.backfilldata.BackfillData",
            return_value=mock_backfill,
        ),
        patch(
            "tfx_trading.backfilldata.parse_args",
            return_value=Namespace(
                start_date=datetime(2026, 1, 1),
                end_date=datetime(2026, 1, 2),
                overwrite=False,
            ),
        ),
    ):
        tfx_trading.backfilldata.main()

    mock_backfill.run.assert_called_once_with(
        mock_api,
        datetime(2026, 1, 1),
        datetime(2026, 1, 2),
        overwrite=False,
    )


def test_run_skips_existing_file_without_kbars_or_sleep(
    backfill_data: BackfillData,
    api_client: MagicMock,
    args: tuple[datetime, datetime],
) -> None:
    kbars_dir = api_client.kbars_path()
    kbars_dir.mkdir(parents=True)
    existing = kbars_dir / "TMFR1_kbars_2026-01-01.csv"
    existing.write_text("keep\n", encoding="utf-8")
    slept: list[float] = []

    empty = MagicMock()
    empty.ts = []
    api_client.kbars.return_value = empty
    backfill_data.run(api_client, *args, sleep=slept.append)

    assert existing.read_text(encoding="utf-8") == "keep\n"
    assert api_client.kbars.call_count == 2
    api_client.kbars.assert_has_calls(
        [
            call(contract="TMFR1", start="2026-01-02", end="2026-01-02"),
            call(contract="TMFR1", start="2026-01-03", end="2026-01-03"),
        ]
    )
    assert slept == [0.15, 0.15]


def test_run_overwrite_refetches_existing(
    backfill_data: BackfillData,
    api_client: MagicMock,
    args: tuple[datetime, datetime],
    make_kbars: Callable[..., MagicMock],
) -> None:
    kbars_dir = api_client.kbars_path()
    kbars_dir.mkdir(parents=True)
    existing = kbars_dir / "TMFR1_kbars_2026-01-01.csv"
    existing.write_text("stale\n", encoding="utf-8")
    kbars_day1 = make_kbars(
        ts=[1767225600000000000],
        Open=[100.0],
        High=[105.0],
        Low=[99.0],
        Close=[102.0],
        Volume=[10],
        Amount=[1000],
    )
    empty_kbars = make_kbars(ts=[], Open=[], High=[], Low=[], Close=[], Volume=[], Amount=[])
    api_client.kbars.side_effect = [kbars_day1, empty_kbars, empty_kbars]
    slept: list[float] = []

    backfill_data.run(api_client, *args, overwrite=True, sleep=slept.append)

    assert existing.exists()
    assert "stale" not in existing.read_text(encoding="utf-8")
    assert api_client.kbars.call_count == 3
    assert slept == [0.15, 0.15, 0.15]
