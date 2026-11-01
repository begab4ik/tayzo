"""Провайдер подарков Telegram: отправка с аккаунта владельца, звёзды докупаются через Fragment при нехватке.

Заказ: order.quantity = цена подарка в звёздах, order.gift_id = id подарка.
Схема fulfill:
  1. баланс звёзд аккаунта < цены → купить недостающее (минимум min_stars) через Fragment на свой username,
     подождать зачисления (до ~3 мин);
  2. отправить подарок анонимно (hide_name=True).
"""
from __future__ import annotations

import asyncio
import logging
import math
from decimal import Decimal

from app.core import settings_store as cfg
from app.core.exceptions import ProviderAuthError, ProviderError
from app.db.base import get_session
from app.providers.base import FulfillResult, Provider, Recipient
from app.providers.telegram_account import tg_account

log = logging.getLogger(__name__)

TOPUP_WAIT_SEC = 180
TOPUP_POLL_SEC = 6


class TelegramGiftProvider(Provider):
    code = "tg_gifts"

    def __init__(self, stars_provider: Provider | None) -> None:
        self.stars_provider = stars_provider  # FragmentStarsProvider — для автодокупки; None = без докупки

    async def resolve_recipient(self, username: str, quantity: int) -> Recipient:
        u = await tg_account.resolve_user(username)
        return Recipient(username=u["username"], name=u["name"], token=str(u["id"]))

    async def fulfill(self, recipient: Recipient, quantity: int, gift_id: int | None = None) -> FulfillResult:
        if not gift_id:
            raise ProviderError("В заказе нет gift_id")
        need = int(quantity)
        cost_ton: Decimal | None = None
        balance = await tg_account.star_balance()
        if balance < need:
            cost_ton = await self._topup_stars(need - balance)
            balance = await self._wait_balance(need)
            if balance < need:
                raise ProviderError(f"Звёзды куплены, но ещё не зачислились (на аккаунте {balance}, нужно {need}) — повтори позже")
        await tg_account.send_gift(recipient.username, int(gift_id), hide_name=True)
        if cost_ton is None:
            async with get_session() as s:
                cost_ton = (await cfg.get_dec(s, "star_price_ton")) * need
        return FulfillResult(ok=True, external_id=f"gift:{gift_id}", cost_ton=cost_ton)

    async def _topup_stars(self, missing: int) -> Decimal:
        if self.stars_provider is None:
            raise ProviderError("Не хватает звёзд на аккаунте, а автодокупка через Fragment выключена")
        async with get_session() as s:
            mn = await cfg.get_int(s, "min_stars")
            own = await cfg.get(s, "tg_account_username")
            buffer = await cfg.get_int(s, "gift_stars_buffer")
        if not own:
            raise ProviderAuthError("У аккаунта подарков нет username — без него Fragment не может зачислить звёзды")
        qty = max(mn, int(math.ceil((missing + buffer) / 50.0) * 50))
        log.info("gift: buying %s stars for @%s via Fragment", qty, own)
        rcp = await self.stars_provider.resolve_recipient(own, qty)
        res = await self.stars_provider.fulfill(rcp, qty)
        return res.cost_ton or Decimal(0)

    async def _wait_balance(self, need: int) -> int:
        waited = 0
        bal = 0
        while waited < TOPUP_WAIT_SEC:
            await asyncio.sleep(TOPUP_POLL_SEC)
            waited += TOPUP_POLL_SEC
            try:
                bal = await tg_account.star_balance()
            except Exception as e:  # noqa: BLE001
                log.warning("star_balance poll failed: %s", e)
                continue
            if bal >= need:
                return bal
        return bal

    async def healthcheck(self) -> str:
        me = await tg_account.me()
        bal = await tg_account.star_balance()
        return f"@{me['username']}: {bal} ⭐"
