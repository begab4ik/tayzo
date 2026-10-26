"""Обязательная подписка на канал(ы) проекта.

Каналы берутся из таблицы required_channels (управляются из админки), при первом запуске
туда добавляется канал из .env. Результат проверки кэшируется в Redis на 5 минут,
чтобы не дёргать getChatMember на каждое нажатие.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot import texts
from app.db.models import RequiredChannel
from app.redis_client import redis

log = logging.getLogger(__name__)

CACHE_TTL = 300
OK_STATUSES = {"member", "administrator", "creator"}


async def get_channels(session: AsyncSession) -> list[RequiredChannel]:
    q = select(RequiredChannel).where(RequiredChannel.is_active.is_(True))
    return list((await session.execute(q)).scalars())


async def is_subscribed(bot: Bot, user_id: int, channels: list[RequiredChannel], force: bool = False) -> list[RequiredChannel]:
    """Возвращает список каналов, на которые юзер НЕ подписан."""
    missing: list[RequiredChannel] = []
    for ch in channels:
        key = f"tayzo:sub:{user_id}:{ch.chat_id}"
        if not force and await redis.get(key) == "1":
            continue
        try:
            member = await bot.get_chat_member(ch.chat_id, user_id)
            ok = member.status in OK_STATUSES
        except (TelegramBadRequest, TelegramForbiddenError) as e:
            # бот не админ канала / канал недоступен — не блокируем юзера, но пишем в лог
            log.warning("get_chat_member(%s) failed: %s", ch.chat_id, e)
            ok = True
        if ok:
            await redis.set(key, "1", ex=CACHE_TTL)
        else:
            missing.append(ch)
    return missing


class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("user")
        if user is None or data.get("is_admin"):
            return await handler(event, data)

        # Кнопку «Проверить» всегда пропускаем — её обрабатывает handlers/subscription.py
        if isinstance(event, CallbackQuery) and event.data == "check_sub":
            return await handler(event, data)

        channels = await get_channels(data["session"])
        if not channels:
            return await handler(event, data)

        missing = await is_subscribed(data["bot"], user.id, channels)
        if not missing:
            return await handler(event, data)

        markup = kb.subscribe_kb(missing)
        if isinstance(event, Message):
            await event.answer(texts.subscribe_required(), reply_markup=markup)
        elif isinstance(event, CallbackQuery):
            await event.answer()
            if event.message:
                await event.message.answer(texts.subscribe_required(), reply_markup=markup)
        return None
