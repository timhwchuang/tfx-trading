from __future__ import annotations

from pathlib import Path

import pytest

from tfx_trading import config_loader


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
    with pytest.raises(FileNotFoundError, match="找不到 kbars 資料夾: "):
        config_loader.load_config()


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
