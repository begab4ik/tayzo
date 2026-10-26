"""Расчёт цен. Цена = себестоимость в TON × курс TON/UZS × (1 + наценка), округление вверх до 100 сум."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import settings_store as cfg
from app.core.enums import ProductType
from app.core.money import round_up_100

PREMIUM_MONTHS = (3, 6, 12)


@dataclass
class Quote:
    product: ProductType
    quantity: int
    price_uzs: int          # сколько платит клиент
    cost_ton: Decimal       # наша себестоимость в TON
    cost_uzs: int           # себестоимость в UZS по текущему курсу
    ton_rate: Decimal

    @property
    def profit_uzs(self) -> int:
        return self.price_uzs - self.cost_uzs


async def quote_stars(session: AsyncSession, quantity: int) -> Quote:
    rate = await cfg.get_dec(session, "ton_rate_uzs")
    star_ton = await cfg.get_dec(session, "star_price_ton")
    markup = await cfg.get_dec(session, "markup_percent")
    override = await cfg.get_dec(session, "star_price_uzs_override")

    cost_ton = star_ton * quantity
    cost_uzs = int(cost_ton * rate)
    if override > 0:
        price = round_up_100(override * quantity)
    else:
        price = round_up_100(Decimal(cost_uzs) * (1 + markup / 100))
    return Quote(ProductType.STARS, quantity, price, cost_ton, cost_uzs, rate)


async def quote_premium(session: AsyncSession, months: int) -> Quote:
    if months not in PREMIUM_MONTHS:
        raise ValueError("months must be 3, 6 or 12")
    rate = await cfg.get_dec(session, "ton_rate_uzs")
    markup = await cfg.get_dec(session, "markup_percent")
    cost_ton = await cfg.get_dec(session, f"premium_{months}_ton")
    cost_uzs = int(cost_ton * rate)
    price = round_up_100(Decimal(cost_uzs) * (1 + markup / 100))
    return Quote(ProductType.PREMIUM, months, price, cost_ton, cost_uzs, rate)


async def star_price_each(session: AsyncSession) -> int:
    """Цена одной звезды для витрины (считаем по 100 и делим — так округление честнее)."""
    q = await quote_stars(session, 100)
    return q.price_uzs // 100
