import os
from pathlib import Path

import yaml

from tfx_trading.config import Config

_PACKAGE_ROOT = Path(__file__).resolve().parent


def load_config() -> Config:
    config_path = Path(_PACKAGE_ROOT / "config" / "config.yaml").expanduser()
    if not config_path.is_file():
        raise FileNotFoundError(f"找不到設定檔: {config_path}")

    with config_path.open(encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    config["api_key"], config["secret_key"] = _resolve_credentials()

    config["kbars_path"] = _PACKAGE_ROOT / "kbars_data"

    if not config["kbars_path"].exists():
        raise FileNotFoundError(f"找不到 kbars 資料夾: {config['kbars_path']}")

    return Config(**config)


def _resolve_credentials() -> tuple[str, str]:
    api_key = os.environ.get("SJ_API_KEY", "")
    secret_key = os.environ.get("SJ_SEC_KEY", "")
    if not api_key or not secret_key:
        raise ValueError("SJ_API_KEY 和 SJ_SEC_KEY 環境變數未設定")

    return api_key, secret_key


__all__ = [
    "load_config",
]
