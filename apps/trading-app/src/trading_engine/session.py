"""Session management: login, CA, contract resolve (Phase G3 SessionService).

Position broker I/O lives in ``position_sync.PositionSyncService``.
"""

from __future__ import annotations

import os
from typing import Any, Protocol

from trading_engine.core.host_service import HostBoundService
from trading_engine.logging_setup import get_logger

logger = get_logger()


class SessionHost(Protocol):
    """Surface used by session login / CA / contract resolve."""

    api: Any
    contract: Any
    _cfg: Any
    _api_lock: Any

    def _call_api(self, fn, *args, **kwargs): ...


class _SessionMethods:
    def _activate_ca(self) -> None:
        """P4-10: 先無 person_id；失敗則以 env / 帳號 person_id 重試。"""
        try:
            if self._call_api(
                self.api.activate_ca,
                ca_path=self._cfg.ca_path,
                ca_passwd=self._cfg.ca_passwd,
            ):
                logger.info("CA 憑證啟用成功")
                return
        except Exception as e:
            logger.warning("CA 啟用失敗（無 person_id）: %s", e)

        person_id = os.environ.get("SJ_CA_PERSON_ID") or self._call_api(
            lambda: getattr(self.api.futopt_account, "person_id", None)
        )
        if not person_id:
            raise RuntimeError("CA 憑證啟用失敗；請設定 SJ_CA_PERSON_ID 或確認券商帳號 person_id")

        if not self._call_api(
            self.api.activate_ca,
            ca_path=self._cfg.ca_path,
            ca_passwd=self._cfg.ca_passwd,
            person_id=person_id,
        ):
            raise RuntimeError(f"CA 憑證啟用失敗（person_id={person_id}）")
        logger.info("CA 憑證啟用成功（person_id）")

    def _require_futopt_account(self) -> None:
        account = self._call_api(lambda: self.api.futopt_account)
        if account is None:
            raise RuntimeError("無期貨帳號，請確認帳號已開通期貨並完成簽署")

    def login(self):
        self._cfg.warn_if_placeholder_credentials(simulation=self._cfg.simulation)
        self._call_api(
            self.api.login,
            api_key=self._cfg.api_key,
            secret_key=self._cfg.secret_key,
            subscribe_trade=True,
        )
        self._require_futopt_account()
        self.contract = self._resolve_contract()
        account = self._call_api(lambda: self.api.futopt_account)
        logger.info(
            "登入成功 | 合約: %s | 模擬: %s | 帳號: %s",
            self.contract.code,
            self._cfg.simulation,
            getattr(account, "account_id", "N/A"),
        )

        if not self._cfg.simulation:
            if not self._cfg.ca_path or not self._cfg.ca_passwd:
                raise RuntimeError("正式模式需設定 SJ_CA_PATH 與 SJ_CA_PASSWD")
            self._activate_ca()
            account = self._call_api(lambda: self.api.futopt_account)
            self._call_api(self.api.subscribe_trade, account)

        self.sync_positions(force_resync=True)
        self._log_api_usage("login")

    def _log_api_usage(self, context: str) -> None:
        try:
            usage = self._call_api(self.api.usage)
        except Exception as e:
            logger.warning("API usage 查詢失敗 (%s): %s", context, e)
            return

        logger.info(
            "API usage [%s] | bytes=%s limit=%s remaining=%s connections=%s",
            context,
            usage.bytes,
            usage.limit_bytes,
            usage.remaining_bytes,
            usage.connections,
        )
        if usage.limit_bytes > 0 and usage.remaining_bytes < usage.limit_bytes * 0.1:
            logger.warning(
                "API 流量剩餘 < 10%% | remaining=%s limit=%s",
                usage.remaining_bytes,
                usage.limit_bytes,
            )

    def _resolve_contract(self):
        code = self._cfg.product_code
        category = code[:3]  # TXF / MXF / TMF for TXFR1, MXFR1, TMFR1, ...
        # Phase G0: Contracts lookup is broker I/O — never under domain lock.
        return self._call_api(self._resolve_contract_unlocked, code, category)

    def _resolve_contract_unlocked(self, code: str, category: str):
        cat = getattr(self.api.Contracts.Futures, category, None)
        if cat is not None and hasattr(cat, code):
            return getattr(cat, code)
        return self.api.Contracts.Futures[code]

class SessionService(HostBoundService):
    def __init__(self, host: SessionHost) -> None:
        super().__init__(host, _SessionMethods)


SessionMixin = SessionService

__all__ = ["SessionHost", "SessionService", "SessionMixin"]

