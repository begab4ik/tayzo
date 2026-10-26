"""Рассылка всем пользователям (копирует сообщение админа: текст, фото, кнопки сохраняются)."""
import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot.states import Admin
from app.db.models import User

router = Router(name="admin_broadcast")
log = logging.getLogger(__name__)


@router.callback_query(F.data == "adm:broadcast")
async def bc_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(Admin.broadcast)
    await call.answer()
    await call.message.edit_text("📣 Отправь сообщение для рассылки (текст/фото/видео — как есть):", reply_markup=kb.admin_back_kb())


@router.message(Admin.broadcast)
async def bc_preview(message: Message, state: FSMContext):
    await state.update_data(chat_id=message.chat.id, message_id=message.message_id)
    await message.answer("Так увидят пользователи ☝️ Отправляем?", reply_markup=kb.broadcast_confirm_kb())


@router.callback_query(F.data == "adm:bc:go")
async def bc_go(call: CallbackQuery, bot: Bot, session: AsyncSession, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    if "message_id" not in data:
        await call.answer("Сообщение не найдено", show_alert=True)
        return
    await call.answer()
    ids = list((await session.execute(select(User.id).where(User.is_banned.is_(False)))).scalars())
    status = await call.message.edit_text(f"🚀 Рассылка запущена: 0 / {len(ids)}")
    asyncio.create_task(_run(bot, data["chat_id"], data["message_id"], ids, status))


async def _run(bot: Bot, from_chat: int, message_id: int, ids: list[int], status: Message):
    sent = failed = 0
    for i, uid in enumerate(ids, 1):
        try:
            await bot.copy_message(uid, from_chat, message_id)
            sent += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            try:
                await bot.copy_message(uid, from_chat, message_id)
                sent += 1
            except Exception:  # noqa: BLE001
                failed += 1
        except TelegramForbiddenError:
            failed += 1
        except Exception as e:  # noqa: BLE001
            failed += 1
            log.debug("broadcast to %s: %s", uid, e)
        await asyncio.sleep(0.05)  # ~20 msg/s — лимит Telegram ~30/s
        if i % 50 == 0:
            try:
                await status.edit_text(f"🚀 Рассылка: {i} / {len(ids)} · ✅ {sent} · ❌ {failed}")
            except Exception:  # noqa: BLE001
                pass
    try:
        await status.edit_text(f"✅ Рассылка завершена: доставлено {sent}, не доставлено {failed}", reply_markup=kb.admin_back_kb())
    except Exception:  # noqa: BLE001
        pass
