"""Покупка Premium: срок -> получатель -> подтверждение -> заказ."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot import texts
from app.bot.handlers.stars import USERNAME_RE, notify_new_order
from app.bot.i18n import t
from app.bot.notify import notify_admins
from app.bot.states import BuyPremium
from app.core import orders, pricing
from app.core import settings_store as cfg
from app.core.enums import ProductType
from app.core.exceptions import InsufficientBalance, ProviderError, RecipientNotFound
from app.db.models import User
from app.providers.base import Recipient
from app.providers.registry import get_provider, is_manual_mode

router = Router(name="premium")


@router.message(F.text.in_(kb.L("btn_premium")))
async def premium_start(message: Message, session: AsyncSession, user: User, state: FSMContext):
    await state.clear()
    lang = user.language
    if not await cfg.get_bool(session, "premium_enabled"):
        await message.answer(t(lang, "premium_disabled"))
        return
    prices = {m: (await pricing.quote_premium(session, m)).price_uzs for m in pricing.PREMIUM_MONTHS}
    await message.answer(texts.premium_intro(lang), reply_markup=kb.premium_kb(lang, prices))


@router.callback_query(F.data.startswith("prem:"))
async def pick_months(call: CallbackQuery, user: User, state: FSMContext):
    months = int(call.data.split(":")[1])
    await state.set_state(BuyPremium.recipient)
    await state.update_data(months=months)
    await call.answer()
    await call.message.edit_text(t(user.language, "premium_who", m=months), reply_markup=kb.recipient_kb(user.language, bool(user.username)))


@router.callback_query(BuyPremium.recipient, F.data == "rcp:self")
async def rcp_self(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    await call.answer()
    await _resolve_and_confirm(call.message, session, user, state, user.username or "", edit=True)


@router.callback_query(BuyPremium.recipient, F.data == "rcp:other")
async def rcp_other(call: CallbackQuery, user: User):
    await call.answer()
    await call.message.edit_text(texts.ask_username(user.language), reply_markup=kb.cancel_kb(user.language))


@router.message(BuyPremium.recipient)
async def rcp_input(message: Message, session: AsyncSession, user: User, state: FSMContext):
    m = USERNAME_RE.match((message.text or "").strip())
    if not m:
        await message.answer(t(user.language, "bad_username"), reply_markup=kb.cancel_kb(user.language))
        return
    await _resolve_and_confirm(message, session, user, state, m.group(1), edit=False)


async def _resolve_and_confirm(message: Message, session: AsyncSession, user: User, state: FSMContext, username: str, edit: bool):
    lang = user.language
    data = await state.get_data()
    months = int(data["months"])
    send = message.edit_text if edit else message.answer
    try:
        rcp = await get_provider(ProductType.PREMIUM).resolve_recipient(username, months)
    except RecipientNotFound:
        await send(f"❌ {t(lang, 'recipient_premium_fail')}", reply_markup=kb.cancel_kb(lang))
        return
    except ProviderError as e:
        await send(t(lang, "recipient_check_fail"), reply_markup=kb.cancel_kb(lang))
        await notify_admins(f"⚠️ Fragment resolve error: {e.message}")
        return
    quote = await pricing.quote_premium(session, months)
    await state.update_data(rcp_username=rcp.username, rcp_name=rcp.name, rcp_token=rcp.token, price=quote.price_uzs)
    await state.set_state(BuyPremium.confirm)
    text = texts.confirm_order(lang, t(lang, "premium_title", m=months), rcp.name, rcp.username, quote.price_uzs, user.balance)
    await send(text, reply_markup=kb.confirm_kb(lang, user.balance >= quote.price_uzs, quote.price_uzs - user.balance))


@router.callback_query(BuyPremium.confirm, F.data == "order:confirm")
async def confirm(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    lang = user.language
    data = await state.get_data()
    months = int(data["months"])
    quote = await pricing.quote_premium(session, months)
    rcp = Recipient(username=data["rcp_username"], name=data["rcp_name"], token=data.get("rcp_token", ""))
    try:
        order = await orders.create(session, user, quote, rcp)
    except InsufficientBalance as e:
        await call.answer(texts.insufficient(lang, e.need, e.have), show_alert=True)
        return
    await session.commit()
    await state.clear()
    await call.answer(t(lang, "order_accepted"))
    await call.message.edit_text(texts.order_created(lang, order.id, texts.order_title(lang, order), is_manual_mode()))
    await notify_new_order(order, user)
