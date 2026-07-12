from __future__ import annotations

from shioaji import KBars, Shioaji, Contract
import typing
from pathlib import Path

if typing.TYPE_CHECKING:
    from config import Config

class ShioajiAPI:
    def __init__(self, shioaji: Shioaji, config: Config) -> None:
        self._shioaji = shioaji
        self._config = config
        self._contract: Contract | None = None

    def kbars(self, contract: Contract, start: str, end: str) -> KBars:
        return self._shioaji.kbars(contract=contract, start=start, end=end)

    def login(self) -> None:
        self._shioaji.login(
            api_key=self._config.api_key,
            secret_key=self._config.secret_key,
        )
        api_usage = self._shioaji.usage()
        self._contract = self._shioaji.Contracts.Futures.TMF.TMFR1
        print("--------------------------------")
        print(f"account:{self._shioaji.futopt_account.account_type}{self._shioaji.futopt_account.account_id} |")
        print(f"contract:{self._contract} |")
        print(f"api_usage:{api_usage} |")
        print("--------------------------------")

    def logout(self) -> None:
        self._shioaji.logout()

    def get_contract(self) -> Contract:
        if self._contract is None:
            raise RuntimeError("API 尚未登入，無法取得合約資訊！請先執行 login()。")
        return self._contract

    def kbar_path(self) -> Path:
        return self._config.kbars_path.expanduser()