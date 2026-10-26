"""Настройки на лету: цены, наценка, курс, лимиты, переключатели.

Экраны: adm:settings (разделы) -> adm:sec:<код> (параметры раздела) -> adm:set:<ключ> (ввод значения)
Булевы параметры переключаются одной кнопкой: adm:toggle:<ключ>.
"""
from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot.states import Admin
from app.core import pricing
from app.core import settings_store as cfg
from app.core.money import fmt_uzs
from app.db.models import AuditLog

router = Router(name="admin_settings")

ON, OFF = "🟢", "⚪️"


def _section(code: str):
    return next((s for s in cfg.SECTIONS if s[0] == code), None)


def _fmt(key: str, value: str) -> str:
    if key in cfg.BOOL_KEYS:
        return "вкл" if value.strip() in ("1", "true", "yes", "on") else "выкл"
    if key.endswith("_uzs_override"):
        return "авто" if Decimal(value) == 0 else fmt_uzs(int(Decimal(value)))
    if key in ("min_topup", "max_topup", "ton_rate_uzs"):
        return fmt_uzs(int(Decimal(value)))
    if key.endswith("_percent"):
        return f"{value}%"
    return value


async def overview_text(session: AsyncSession) -> str:
    each = await pricing.star_price_each(session)
    p = [await pricing.quote_premium(session, m) for m in (3, 6, 12)]
    star_mode = "фикс." if await cfg.get_dec(session, "star_price_uzs_override") > 0 else "авто"
    rate = await cfg.get_dec(session, "ton_rate_uzs")
    markup = await cfg.get(session, "markup_percent")
    return (
        "⚙️ <b>Настройки</b>\n\n"
        f"⭐ 1 звезда для клиента: <b>{fmt_uzs(each)}</b> ({star_mode})\n"
        f"💎 Premium: 3м {fmt_uzs(p[0].price_uzs)} · 6м {fmt_uzs(p[1].price_uzs)} · 12м {fmt_uzs(p[2].price_uzs)}\n"
        f"📉 Курс TON: {fmt_uzs(int(rate))} · наценка {markup}%\n\n"
        "Выбери раздел:"
    )


def sections_kb():
    b = InlineKeyboardBuilder()
    for code, title, _ in cfg.SECTIONS:
        b.button(text=title, callback_data=f"adm:sec:{code}")
    b.button(text="◀️ Админка", callback_data="adm:menu")
    b.adjust(1)
    return b.as_markup()


async def section_kb(session: AsyncSession, code: str):
    _, _, keys = _section(code)
    data = await cfg.get_all(session)
    b = InlineKeyboardBuilder()
    for key in keys:
        if key in cfg.BOOL_KEYS:
            on = data[key].strip() in ("1", "true", "yes", "on")
            b.button(text=f"{ON if on else OFF} {cfg.DESCRIPTIONS[key]}", callback_data=f"adm:toggle:{key}")
        else:
            b.button(text=f"{cfg.DESCRIPTIONS[key]}: {_fmt(key, data[key])}", callback_data=f"adm:set:{key}")
    b.button(text="◀️ Разделы", callback_data="adm:settings")
    b.adjust(1)
    return b.as_markup()


async def section_text(session: AsyncSession, code: str) -> str:
    _, title, _ = _section(code)
    extra = ""
    if code == "prices":
        extra = "\nФикс. цена имеет приоритет. «Авто» = себестоимость × курс TON × (1 + наценка), округление до 100 сум."
    elif code == "toggles":
        extra = "\nНажми, чтобы переключить. Техработы закрывают бота для всех, кроме админов."
    return f"<b>{title}</b>{extra}\n\nНажми на параметр, чтобы изменить:"


# ---------- экраны ----------
@router.callback_query(F.data == "adm:settings")
async def show_sections(call: CallbackQuery, session: AsyncSession, state: FSMContext):
    await state.clear()
    await call.answer()
    await call.message.edit_text(await overview_text(session), reply_markup=sections_kb())


@router.callback_query(F.data.startswith("adm:sec:"))
async def show_section(call: CallbackQuery, session: AsyncSession, state: FSMContext):
    await state.clear()
    code = call.data.split(":")[2]
    if not _section(code):
        await call.answer("Нет такого раздела", show_alert=True)
        return
    await call.answer()
    await call.message.edit_text(await section_text(session, code), reply_markup=await section_kb(session, code))


@router.callback_query(F.data.startswith("adm:toggle:"))
async def toggle(call: CallbackQuery, session: AsyncSession):
    key = call.data.split(":")[2]
    if key not in cfg.BOOL_KEYS:
        await call.answer("Это не переключатель", show_alert=True)
        return
    new = "0" if await cfg.get_bool(session, key) else "1"
    await cfg.set_value(session, key, new)
    session.add(AuditLog(admin_id=call.from_user.id, action="set_setting", details={"key": key, "value": new}))
    await session.commit()
    await call.answer(f"{cfg.DESCRIPTIONS[key]}: {'вкл' if new == '1' else 'выкл'}")
    code = next(c for c, _, keys in cfg.SECTIONS if key in keys)
    await call.message.edit_reply_markup(reply_markup=await section_kb(session, code))


@router.callback_query(F.data.startswith("adm:set:"))
async def set_start(call: CallbackQuery, session: AsyncSession, state: FSMContext):
    key = call.data.split(":")[2]
    if key not in cfg.DEFAULTS or key in cfg.BOOL_KEYS:
        await call.answer("Неизвестный параметр", show_alert=True)
        return
    code = next(c for c, _, keys in cfg.SECTIONS if key in keys)
    await state.set_state(Admin.set_value)
    await state.update_data(key=key, section=code, msg_id=call.message.message_id)
    await call.answer()
    current = await cfg.get(session, key)
    hint = cfg.HINTS.get(key, "Введи новое значение (число).")
    b = InlineKeyboardBuilder()
    b.button(text="◀️ Отмена", callback_data=f"adm:sec:{code}")
    await call.message.edit_text(
        f"<b>{cfg.DESCRIPTIONS[key]}</b>\nСейчас: <code>{_fmt(key, current)}</code>\n\n{hint}\n\n✏️ Отправь значение сообщением:",
        reply_markup=b.as_markup(),
    )


@router.message(Admin.set_value)
async def set_input(message: Message, session: AsyncSession, state: FSMContext):
    data = await state.get_data()
    key, code = data["key"], data["section"]
    raw = (message.text or "").strip().replace(",", ".").replace(" ", "")
    try:
        value = Decimal(raw)
        if value < 0:
            raise InvalidOperation
    except InvalidOperation:
        await message.answer("Нужно число ≥ 0. Попробуй ещё раз или нажми «Отмена» выше.")
        return
    await cfg.set_value(session, key, raw)
    session.add(AuditLog(admin_id=message.from_user.id, action="set_setting", details={"key": key, "value": raw}))
    await session.commit()
    await state.clear()
    # убираем сообщение с вводом и обновляем экран раздела на месте
    try:
        await message.delete()
    except Exception:  # noqa: BLE001
        pass
    try:
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=data["msg_id"],
            text=f"✅ {cfg.DESCRIPTIONS[key]} → <b>{_fmt(key, raw)}</b>\n\n" + await section_text(session, code),
            reply_markup=await section_kb(session, code),
        )
    except Exception:  # noqa: BLE001 — если исходное сообщение недоступно, шлём новое
        await message.answer(await section_text(session, code), reply_markup=await section_kb(session, code))
