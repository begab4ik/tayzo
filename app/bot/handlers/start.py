from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot import keyboards as kb
from app.bot import texts
from app.db.models import User

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, user: User, is_admin: bool, state: FSMContext):
    await state.clear()
    await message.answer(texts.welcome(user.first_name), reply_markup=kb.main_menu(is_admin))


@router.message(Command("menu"))
@router.message(Command("cancel"))
async def cmd_menu(message: Message, is_admin: bool, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню 👇", reply_markup=kb.main_menu(is_admin))


@router.callback_query(F.data == "menu")
async def cb_menu(call: CallbackQuery, is_admin: bool, state: FSMContext):
    """«Отмена» / «Назад» из любого inline-экрана: закрываем экран на месте, меню снизу уже есть."""
    await state.clear()
    await call.answer()
    try:
        await call.message.edit_text("↩️ Отменено. Выбери действие в меню ниже 👇")
    except Exception:  # noqa: BLE001 — сообщение без текста (фото) или уже изменено
        await call.message.answer("Выбери действие в меню ниже 👇", reply_markup=kb.main_menu(is_admin))


@router.message(F.text == kb.BTN_FAQ)
async def faq(message: Message):
    await message.answer(texts.faq())


@router.message(F.text == kb.BTN_SUPPORT)
@router.message(Command("support"))
async def support(message: Message):
    await message.answer(texts.support())
