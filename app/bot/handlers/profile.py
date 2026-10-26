from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot import texts
from app.bot.i18n import t
from app.bot.states import Promo
from app.core import orders, promo, referrals
from app.core import settings_store as cfg
from app.core.enums import OrderStatus
from app.core.exceptions import TayzoError
from app.core.money import fmt_uzs
from app.db.models import Order, User

router = Router(name="profile")

STATUS_ICON = {
    OrderStatus.PENDING: "⏳",
    OrderStatus.PROCESSING: "⚙️",
    OrderStatus.DELIVERED: "✅",
    OrderStatus.FAILED: "⏳",
    OrderStatus.MANUAL: "👨‍💻",
    OrderStatus.REFUNDED: "↩️",
}
STATUS_KEY = {
    OrderStatus.PENDING: "st_pending",
    OrderStatus.PROCESSING: "st_processing",
    OrderStatus.DELIVERED: "st_delivered",
    OrderStatus.FAILED: "st_pending",
    OrderStatus.MANUAL: "st_manual",
    OrderStatus.REFUNDED: "st_refunded",
}


@router.message(F.text.in_(kb.L("btn_profile")))
@router.message(Command("profile"))
async def profile(message: Message, bot: Bot, session: AsyncSession, user: User):
    orders_count = (await session.execute(select(func.count()).where(Order.user_id == user.id))).scalar_one()
    ref_count, ref_earned = await referrals.stats(session, user.id)
    me = await bot.me()
    percent = await cfg.get_int(session, "referral_percent")
    await message.answer(
        texts.profile(user.language, user, orders_count, ref_count, ref_earned, referrals.ref_link(me.username, user.id), percent),
        disable_web_page_preview=True,
    )


@router.message(F.text.in_(kb.L("btn_orders")))
@router.message(Command("orders"))
async def my_orders(message: Message, session: AsyncSession, user: User):
    lang = user.language
    rows = await orders.user_orders(session, user.id, limit=10)
    if not rows:
        await message.answer(t(lang, "no_orders"))
        return
    lines = [t(lang, "orders_title") + "\n"]
    for o in rows:
        lines.append(
            f"{STATUS_ICON[o.status]} #{o.id} · {texts.order_title(lang, o)} → @{o.recipient_username}\n"
            f"    {fmt_uzs(o.price)} · {t(lang, STATUS_KEY[o.status])} · {o.created_at:%d.%m %H:%M}"
        )
    await message.answer("\n".join(lines))


@router.message(F.text.in_(kb.L("btn_promo")))
@router.message(Command("promo"))
async def promo_start(message: Message, user: User, state: FSMContext):
    await state.set_state(Promo.code)
    await message.answer(t(user.language, "promo_enter"), reply_markup=kb.cancel_kb(user.language))


@router.message(Promo.code)
async def promo_input(message: Message, session: AsyncSession, user: User, state: FSMContext):
    code = (message.text or "").strip()
    try:
        p = await promo.activate(session, user.id, code)
    except TayzoError as e:
        await message.answer(f"❌ {e.message}", reply_markup=kb.cancel_kb(user.language))
        return
    await state.clear()
    await session.refresh(user)
    await message.answer(t(user.language, "promo_ok", amount=fmt_uzs(p.amount), balance=fmt_uzs(user.balance)))
