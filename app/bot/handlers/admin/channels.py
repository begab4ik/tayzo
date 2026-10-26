"""Управление каналами обязательной подписки."""
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot.states import Admin
from app.db.models import RequiredChannel

router = Router(name="admin_channels")


def channels_kb(rows: list[RequiredChannel]):
    b = InlineKeyboardBuilder()
    for ch in rows:
        b.button(text=f"{'🟢' if ch.is_active else '⚪️'} {ch.title}", callback_data=f"adm:ch:toggle:{ch.id}")
        b.button(text="🗑", callback_data=f"adm:ch:del:{ch.id}")
    b.button(text="➕ Добавить канал", callback_data="adm:ch:add")
    b.button(text="◀️ Админка", callback_data="adm:menu")
    b.adjust(*([2] * len(rows)), 1, 1)
    return b.as_markup()


async def render(session: AsyncSession):
    rows = list((await session.execute(select(RequiredChannel).order_by(RequiredChannel.id))).scalars())
    text = "📢 <b>Обязательная подписка</b>\n\nКаналы (🟢 активен / ⚪️ выключен). Бот должен быть админом канала."
    return text, channels_kb(rows)


@router.callback_query(F.data == "adm:channels")
async def channels_menu(call: CallbackQuery, session: AsyncSession, state: FSMContext):
    await state.clear()
    text, markup = await render(session)
    await call.answer()
    await call.message.edit_text(text, reply_markup=markup)


@router.callback_query(F.data == "adm:ch:add")
async def add_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(Admin.add_channel)
    await call.answer()
    await call.message.edit_text(
        "Перешли сюда любой пост из канала или отправь <code>@username</code> / ID канала.\nБот уже должен быть добавлен в админы канала.",
        reply_markup=kb.admin_back_kb(),
    )


@router.message(Admin.add_channel)
async def add_input(message: Message, bot: Bot, session: AsyncSession, state: FSMContext):
    ref: str | int | None = None
    if message.forward_from_chat:
        ref = message.forward_from_chat.id
    else:
        raw = (message.text or "").strip()
        ref = int(raw) if raw.lstrip("-").isdigit() else raw
    try:
        chat = await bot.get_chat(ref)
        me = await bot.get_chat_member(chat.id, (await bot.me()).id)
        if me.status not in ("administrator", "creator"):
            await message.answer("❌ Бот не админ в этом канале. Добавь и повтори.")
            return
    except Exception as e:  # noqa: BLE001
        await message.answer(f"❌ Не удалось получить канал: {e}")
        return
    url = f"https://t.me/{chat.username}" if chat.username else (chat.invite_link or "")
    if not url:
        try:
            url = await bot.export_chat_invite_link(chat.id)
        except Exception:  # noqa: BLE001
            await message.answer("❌ У канала нет публичной ссылки, а создать invite-ссылку не удалось.")
            return
    existing = (await session.execute(select(RequiredChannel).where(RequiredChannel.chat_id == chat.id))).scalar_one_or_none()
    if existing:
        existing.title, existing.url, existing.is_active = chat.title or str(chat.id), url, True
    else:
        session.add(RequiredChannel(chat_id=chat.id, title=chat.title or str(chat.id), url=url))
    await session.commit()
    await state.clear()
    text, markup = await render(session)
    await message.answer(f"✅ Канал «{chat.title}» добавлен.\n\n" + text, reply_markup=markup)


@router.callback_query(F.data.startswith("adm:ch:toggle:"))
async def toggle(call: CallbackQuery, session: AsyncSession):
    ch = await session.get(RequiredChannel, int(call.data.split(":")[3]))
    if ch:
        ch.is_active = not ch.is_active
        await session.commit()
    text, markup = await render(session)
    await call.answer()
    await call.message.edit_text(text, reply_markup=markup)


@router.callback_query(F.data.startswith("adm:ch:del:"))
async def delete(call: CallbackQuery, session: AsyncSession):
    ch = await session.get(RequiredChannel, int(call.data.split(":")[3]))
    if ch:
        await session.delete(ch)
        await session.commit()
    text, markup = await render(session)
    await call.answer("Удалён")
    await call.message.edit_text(text, reply_markup=markup)
