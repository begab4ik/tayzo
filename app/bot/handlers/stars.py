"""Покупка Stars: получатель -> количество -> подтверждение -> заказ."""
from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot import texts
from app.bot.i18n import t
from app.bot.notify import notify_admins
from app.bot.states import BuyStars
from app.core import orders, pricing
from app.core import settings_store as cfg
from app.core.enums import ProductType
from app.core.exceptions import InsufficientBalance, ProviderError, RecipientNotFound
from app.core.money import fmt_uzs
from app.db.models import User
from app.providers.base import Recipient
from app.providers.registry import get_provider, is_manual_mode

router = Router(name="stars")
USERNAME_RE = re.compile(r"^@?([A-Za-z][A-Za-z0-9_]{3,31})$")


async def notify_new_order(order, user: User) -> None:
    await notify_admins(
        f"🛒 Новый заказ <b>#{order.id}</b>: {order.title} → @{order.recipient_username}\n"
        f"Покупатель: {user.display} (id{user.id}) · {fmt_uzs(order.price)}"
        + ("\n⚠️ <b>Ручной режим</b> — выполни и отметь в очереди." if is_manual_mode() else ""),
        reply_markup=kb.order_admin_kb(order.id) if is_manual_mode() else None,
    )


@router.message(F.text.in_(kb.L("btn_stars")))
async def stars_start(message: Message, session: AsyncSession, user: User, state: FSMContext):
    await state.clear()
    lang = user.language
    if not await cfg.get_bool(session, "stars_enabled"):
        await message.answer(t(lang, "stars_disabled"))
        return
    price_each = await pricing.star_price_each(session)
    mn, mx = await cfg.get_int(session, "min_stars"), await cfg.get_int(session, "max_stars")
    await state.set_state(BuyStars.recipient)
    await message.answer(texts.stars_intro(lang, price_each, mn, mx), reply_markup=kb.recipient_kb(lang, bool(user.username)))


@router.callback_query(BuyStars.recipient, F.data == "rcp:self")
async def rcp_self(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    await call.answer()
    await _resolve_and_ask_qty(call.message, session, user, state, user.username or "", edit=True)


@router.callback_query(BuyStars.recipient, F.data == "rcp:other")
async def rcp_other(call: CallbackQuery, user: User):
    await call.answer()
    await call.message.edit_text(texts.ask_username(user.language), reply_markup=kb.cancel_kb(user.language))


@router.message(BuyStars.recipient)
async def rcp_input(message: Message, session: AsyncSession, user: User, state: FSMContext):
    m = USERNAME_RE.match((message.text or "").strip())
    if not m:
        await message.answer(t(user.language, "bad_username"), reply_markup=kb.cancel_kb(user.language))
        return
    await _resolve_and_ask_qty(message, session, user, state, m.group(1), edit=False)


async def _resolve_and_ask_qty(message: Message, session: AsyncSession, user: User, state: FSMContext, username: str, edit: bool):
    lang = user.language
    send = message.edit_text if edit else message.answer
    mn = await cfg.get_int(session, "min_stars")
    try:
        rcp = await get_provider(ProductType.STARS).resolve_recipient(username, mn)
    except RecipientNotFound:
        await send(f"❌ {t(lang, 'recipient_not_found')}", reply_markup=kb.cancel_kb(lang))
        return
    except ProviderError as e:
        await send(t(lang, "recipient_check_fail"), reply_markup=kb.cancel_kb(lang))
        await notify_admins(f"⚠️ Fragment resolve error: {e.message}")
        return
    await state.update_data(rcp_username=rcp.username, rcp_name=rcp.name, rcp_token=rcp.token)
    await state.set_state(BuyStars.quantity)
    price_each = await pricing.star_price_each(session)
    await send(texts.ask_stars_qty(lang, rcp.name, rcp.username), reply_markup=kb.stars_qty_kb(lang, price_each))


@router.callback_query(BuyStars.quantity, F.data.startswith("qty:"))
async def qty_preset(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    await call.answer()
    await _show_confirm(call.message, session, user, state, int(call.data.split(":")[1]), edit=True)


@router.message(BuyStars.quantity)
async def qty_input(message: Message, session: AsyncSession, user: User, state: FSMContext):
    raw = (message.text or "").replace(" ", "")
    if not raw.isdigit():
        await message.answer(t(user.language, "qty_number"), reply_markup=kb.cancel_kb(user.language))
        return
    await _show_confirm(message, session, user, state, int(raw), edit=False)


async def _show_confirm(message: Message, session: AsyncSession, user: User, state: FSMContext, qty: int, edit: bool):
    lang = user.language
    mn, mx = await cfg.get_int(session, "min_stars"), await cfg.get_int(session, "max_stars")
    if not (mn <= qty <= mx):
        await message.answer(t(lang, "qty_range", min=mn, max=mx), reply_markup=kb.cancel_kb(lang))
        return
    quote = await pricing.quote_stars(session, qty)
    data = await state.get_data()
    await state.update_data(qty=qty, price=quote.price_uzs)
    await state.set_state(BuyStars.confirm)
    enough = user.balance >= quote.price_uzs
    text = texts.confirm_order(lang, f"⭐ {qty} Stars", data["rcp_name"], data["rcp_username"], quote.price_uzs, user.balance)
    markup = kb.confirm_kb(lang, enough, quote.price_uzs - user.balance)
    await (message.edit_text if edit else message.answer)(text, reply_markup=markup)


@router.callback_query(BuyStars.confirm, F.data == "order:confirm")
async def confirm(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    lang = user.language
    data = await state.get_data()
    qty = int(data["qty"])
    quote = await pricing.quote_stars(session, qty)  # пересчитываем — курс мог измениться
    if quote.price_uzs != int(data["price"]):
        await state.update_data(price=quote.price_uzs)
        await call.answer(t(lang, "price_changed"), show_alert=True)
        text = texts.confirm_order(lang, f"⭐ {qty} Stars", data["rcp_name"], data["rcp_username"], quote.price_uzs, user.balance)
        await call.message.edit_text(text, reply_markup=kb.confirm_kb(lang, user.balance >= quote.price_uzs, quote.price_uzs - user.balance))
        return

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
