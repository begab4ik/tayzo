"""Обёртка над TON-кошельком (tonutils 2.x): баланс и отправка транзакций, которые формирует Fragment."""
from __future__ import annotations

import asyncio
import base64
import logging
from decimal import Decimal

from app.config import settings
from app.core.exceptions import ProviderError

log = logging.getLogger(__name__)

NANO = Decimal(10**9)


class TonWallet:
    def __init__(self) -> None:
        self._wallet = None
        self._public_key = None
        self._lock = asyncio.Lock()  # одна транзакция за раз: seqno кошелька последовательный

    def _ensure(self):
        if self._wallet is not None:
            return
        if not settings.ton_mnemonic:
            raise ProviderError("TON_MNEMONIC не задан")
        from ton_core import NetworkGlobalID
        from tonutils.clients import ToncenterClient
        from tonutils.contracts import WalletV4R2, WalletV5R1

        client = ToncenterClient(NetworkGlobalID.MAINNET, api_key=settings.toncenter_api_key or None, timeout=20)
        cls = WalletV5R1 if settings.ton_wallet_version.lower() == "v5r1" else WalletV4R2
        wallet, public_key, _priv, _mn = cls.from_mnemonic(client, settings.ton_mnemonic.split())
        self._wallet = wallet
        self._public_key = public_key

    @property
    def address(self) -> str:
        self._ensure()
        return self._wallet.address.to_str(is_user_friendly=True, is_bounceable=False)

    def tonconnect_account(self) -> dict:
        """Объект account в формате TonConnect — его ждёт Fragment в getBuyStarsLink."""
        self._ensure()
        state_init = base64.b64encode(self._wallet.state_init.serialize().to_boc()).decode()
        return {
            "address": self._wallet.address.to_str(is_user_friendly=False),
            "chain": "-239",
            "walletStateInit": state_init,
            "publicKey": self._public_key.as_hex,
        }

    async def balance(self) -> Decimal:
        """Баланс в TON. Запрашиваем напрямую у клиента: wallet.refresh() глотает ошибки и отдаёт 0."""
        self._ensure()
        try:
            info = await self._wallet.client.get_info(self._wallet.address)
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"TON API недоступен: {type(e).__name__}: {e}") from e
        return Decimal(info.balance) / NANO

    async def send(self, messages: list[dict]) -> str:
        """messages: [{address, amount (нанотоны, str), payload (base64 BOC)}] из ответа Fragment.
        Возвращает hash внешнего сообщения."""
        self._ensure()
        from ton_core import Cell
        from tonutils.contracts import TONTransferBuilder

        def build(m: dict) -> TONTransferBuilder:
            body = Cell.one_from_boc(base64.b64decode(m["payload"])) if m.get("payload") else None
            return TONTransferBuilder(destination=m["address"], amount=int(m["amount"]), body=body)

        async with self._lock:
            if len(messages) == 1:
                ext = await self._wallet.transfer_message(build(messages[0]))
            else:
                ext = await self._wallet.batch_transfer_message([build(m) for m in messages])
            tx_hash = ext.normalized_hash.hex() if hasattr(ext.normalized_hash, "hex") else str(ext.normalized_hash)
            log.info("TON tx sent: %s", tx_hash)
            return tx_hash


ton_wallet = TonWallet()
