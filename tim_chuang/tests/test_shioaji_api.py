from __future__ import annotations

import pytest
from unittest.mock import create_autospec, MagicMock
from shioaji_api import ShioajiAPI
from unittest.mock import patch, call
from shioaji import Shioaji
from config import Config

@pytest.fixture
def mock_config() -> MagicMock:
    mock_cfg = MagicMock(spec=Config)
    mock_cfg.simulation = True
    mock_cfg.api_key = "test_api_key"
    mock_cfg.secret_key = "test_secret_key"
    return mock_cfg

@pytest.fixture
def mock_shioaji() -> MagicMock:
    return create_autospec(
        Shioaji,
        instance=True,
    )

@pytest.fixture
def shioaji_api(mock_shioaji: MagicMock, mock_config: MagicMock) -> ShioajiAPI:
    return ShioajiAPI(shioaji=mock_shioaji, config=mock_config)

def test_init(shioaji_api: ShioajiAPI, mock_shioaji: MagicMock):
    assert shioaji_api._shioaji is mock_shioaji

def test_login(shioaji_api: ShioajiAPI, mock_shioaji: MagicMock, mock_config: MagicMock):
    mock_shioaji.usage.return_value = "10%"
    mock_shioaji.Contracts.Futures.TMF.TMFR1 = "TMFR1"
    mock_shioaji.futopt_account.account_type = "F"
    mock_shioaji.futopt_account.account_id = "123456"

    with patch("builtins.print") as mock_print:
        shioaji_api.login()

    mock_shioaji.login.assert_called_once_with(api_key=mock_config.api_key, secret_key=mock_config.secret_key)

    mock_print.assert_has_calls([
        call("--------------------------------"),
        call("account:F123456 |"),
        call("contract:TMFR1 |"),
        call("api_usage:10% |"),
        call("--------------------------------"),
    ])

    assert shioaji_api.get_contract() == "TMFR1"

def test_logout(shioaji_api: ShioajiAPI, mock_shioaji: MagicMock):
    shioaji_api.logout()
    mock_shioaji.logout.assert_called_once()

def test_kbars(shioaji_api: ShioajiAPI, mock_shioaji: MagicMock, mock_config: MagicMock):
    mock_shioaji.Contracts.Futures.TMF.TMFR1 = "TMFR1"
    mock_shioaji.kbars.return_value = "fake_kbars"

    shioaji_api.login()

    mock_shioaji.login.assert_called_once()

    result = shioaji_api.kbars(
        contract=shioaji_api.get_contract(),
        start="2026-01-01",
        end="2026-01-02",
    )

    mock_shioaji.kbars.assert_called_once_with(
        contract="TMFR1",
        start="2026-01-01",
        end="2026-01-02",
    )

    assert result == "fake_kbars"

def test_get_contract_without_login(shioaji_api: ShioajiAPI):
    with pytest.raises(
        RuntimeError,
        match="API 尚未登入，無法取得合約資訊！請先執行 login\\(\\)。",
    ):
        shioaji_api.get_contract()
