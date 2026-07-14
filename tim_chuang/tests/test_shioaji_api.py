from __future__ import annotations

import logging
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, create_autospec

import pytest
from shioaji import Shioaji

from tfx_trading import shioaji_api as shioaji_api_module
from tfx_trading.config import Config
from tfx_trading.shioaji_api import ShioajiAPI


@pytest.fixture
def mock_config() -> Config:
    mock_cfg = cast(
        MagicMock,
        create_autospec(
            Config,
            instance=True,
        ),
    )
    mock_cfg.simulation = True
    mock_cfg.api_key = "test_api_key"
    mock_cfg.secret_key = "test_secret_key"
    mock_cfg.kbars_path = Path("~/kbars_data")
    return cast(Config, mock_cfg)


@pytest.fixture
def mock_shioaji() -> MagicMock:
    mock_sj = cast(
        MagicMock,
        create_autospec(
            Shioaji,
            instance=True,
        ),
    )

    mock_sj.usage.return_value = "10%"
    mock_sj.Contracts.Futures.TMF.TMFR1 = "TMFR1"
    mock_sj.futopt_account.account_type = "F"
    mock_sj.futopt_account.account_id = "123456"
    mock_sj.kbars.return_value = "fake_kbars"

    return mock_sj


@pytest.fixture
def api_client(mock_shioaji: MagicMock, mock_config: Config) -> ShioajiAPI:
    return ShioajiAPI(shioaji=mock_shioaji, config=mock_config)


def test_init(
    mock_shioaji: MagicMock, mock_config: Config, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(
        logging.INFO,
        logger=shioaji_api_module.__name__,
    ):
        api_client = ShioajiAPI(shioaji=mock_shioaji, config=mock_config)

    mock_shioaji.login.assert_called_once_with(
        api_key=mock_config.api_key, secret_key=mock_config.secret_key
    )
    mock_shioaji.usage.assert_called_once()

    assert "account:F123456 |" in caplog.text
    assert "contract:TMFR1 |" in caplog.text
    assert "api_usage:10% |" in caplog.text
    assert api_client.get_contract() == mock_shioaji.Contracts.Futures.TMF.TMFR1


def test_logout(api_client: ShioajiAPI, mock_shioaji: MagicMock) -> None:
    api_client.logout()
    mock_shioaji.logout.assert_called_once()


def test_kbars(api_client: ShioajiAPI, mock_shioaji: MagicMock) -> None:
    contract = api_client.get_contract()

    result = api_client.kbars(
        contract=contract,
        start="2026-01-01",
        end="2026-01-02",
    )

    mock_shioaji.kbars.assert_called_once_with(
        contract=contract,
        start="2026-01-01",
        end="2026-01-02",
    )

    assert result == "fake_kbars"


def test_kbars_path(api_client: ShioajiAPI) -> None:
    assert api_client.kbars_path() == Path.home() / "kbars_data"


def test_context_manager(mock_shioaji: MagicMock, mock_config: Config) -> None:
    with ShioajiAPI(shioaji=mock_shioaji, config=mock_config) as api_client:
        assert api_client._shioaji is mock_shioaji
    mock_shioaji.logout.assert_called_once()
