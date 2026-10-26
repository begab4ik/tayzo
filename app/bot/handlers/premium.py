"""Покупка Premium: срок -> получатель -> подтверждение -> заказ."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot import texts
from app.bot.handlers.stars import USERNAME_RE
from app.bot.notify import notify_admins
from app.bot.states import BuyPremium
from app.core import orders, pricing
from app.core import settings_store as cfg
from app.core.enums import ProductType
from app.core.exceptions import InsufficientBalance, ProviderError, RecipientNotFound
from app.core.money import fmt_uzs
from app.db.models import User
from app.providers.base import Recipient
from app.providers.registry import get_provider, is_manual_mode

router = Router(name="premium")


@router.message(F.text == kb.BTN_PREMIUM)
async def premium_start(message: Message, session: AsyncSession, state: FSMContext):
    await state.clear()
    if not await cfg.get_bool(session, "premium_enabled"):
        await message.answer("💎 Продажа Premium временно приостановлена.")
        return
    prices = {m: (await pricing.quote_premium(session, m)).price_uzs for m in pricing.PREMIUM_MONTHS}
    await message.answer(texts.premium_intro(), reply_markup=kb.premium_kb(prices))


@router.callback_query(F.data.startswith("prem:"))
async def pick_months(call: CallbackQuery, user: User, state: FSMContext):
    months = int(call.data.split(":")[1])
    await state.set_state(BuyPremium.recipient)
    await state.update_data(months=months)
    await call.answer()
    await call.message.edit_text(f"💎 Premium на <b>{months} мес.</b>\n\nКому оформить?", reply_markup=kb.recipient_kb(bool(user.username)))


@router.callback_query(BuyPremium.recipient, F.data == "rcp:self")
async def rcp_self(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    await call.answer()
    await _resolve_and_confirm(call.message, session, user, state, user.username or "", edit=True)


@router.callback_query(BuyPremium.recipient, F.data == "rcp:other")
async def rcp_other(call: CallbackQuery):
    await call.answer()
    await call.message.edit_text(texts.ask_username(), reply_markup=kb.cancel_kb())


@router.message(BuyPremium.recipient)
async def rcp_input(message: Message, session: AsyncSession, user: User, state: FSMContext):
    m = USERNAME_RE.match((message.text or "").strip())
    if not m:
        await message.answer("Неверный формат. Пример: <code>@durov</code>", reply_markup=kb.cancel_kb())
        return
    await _resolve_and_confirm(message, session, user, state, m.group(1), edit=False)


async def _resolve_and_confirm(message: Message, session: AsyncSession, user: User, state: FSMContext, username: str, edit: bool):
    data = await state.get_data()
    months = int(data["months"])
    send = message.edit_text if edit else message.answer
    try:
        rcp = await get_provider(ProductType.PREMIUM).resolve_recipient(username, months)
    except RecipientNotFound as e:
        await send(f"❌ {e.message}", reply_markup=kb.cancel_kb())
        return
    except ProviderError as e:
        await send("⚠️ Не удалось проверить получателя, попробуй через минуту.", reply_markup=kb.cancel_kb())
        await notify_admins(f"⚠️ Fragment resolve error: {e.message}")
        return
    quote = await pricing.quote_premium(session, months)
    await state.update_data(rcp_username=rcp.username, rcp_name=rcp.name, rcp_token=rcp.token, price=quote.price_uzs)
    await state.set_state(BuyPremium.confirm)
    text = texts.confirm_order(f"💎 Premium {months} мес.", rcp.name, rcp.username, quote.price_uzs, user.balance)
    await send(text, reply_markup=kb.confirm_kb(user.balance >= quote.price_uzs, quote.price_uzs - user.balance))


@router.callback_query(BuyPremium.confirm, F.data == "order:confirm")
async def confirm(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    data = await state.get_data()
    months = int(data["months"])
    quote = await pricing.quote_premium(session, months)
    rcp = Recipient(username=data["rcp_username"], name=data["rcp_name"], token=data.get("rcp_token", ""))
    try:
        order = await orders.create(session, user, quote, rcp)
    except InsufficientBalance as e:
        await call.answer(texts.insufficient(e.need, e.have), show_alert=True)
        return
    await session.commit()
    await state.clear()
    await call.answer("Заказ принят ✅")
    await call.message.edit_text(texts.order_created(order.id, order.title, is_manual_mode()))
    await notify_admins(
        f"🛒 Новый заказ <b>#{order.id}</b>: {order.title} → @{order.recipient_username}\n"
        f"Покупатель: {user.display} (id{user.id}) · {fmt_uzs(order.price)}"
        + ("\n⚠️ <b>Ручной режим</b> — выполни и отметь в очереди." if is_manual_mode() else ""),
        reply_markup=kb.order_admin_kb(order.id) if is_manual_mode() else None,
    )
