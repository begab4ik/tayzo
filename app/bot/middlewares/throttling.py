from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.redis_client import redis


class ThrottlingMiddleware(BaseMiddleware):
    """Не больше одного действия в `interval` сек от юзера — защита от спама кнопками."""

    def __init__(self, interval: float = 0.4):
        self.interval = interval

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None:
            return await handler(event, data)
        key = f"tayzo:thr:{tg_user.id}"
        if not await redis.set(key, "1", px=int(self.interval * 1000), nx=True):
            if isinstance(event, CallbackQuery):
                await event.answer("Не так быстро 🙂")
            elif isinstance(event, Message):
                pass
            return None
        return await handler(event, data)
