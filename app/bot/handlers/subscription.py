from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot.i18n import t
from app.bot.middlewares.subscription import get_channels, is_subscribed
from app.db.models import User

router = Router(name="subscription")


@router.callback_query(F.data == "check_sub")
async def check_sub(call: CallbackQuery, bot: Bot, session: AsyncSession, user: User, is_admin: bool):
    channels = await get_channels(session)
    missing = await is_subscribed(bot, user.id, channels, force=True)
    if missing:
        await call.answer(t(user.language, "sub_not_found"), show_alert=True)
        return
    await call.answer(t(user.language, "sub_thanks"))
    try:
        await call.message.edit_text(t(user.language, "sub_ok"))
    except Exception:  # noqa: BLE001
        pass
    await call.message.answer(t(user.language, "menu_hint"), reply_markup=kb.main_menu(user.language, is_admin))
