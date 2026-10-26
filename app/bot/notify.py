import logging

from aiogram.types import InlineKeyboardMarkup

from app.bot.loader import bot
from app.config import settings

log = logging.getLogger(__name__)


async def notify_admins(text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    targets = {settings.admin_notify_chat_id} if settings.admin_notify_chat_id else set(settings.admin_ids)
    for chat_id in targets:
        try:
            await bot.send_message(chat_id, text, reply_markup=reply_markup, disable_web_page_preview=True)
        except Exception as e:  # noqa: BLE001
            log.warning("notify admin %s failed: %s", chat_id, e)


async def notify_user(user_id: int, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> bool:
    try:
        await bot.send_message(user_id, text, reply_markup=reply_markup, disable_web_page_preview=True)
        return True
    except Exception as e:  # noqa: BLE001
        log.info("notify user %s failed: %s", user_id, e)
        return False
