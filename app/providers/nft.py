"""Провайдер NFT-подарков: покупка лота с рынка перепродажи Telegram сразу на получателя.

order.quantity = цена лота в ⭐, order.nft_slug = slug лота (PlushPepe-1234).
Звёзды докупаются через Fragment так же, как для обычных подарков (наследуем TelegramGiftProvider).
"""
from __future__ import annotations

import logging
from decimal import Decimal

from app.core import settings_store as cfg
from app.core.exceptions import ProviderError
from app.db.base import get_session
from app.providers.base import FulfillResult, Recipient
from app.providers.gifts import TelegramGiftProvider
from app.providers.telegram_account import tg_account

log = logging.getLogger(__name__)


class TelegramNftProvider(TelegramGiftProvider):
    code = "tg_nft"

    async def fulfill(self, recipient: Recipient, quantity: int, slug: str | None = None, **_) -> FulfillResult:  # type: ignore[override]
        if not slug:
            raise ProviderError("В заказе нет slug лота")
        need = int(quantity)
        cost_ton: Decimal | None = None
        balance = await tg_account.star_balance()
        if balance < need:
            cost_ton = await self._topup_stars(need - balance)
            balance = await self._wait_balance(need)
            if balance < need:
                raise ProviderError(f"Звёзды куплены, но ещё не зачислились (на аккаунте {balance}, нужно {need}) — повтори позже")
        spent = await tg_account.buy_nft(slug, recipient.username, expected_stars=need)
        if cost_ton is None:
            async with get_session() as s:
                cost_ton = (await cfg.get_dec(s, "star_price_ton")) * spent
        log.info("nft %s bought for @%s: %s stars", slug, recipient.username, spent)
        return FulfillResult(ok=True, external_id=f"nft:{slug}", cost_ton=cost_ton)
