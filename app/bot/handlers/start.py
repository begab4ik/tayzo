import re

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot import texts
from app.bot.i18n import LANGS, t
from app.db.models import User

router = Router(name="start")


DEEP_RE = re.compile(r"^(stars|premium|site)(?:_(\w+?))?(?:_(ru|uz|en))?$")


def parse_deep_link(arg: str | None) -> tuple[str | None, str | None, str | None]:
    """Параметр start с сайта: stars_250_ru / premium_6_uz / site_hero_en → (раздел, значение, язык)."""
    m = DEEP_RE.match((arg or "").strip().lower())
    if not m:
        return None, None, None
    section, value, lang = m.groups()
    if section == "stars" and value and not value.isdigit():
        value = None
    if section == "premium" and value and not value.isdigit():
        value = None
    return section, value, lang


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, session: AsyncSession, user: User, is_admin: bool, state: FSMContext):
    await state.clear()
    section, value, lang = parse_deep_link(command.args)
    if lang and not user.lang_chosen:
        # пришёл с сайта — язык уже выбран там, не спрашиваем второй раз
        user.language = lang
        user.lang_chosen = True
        await session.commit()
    if not user.lang_chosen:
        await message.answer(t(user.language, "choose_lang"), reply_markup=kb.lang_kb())
        return
    await message.answer(texts.welcome(user.language, user.first_name), reply_markup=kb.main_menu(user.language, is_admin))
    if section == "stars":
        from app.bot.handlers.stars import stars_start

        await stars_start(message, session, user, state, preset_qty=int(value) if value else None)
    elif section == "premium":
        from app.bot.handlers.premium import premium_start

        await premium_start(message, session, user, state)


@router.message(F.text.in_(kb.L("btn_lang")))
@router.message(Command("lang", "language"))
async def change_lang(message: Message, user: User):
    await message.answer(t(user.language, "choose_lang"), reply_markup=kb.lang_kb())


@router.callback_query(F.data.startswith("lang:"))
async def set_lang(call: CallbackQuery, session: AsyncSession, user: User, is_admin: bool, state: FSMContext):
    code = call.data.split(":")[1]
    if code not in LANGS:
        await call.answer()
        return
    first_time = not user.lang_chosen
    user.language = code
    user.lang_chosen = True
    await session.commit()
    await state.clear()
    await call.answer(t(code, "lang_set"))
    try:
        await call.message.edit_text(t(code, "lang_set"))
    except Exception:  # noqa: BLE001
        pass
    text = texts.welcome(code, user.first_name) if first_time else t(code, "menu_hint")
    await call.message.answer(text, reply_markup=kb.main_menu(code, is_admin))


@router.message(Command("menu", "cancel"))
async def cmd_menu(message: Message, user: User, is_admin: bool, state: FSMContext):
    await state.clear()
    await message.answer(t(user.language, "menu_hint"), reply_markup=kb.main_menu(user.language, is_admin))


@router.callback_query(F.data == "menu")
async def cb_menu(call: CallbackQuery, user: User, is_admin: bool, state: FSMContext):
    """«Отмена» / «Назад» из любого inline-экрана: закрываем экран на месте, меню снизу уже есть."""
    await state.clear()
    await call.answer()
    try:
        await call.message.edit_text(t(user.language, "cancelled"))
    except Exception:  # noqa: BLE001
        await call.message.answer(t(user.language, "menu_hint"), reply_markup=kb.main_menu(user.language, is_admin))


@router.message(F.text.in_(kb.L("btn_faq")))
async def faq(message: Message, user: User):
    await message.answer(texts.faq(user.language))


@router.message(F.text.in_(kb.L("btn_support")))
@router.message(Command("support"))
async def support(message: Message, user: User):
    await message.answer(texts.support(user.language))
