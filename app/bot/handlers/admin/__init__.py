from aiogram import Router
from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject

from app.config import settings


class IsAdmin(BaseFilter):
    async def __call__(self, event: TelegramObject, event_from_user=None) -> bool:
        return bool(event_from_user and settings.is_admin(event_from_user.id))


from app.bot.handlers.admin import broadcast, channels, orders, panel, promo, settings_h, stats, users  # noqa: E402

router = Router(name="admin")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())
router.include_routers(
    panel.router, stats.router, orders.router, users.router, settings_h.router, promo.router, channels.router, broadcast.router
)
