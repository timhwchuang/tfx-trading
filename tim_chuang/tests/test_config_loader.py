from __future__ import annotations

from pathlib import Path

import pytest

from tfx_trading import config_loader
from tfx_trading.config import Config


@pytest.fixture
def credentials(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    values = {"api_key": "sj_api_key", "secret_key": "sj_sec_key"}
    monkeypatch.setenv("SJ_API_KEY", values["api_key"])
    monkeypatch.setenv("SJ_SEC_KEY", values["secret_key"])
    return values


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    config = tmp_path / "config"
    config.mkdir()
    config_path = config / "config.yaml"
    config_path.write_text("simulation: true", encoding="utf-8")
    return config_path


@pytest.fixture
def kbars_dir(tmp_path: Path) -> Path:
    kbars_dir = tmp_path / "kbars_data"
    kbars_dir.mkdir()
    return kbars_dir


@pytest.fixture
def package_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(config_loader, "_PACKAGE_ROOT", tmp_path)
    return tmp_path


def test_load_config(
    config_file: Path, kbars_dir: Path, package_root: Path, credentials: dict[str, str]
) -> None:
    config = config_loader.load_config()
    assert config.api_key == credentials["api_key"]
    assert config.secret_key == credentials["secret_key"]
    assert config.simulation is True
    assert config.kbars_path == kbars_dir


def test_load_config_with_no_config(package_root: Path) -> None:
    with pytest.raises(FileNotFoundError, match="找不到設定檔: "):
        config_loader.load_config()


def test_load_config_with_no_kbars_data(
    config_file: Path, package_root: Path, credentials: dict[str, str]
) -> None:
    kbars_dir = package_root / "kbars_data"
    assert not kbars_dir.exists()
    config = config_loader.load_config()
    assert kbars_dir.is_dir()
    assert config.kbars_path == kbars_dir


def test_load_config_ignores_trading_section(
    tmp_path: Path,
    package_root: Path,
    credentials: dict[str, str],
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        "simulation: true\ntrading:\n  commission_nt: 20\n  fill_mode: conservative\n",
        encoding="utf-8",
    )
    config = config_loader.load_config()
    assert isinstance(config, Config)
    assert config.simulation is True
    assert not hasattr(config, "commission_nt")
    assert not hasattr(config, "trading")


def test_load_config_ignores_strategy_section(
    tmp_path: Path,
    package_root: Path,
    credentials: dict[str, str],
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        "simulation: true\nstrategy:\n  entry_price: top\n  max_daily_loss_nt: 3000\n",
        encoding="utf-8",
    )
    config = config_loader.load_config()
    assert isinstance(config, Config)
    assert config.simulation is True
    assert not hasattr(config, "entry_price")
    assert not hasattr(config, "strategy")


@pytest.mark.parametrize(
    "missing_env",
    [
        "SJ_API_KEY",
        "SJ_SEC_KEY",
    ],
)
def test_load_config_with_no_env_var(
    config_file: Path,
    kbars_dir: Path,
    package_root: Path,
    credentials: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    missing_env: str,
) -> None:
    monkeypatch.delenv(missing_env, raising=False)
    with pytest.raises(ValueError, match="環境變數未設定"):
        config_loader.load_config()
