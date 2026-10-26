"""Настройки на лету: наценка, курс, лимиты, техработы."""
from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot.states import Admin
from app.core import pricing
from app.core import settings_store as cfg
from app.core.money import fmt_uzs
from app.db.models import AuditLog

router = Router(name="admin_settings")


async def settings_text(session: AsyncSession) -> str:
    each = await pricing.star_price_each(session)
    p3, p6, p12 = (await pricing.quote_premium(session, m) for m in (3, 6, 12))
    return (
        "⚙️ <b>Настройки</b>\n\n"
        f"Текущая цена для клиента: ⭐ <b>{fmt_uzs(each)}</b>/шт · "
        f"💎 3м {fmt_uzs(p3.price_uzs)} · 6м {fmt_uzs(p6.price_uzs)} · 12м {fmt_uzs(p12.price_uzs)}\n\n"
        "Нажми на параметр, чтобы изменить:"
    )


@router.callback_query(F.data == "adm:settings")
async def show_settings(call: CallbackQuery, session: AsyncSession, state: FSMContext):
    await state.clear()
    await call.answer()
    await call.message.edit_text(await settings_text(session), reply_markup=kb.settings_kb(await cfg.get_all(session)))


@router.callback_query(F.data.startswith("adm:set:"))
async def set_start(call: CallbackQuery, session: AsyncSession, state: FSMContext):
    key = call.data.split(":")[2]
    if key not in cfg.DEFAULTS:
        await call.answer("Неизвестный параметр", show_alert=True)
        return
    await state.set_state(Admin.set_value)
    await state.update_data(key=key)
    await call.answer()
    await call.message.answer(
        f"<b>{cfg.DESCRIPTIONS[key]}</b>\nТекущее: <code>{await cfg.get(session, key)}</code>\n\nВведи новое значение:",
        reply_markup=kb.admin_back_kb(),
    )


@router.message(Admin.set_value)
async def set_input(message: Message, session: AsyncSession, state: FSMContext):
    data = await state.get_data()
    key = data["key"]
    raw = (message.text or "").strip().replace(",", ".")
    try:
        Decimal(raw)
    except InvalidOperation:
        await message.answer("Нужно число. Попробуй ещё раз:")
        return
    await cfg.set_value(session, key, raw)
    session.add(AuditLog(admin_id=message.from_user.id, action="set_setting", details={"key": key, "value": raw}))
    await session.commit()
    await state.clear()
    await message.answer(f"✅ {cfg.DESCRIPTIONS[key]} = <code>{raw}</code>")
    await message.answer(await settings_text(session), reply_markup=kb.settings_kb(await cfg.get_all(session)))
