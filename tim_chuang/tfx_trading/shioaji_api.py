from __future__ import annotations

import logging
from pathlib import Path
from types import TracebackType

from shioaji import Contract, KBars, Shioaji

from tfx_trading.config import Config

logger = logging.getLogger(__name__)


class ShioajiAPI:
    def __enter__(self) -> ShioajiAPI:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.logout()

    def __init__(self, shioaji: Shioaji, config: Config) -> None:
        self._shioaji = shioaji
        self._config = config

        self._shioaji.login(
            api_key=self._config.api_key,
            secret_key=self._config.secret_key,
        )
        api_usage = self._shioaji.usage()
        self._contract: Contract = self._shioaji.Contracts.Futures.TMF.TMFR1
        logger.info("--------------------------------")
        logger.info(
            "account:%s%s |",
            self._shioaji.futopt_account.account_type,
            self._shioaji.futopt_account.account_id,
        )
        logger.info("contract:%s |", self._contract)
        logger.info("api_usage:%s |", api_usage)
        logger.info("--------------------------------")

    def kbars(self, contract: Contract, start: str, end: str) -> KBars:
        return self._shioaji.kbars(contract=contract, start=start, end=end)

    def logout(self) -> None:
        self._shioaji.logout()

    def get_contract(self) -> Contract:
        return self._contract

    def kbars_path(self) -> Path:
        return self._config.kbars_path.expanduser()
