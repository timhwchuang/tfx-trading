from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, create_autospec

import pytest
from shioaji import Shioaji

from config import Config
from shioaji_api import ShioajiAPI


@pytest.fixture
def mock_config() -> MagicMock:
    mock_cfg = MagicMock(spec=Config)
    mock_cfg.simulation = True
    mock_cfg.api_key = "test_api_key"
    mock_cfg.secret_key = "test_secret_key"
    mock_cfg.kbars_path = Path("~/kbars_data")
    return mock_cfg


@pytest.fixture
def mock_shioaji() -> MagicMock:
    mock_sj = create_autospec(Shioaji, instance=True)
    mock_sj.usage.return_value = "10%"
    mock_sj.Contracts.Futures.TMF.TMFR1 = "TMFR1"
    mock_sj.futopt_account.account_type = "F"
    mock_sj.futopt_account.account_id = "123456"
    mock_sj.kbars.return_value = "fake_kbars"
    return mock_sj


@pytest.fixture
def shioaji_api(mock_shioaji: MagicMock, mock_config: MagicMock) -> ShioajiAPI:
    return ShioajiAPI(shioaji=mock_shioaji, config=mock_config)


def test_init(
    mock_shioaji: MagicMock, mock_config: MagicMock, caplog: pytest.LogCaptureFixture
):
    with caplog.at_level(logging.INFO, logger="shioaji_api"):
        shioaji_api = ShioajiAPI(shioaji=mock_shioaji, config=mock_config)

    mock_shioaji.login.assert_called_once_with(
        api_key=mock_config.api_key, secret_key=mock_config.secret_key
    )
    mock_shioaji.usage.assert_called_once()

    assert "account:F123456 |" in caplog.text
    assert "contract:TMFR1 |" in caplog.text
    assert "api_usage:10% |" in caplog.text

    assert shioaji_api._shioaji is mock_shioaji
    assert shioaji_api.get_contract() == mock_shioaji.Contracts.Futures.TMF.TMFR1


def test_logout(shioaji_api: ShioajiAPI, mock_shioaji: MagicMock):
    shioaji_api.logout()
    mock_shioaji.logout.assert_called_once()


def test_kbars(shioaji_api: ShioajiAPI, mock_shioaji: MagicMock):
    contract = shioaji_api.get_contract()

    result = shioaji_api.kbars(
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


def test_kbars_path(shioaji_api: ShioajiAPI):
    assert shioaji_api.kbars_path() == Path.home() / "kbars_data"


def test_context_manager(mock_shioaji: MagicMock, mock_config: MagicMock):
    with ShioajiAPI(shioaji=mock_shioaji, config=mock_config) as shioaji_api:
        assert shioaji_api._shioaji is mock_shioaji
    mock_shioaji.logout.assert_called_once()
