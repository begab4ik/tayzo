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
    "premium_3_ton": "10.21",          # себестоимость Premium в TON (обновляется воркером по Fragment)
    "premium_6_ton": "13.61",
    "premium_12_ton": "24.60",
    "premium_probe_username": "b3gabb",  # username БЕЗ Premium, по которому воркер узнаёт цену на Fragment
    "star_price_uzs_override": "0",    # если >0 — фиксированная цена звезды в UZS, игнорирует курс
    "premium_3_uzs_override": "0",     # если >0 — фиксированная цена Premium в UZS
    "premium_6_uzs_override": "0",
    "premium_12_uzs_override": "0",
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
    "premium_probe_username": "Username для проверки цены Premium",
    "star_price_uzs_override": "Цена 1 ⭐, сум (0 = авто по курсу)",
    "markup_percent": "Наценка, %",
    "ton_rate_uzs": "Курс TON → сум",
    "star_price_ton": "Себестоимость 1 ⭐, TON",
    "premium_3_uzs_override": "Premium 3 мес, сум (0 = авто)",
    "premium_6_uzs_override": "Premium 6 мес, сум (0 = авто)",
    "premium_12_uzs_override": "Premium 12 мес, сум (0 = авто)",
    "premium_3_ton": "Себестоимость Premium 3 мес, TON",
    "premium_6_ton": "Себестоимость Premium 6 мес, TON",
    "premium_12_ton": "Себестоимость Premium 12 мес, TON",
    "min_stars": "Мин. звёзд в заказе",
    "max_stars": "Макс. звёзд в заказе",
    "min_topup": "Мин. пополнение, сум",
    "max_topup": "Макс. пополнение, сум",
    "referral_percent": "Реферальный бонус, %",
    "low_ton_alert": "Алерт, если TON меньше",
    "maintenance": "Техработы",
    "stars_enabled": "Продажа Stars",
    "premium_enabled": "Продажа Premium",
}

# Разделы меню настроек в админке: (код, заголовок, ключи)
SECTIONS: list[tuple[str, str, list[str]]] = [
    ("prices", "💰 Цены", ["star_price_uzs_override", "markup_percent", "premium_3_uzs_override", "premium_6_uzs_override", "premium_12_uzs_override"]),
    ("cost", "📉 Курс и себестоимость", ["ton_rate_uzs", "star_price_ton", "premium_3_ton", "premium_6_ton", "premium_12_ton", "premium_probe_username", "low_ton_alert"]),
    ("limits", "📏 Лимиты", ["min_stars", "max_stars", "min_topup", "max_topup"]),
    ("refs", "👥 Рефералы", ["referral_percent"]),
    ("toggles", "🔘 Переключатели", ["stars_enabled", "premium_enabled", "maintenance"]),
]
BOOL_KEYS = {"maintenance", "stars_enabled", "premium_enabled"}

# Подсказки при вводе значения
HINTS: dict[str, str] = {
    "premium_probe_username": "Любой username <b>без</b> Premium (например, запасной аккаунт). По нему бот раз в час узнаёт у Fragment себестоимость Premium. Пусто — не обновлять.",
    "star_price_uzs_override": "Введи цену одной звезды в сумах, например <code>450</code>.\n<code>0</code> — считать автоматически: себестоимость × курс × наценка.",
    "markup_percent": "Процент сверх себестоимости, например <code>15</code>. Применяется, когда цена считается автоматически.",
    "ton_rate_uzs": "Курс 1 TON в сумах. Обновляется сам каждые 10 минут — ручное значение перезапишется.",
    "star_price_ton": "Сколько TON стоит 1 звезда на Fragment. Обновляется сам раз в час.",
    "min_topup": "Минимальная сумма пополнения через Click, сум.",
    "referral_percent": "Сколько % от каждого пополнения реферала начислять пригласившему.",
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
