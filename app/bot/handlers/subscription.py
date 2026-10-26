from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot.middlewares.subscription import get_channels, is_subscribed
from app.db.models import User

router = Router(name="subscription")


@router.callback_query(F.data == "check_sub")
async def check_sub(call: CallbackQuery, bot: Bot, session: AsyncSession, user: User, is_admin: bool):
    channels = await get_channels(session)
    missing = await is_subscribed(bot, user.id, channels, force=True)
    if missing:
        await call.answer("Подписка не найдена. Подпишись и нажми ещё раз.", show_alert=True)
        return
    await call.answer("Спасибо за подписку! 💛")
    try:
        await call.message.edit_text("✅ Подписка подтверждена, доступ открыт.")
    except Exception:  # noqa: BLE001
        pass
    await call.message.answer("Выбирай, что нужно 👇", reply_markup=kb.main_menu(is_admin))
