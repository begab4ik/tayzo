from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.bot import texts
from app.config import settings
from app.core import referrals
from app.core import settings_store as cfg
from app.db.models import User


class UserMiddleware(BaseMiddleware):
    """Создаёт/обновляет пользователя, прокидывает `user` в хендлер, режет забаненных и техработы."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)

        session = data["session"]
        user = await session.get(User, tg_user.id)
        if user is None:
            referrer_id = None
            if isinstance(event, Message) and event.text and event.text.startswith("/start"):
                parts = event.text.split(maxsplit=1)
                referrer_id = referrals.parse_ref(parts[1] if len(parts) > 1 else None)
                if referrer_id == tg_user.id or (referrer_id and await session.get(User, referrer_id) is None):
                    referrer_id = None
            user = User(
                id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                language=(tg_user.language_code or "ru")[:2] if (tg_user.language_code or "ru")[:2] in ("ru", "en", "uz") else "ru",
                referrer_id=referrer_id,
            )
            session.add(user)
            await session.flush()
        else:
            if user.username != tg_user.username or user.first_name != tg_user.first_name:
                user.username = tg_user.username
                user.first_name = tg_user.first_name

        data["user"] = user
        data["is_admin"] = settings.is_admin(user.id)

        if user.is_banned and not data["is_admin"]:
            await _reply(event, texts.banned(user.language))
            return None
        if not data["is_admin"] and await cfg.get_bool(session, "maintenance"):
            await _reply(event, texts.maintenance(user.language))
            return None

        return await handler(event, data)


async def _reply(event: TelegramObject, text: str) -> None:
    if isinstance(event, Message):
        await event.answer(text)
    elif isinstance(event, CallbackQuery):
        await event.answer(text, show_alert=True)
