from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot import texts
from app.bot.i18n import LANGS, t
from app.db.models import User

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, user: User, is_admin: bool, state: FSMContext):
    await state.clear()
    if not user.lang_chosen:
        await message.answer(t(user.language, "choose_lang"), reply_markup=kb.lang_kb())
        return
    await message.answer(texts.welcome(user.language, user.first_name), reply_markup=kb.main_menu(user.language, is_admin))


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
