"""Админка → 🎁 Подарки: вход в Telegram-аккаунт владельца (MTProto), статус, баланс звёзд, обновление каталога."""
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot.states import Admin
from app.core import settings_store as cfg
from app.core.exceptions import ProviderAuthError, ProviderError
from app.providers.telegram_account import tg_account

router = Router(name="admin_gifts")


def gifts_kb(connected: bool):
    b = InlineKeyboardBuilder()
    if connected:
        b.button(text="🔄 Обновить каталог", callback_data="adm:gifts:refresh")
        b.button(text="⚙️ Настройки подарков", callback_data="adm:sec:gifts")
        b.button(text="🚪 Выйти из аккаунта", callback_data="adm:gifts:logout")
    else:
        b.button(text="🔑 Войти в аккаунт", callback_data="adm:gifts:login")
    b.button(text="◀️ Админка", callback_data="adm:menu")
    b.adjust(1)
    return b.as_markup()


async def status_text(session: AsyncSession) -> tuple[str, bool]:
    if not tg_account.configured:
        return ("🎁 <b>Подарки</b>\n\n❌ В <code>tokens.env</code> не заданы <code>TG_API_ID</code> и <code>TG_API_HASH</code> "
                "(my.telegram.org → API development tools). Добавь и перезапусти бота."), False
    if not await cfg.get(session, "tg_session"):
        return ("🎁 <b>Подарки</b>\n\nАккаунт не подключён. Нажми «Войти» — понадобится номер телефона, код из Telegram "
                "и пароль 2FA (если включён). Подарки будут отправляться <b>с этого аккаунта анонимно</b>, звёзды на него "
                "бот докупает сам через Fragment."), False
    try:
        me = await tg_account.me()
        bal = await tg_account.star_balance()
        gifts = await tg_account.gifts()
        enabled = await cfg.get_bool(session, "gifts_enabled")
        return (f"🎁 <b>Подарки</b>\n\n✅ Аккаунт: <b>{me['name']}</b> @{me['username'] or '—'}\n"
                f"⭐ Звёзд на аккаунте: <b>{bal}</b>\n🗂 Подарков в каталоге: <b>{len(gifts)}</b>\n"
                f"Продажа: {'включена' if enabled else 'выключена'}\n\n"
                "Если звёзд не хватает на подарок, бот докупит их через Fragment перед отправкой."), True
    except ProviderAuthError as e:
        return f"🎁 <b>Подарки</b>\n\n⚠️ {e}", False
    except Exception as e:  # noqa: BLE001
        return f"🎁 <b>Подарки</b>\n\n⚠️ Ошибка: <code>{e}</code>", True


@router.callback_query(F.data == "adm:gifts")
async def gifts_menu(call: CallbackQuery, session: AsyncSession, state: FSMContext):
    await state.clear()
    await call.answer()
    text, ok = await status_text(session)
    await call.message.edit_text(text, reply_markup=gifts_kb(ok))


@router.callback_query(F.data == "adm:gifts:refresh")
async def gifts_refresh(call: CallbackQuery, session: AsyncSession):
    await call.answer("Обновляю…")
    try:
        gifts = await tg_account.fetch_gifts()
        await call.answer(f"Каталог обновлён: {len(gifts)} подарков", show_alert=True)
    except Exception as e:  # noqa: BLE001
        await call.answer(f"Ошибка: {e}"[:190], show_alert=True)
    text, ok = await status_text(session)
    await call.message.edit_text(text, reply_markup=gifts_kb(ok))


@router.callback_query(F.data == "adm:gifts:logout")
async def gifts_logout(call: CallbackQuery, session: AsyncSession):
    await tg_account.logout()
    await call.answer("Сессия удалена")
    text, ok = await status_text(session)
    await call.message.edit_text(text, reply_markup=gifts_kb(ok))


@router.callback_query(F.data == "adm:gifts:login")
async def login_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(Admin.tg_phone)
    await call.answer()
    await call.message.edit_text("Введи номер телефона аккаунта в формате <code>+998901234567</code>:", reply_markup=kb.admin_back_kb())


@router.message(Admin.tg_phone)
async def login_phone(message: Message, state: FSMContext):
    phone = (message.text or "").strip().replace(" ", "")
    if not phone.startswith("+") or not phone[1:].isdigit():
        await message.answer("Нужен номер вида <code>+998901234567</code>")
        return
    try:
        await tg_account.login_start(message.from_user.id, phone)
    except Exception as e:  # noqa: BLE001
        await message.answer(f"Не удалось отправить код: <code>{e}</code>", reply_markup=kb.admin_back_kb())
        return
    await state.set_state(Admin.tg_code)
    await message.answer("Telegram прислал код в приложение (или SMS). Введи его <b>с пробелами между цифрами</b>, например <code>1 2 3 4 5</code> — иначе Telegram аннулирует код.", reply_markup=kb.admin_back_kb())


@router.message(Admin.tg_code)
async def login_code(message: Message, state: FSMContext):
    code = (message.text or "").strip()
    try:
        done = await tg_account.login_code(message.from_user.id, code)
    except KeyError:
        await state.clear()
        await message.answer("Сессия входа потеряна (бот перезапускался). Начни заново: Админка → 🎁 Подарки.", reply_markup=kb.admin_back_kb())
        return
    except Exception as e:  # noqa: BLE001
        await message.answer(f"Код не подошёл: <code>{e}</code>. Попробуй ещё раз:", reply_markup=kb.admin_back_kb())
        return
    if not done:
        await state.set_state(Admin.tg_password)
        await message.answer("Включена двухэтапная защита. Введи пароль 2FA (сообщение удалю):", reply_markup=kb.admin_back_kb())
        return
    await state.clear()
    await message.answer("✅ Аккаунт подключён. Загружаю каталог подарков…")
    await _after_login(message)


@router.message(Admin.tg_password)
async def login_password(message: Message, state: FSMContext):
    pw = message.text or ""
    try:
        await message.delete()
    except Exception:  # noqa: BLE001
        pass
    try:
        await tg_account.login_password(message.from_user.id, pw)
    except KeyError:
        await state.clear()
        await message.answer("Сессия входа потеряна. Начни заново: Админка → 🎁 Подарки.", reply_markup=kb.admin_back_kb())
        return
    except Exception as e:  # noqa: BLE001
        await message.answer(f"Пароль не подошёл: <code>{e}</code>. Ещё раз:", reply_markup=kb.admin_back_kb())
        return
    await state.clear()
    await message.answer("✅ Аккаунт подключён. Загружаю каталог подарков…")
    await _after_login(message)


async def _after_login(message: Message):
    try:
        gifts = await tg_account.fetch_gifts()
        bal = await tg_account.star_balance()
        me = await tg_account.me()
        await message.answer(f"🎁 @{me['username']}: {bal} ⭐ на аккаунте, {len(gifts)} подарков в каталоге.", reply_markup=gifts_kb(True))
    except (ProviderError, ProviderAuthError, Exception) as e:  # noqa: BLE001
        await message.answer(f"Аккаунт подключён, но каталог не загрузился: <code>{e}</code>", reply_markup=gifts_kb(True))
