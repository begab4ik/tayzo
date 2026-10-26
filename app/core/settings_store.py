"""Настройки, которые админ меняет на лету (наценка, курс, лимиты). Хранятся в БД, кэш в Redis."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Setting
from app.redis_client import redis

CACHE_PREFIX = "tayzo:setting:"
CACHE_TTL = 60

# Значения по умолчанию. Всё, что админ не трогал, берётся отсюда.
DEFAULTS: dict[str, str] = {
    "markup_percent": "15",            # наценка над себестоимостью
    "ton_rate_uzs": "70000",           # курс TON → UZS (обновляется воркером)
    "star_price_ton": "0.0055",        # себестоимость 1 звезды в TON (обновляется воркером)
    "premium_3_ton": "3.9",            # себестоимость Premium в TON
    "premium_6_ton": "5.2",
    "premium_12_ton": "9.4",
    "star_price_uzs_override": "0",    # если >0 — фиксированная цена звезды в UZS, игнорирует курс
    "min_stars": "50",
    "max_stars": "100000",
    "min_topup": "5000",
    "max_topup": "10000000",
    "referral_percent": "5",           # % от пополнений реферала
    "maintenance": "0",                # 1 — бот закрыт на техработы
    "low_ton_alert": "2",              # алерт админу, если на кошельке меньше TON
    "stars_enabled": "1",
    "premium_enabled": "1",
}

DESCRIPTIONS: dict[str, str] = {
    "markup_percent": "Наценка, %",
    "ton_rate_uzs": "Курс TON → UZS",
    "star_price_ton": "Себестоимость 1 ⭐ в TON",
    "premium_3_ton": "Себестоимость Premium 3 мес (TON)",
    "premium_6_ton": "Себестоимость Premium 6 мес (TON)",
    "premium_12_ton": "Себестоимость Premium 12 мес (TON)",
    "star_price_uzs_override": "Фикс. цена 1 ⭐ в UZS (0 = авто)",
    "min_stars": "Мин. звёзд в заказе",
    "max_stars": "Макс. звёзд в заказе",
    "min_topup": "Мин. пополнение, UZS",
    "max_topup": "Макс. пополнение, UZS",
    "referral_percent": "Реферальный бонус, %",
    "maintenance": "Техработы (1/0)",
    "low_ton_alert": "Алерт при балансе TON ниже",
    "stars_enabled": "Продажа Stars (1/0)",
    "premium_enabled": "Продажа Premium (1/0)",
}


async def get(session: AsyncSession, key: str) -> str:
    cached = await redis.get(CACHE_PREFIX + key)
    if cached is not None:
        return cached
    row = await session.get(Setting, key)
    value = row.value if row else DEFAULTS.get(key, "")
    await redis.set(CACHE_PREFIX + key, value, ex=CACHE_TTL)
    return value


async def get_int(session: AsyncSession, key: str) -> int:
    return int(Decimal(await get(session, key)))


async def get_dec(session: AsyncSession, key: str) -> Decimal:
    return Decimal(await get(session, key))


async def get_bool(session: AsyncSession, key: str) -> bool:
    return (await get(session, key)).strip() in ("1", "true", "yes", "on")


async def set_value(session: AsyncSession, key: str, value: str) -> None:
    stmt = insert(Setting).values(key=key, value=value)
    stmt = stmt.on_conflict_do_update(index_elements=[Setting.key], set_={"value": value})
    await session.execute(stmt)
    await redis.delete(CACHE_PREFIX + key)


async def get_all(session: AsyncSession) -> dict[str, str]:
    rows = (await session.execute(select(Setting))).scalars().all()
    data = dict(DEFAULTS)
    data.update({r.key: r.value for r in rows})
    return data
