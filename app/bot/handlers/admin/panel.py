from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.config import settings
from app.core import stats as stats_svc
from app.core.money import fmt_uzs
from app.providers.registry import is_manual_mode

router = Router(name="admin_panel")


async def panel_text(session: AsyncSession) -> str:
    t = await stats_svc.totals(session)
    mode = "🟠 ручной (Fragment не настроен)" if is_manual_mode() else "🟢 авто (Fragment)"
    click = "🟢" if settings.click_configured else "🔴 не настроен"
    return (
        "🛠 <b>Админ-панель Tayzo</b>\n\n"
        f"Пользователей: <b>{t['users']}</b>\n"
        f"Сумма балансов (обязательства): <b>{fmt_uzs(t['balances'])}</b>\n"
        f"Режим выполнения: {mode}\n"
        f"Click: {click}"
    )


@router.message(Command("admin"))
@router.message(F.text == kb.BTN_ADMIN)
async def admin_menu(message: Message, session: AsyncSession, state: FSMContext):
    await state.clear()
    await message.answer(await panel_text(session), reply_markup=kb.admin_menu_kb())


@router.callback_query(F.data == "adm:menu")
async def admin_menu_cb(call: CallbackQuery, session: AsyncSession, state: FSMContext):
    await state.clear()
    await call.answer()
    await call.message.edit_text(await panel_text(session), reply_markup=kb.admin_menu_kb())


@router.callback_query(F.data == "adm:ton")
async def ton_info(call: CallbackQuery):
    await call.answer()
    if is_manual_mode():
        await call.message.edit_text("TON-кошелёк не настроен (ручной режим). Заполни TON_MNEMONIC и Fragment cookies в .env.", reply_markup=kb.admin_back_kb())
        return
    from app.providers.ton_wallet import ton_wallet

    try:
        bal = await ton_wallet.balance()
        text = f"💎 <b>TON кошелёк</b>\n\nАдрес: <code>{ton_wallet.address}</code>\nБаланс: <b>{bal:.3f} TON</b>"
    except Exception as e:  # noqa: BLE001
        text = f"❌ Ошибка кошелька: <code>{e}</code>"
    await call.message.edit_text(text, reply_markup=kb.admin_back_kb())
