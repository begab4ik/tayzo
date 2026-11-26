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
        self._private_key = _priv
        self._connected = False

    async def _conn(self):
        """tonutils 2.x: клиент нужно открыть перед первым запросом (иначе тихие нули/ошибки)."""
        self._ensure()
        if not self._connected:
            await self._wallet.client.connect()
            self._connected = True
        return self._wallet.client

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

    def ton_proof(self, payload: str, domain: str) -> dict:
        """Подпись ton_proof (TonConnect v2) — доказывает сайту, что кошелёк наш. Денег не тратит."""
        import hashlib
        import time

        from ton_core import sign_message

        self._ensure()
        ts = int(time.time())
        addr = self._wallet.address
        d = domain.encode()
        msg = (
            b"ton-proof-item-v2/"
            + int(addr.wc).to_bytes(4, "big", signed=True)
            + addr.hash_part
            + len(d).to_bytes(4, "little")
            + d
            + ts.to_bytes(8, "little")
            + payload.encode()
        )
        full = b"\xff\xff" + b"ton-connect" + hashlib.sha256(msg).digest()
        sig = sign_message(hashlib.sha256(full).digest(), self._private_key.keypair.as_bytes)
        return {"timestamp": ts, "domain": {"lengthBytes": len(d), "value": domain}, "signature": base64.b64encode(sig).decode(), "payload": payload}

    async def balance(self) -> Decimal:
        """Баланс в TON. Запрашиваем напрямую у клиента: wallet.refresh() глотает ошибки и отдаёт 0."""
        client = await self._conn()
        try:
            info = await client.get_info(self._wallet.address)
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"TON API недоступен: {type(e).__name__}: {e}") from e
        return Decimal(info.balance) / NANO

    def build_messages(self, messages: list[dict]) -> list:
        """Собрать TONTransferBuilder'ы из сообщений Fragment (ничего не отправляет)."""
        self._ensure()
        from ton_core import Cell
        from tonutils.contracts import TONTransferBuilder

        out = []
        for m in messages:
            body = None
            if m.get("payload"):
                body = Cell.one_from_boc(_b64decode(m["payload"]))
            out.append(TONTransferBuilder(destination=m["address"], amount=int(m["amount"]), body=body))
        return out

    async def send(self, messages: list[dict]) -> str:
        """messages: [{address, amount (нанотоны, str), payload (base64 BOC)}] из ответа Fragment.
        Возвращает hash внешнего сообщения."""
        await self._conn()
        builders = self.build_messages(messages)
        async with self._lock:
            if len(builders) == 1:
                ext = await self._wallet.transfer_message(builders[0])
            else:
                ext = await self._wallet.batch_transfer_message(builders)
            tx_hash = ext.normalized_hash.hex() if hasattr(ext.normalized_hash, "hex") else str(ext.normalized_hash)
            log.info("TON tx sent: %s", tx_hash)
            return tx_hash


def _b64decode(s: str) -> bytes:
    """Fragment отдаёт payload в base64 без '=' и иногда в url-safe варианте — выравниваем и декодируем."""
    s = s.strip().replace("-", "+").replace("_", "/")
    s += "=" * (-len(s) % 4)
    return base64.b64decode(s)


ton_wallet = TonWallet()
