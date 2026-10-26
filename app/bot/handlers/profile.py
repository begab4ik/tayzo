from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot import texts
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
STATUS_TEXT = {
    OrderStatus.PENDING: "в очереди",
    OrderStatus.PROCESSING: "выполняется",
    OrderStatus.DELIVERED: "выполнен",
    OrderStatus.FAILED: "в очереди",
    OrderStatus.MANUAL: "проверяется менеджером",
    OrderStatus.REFUNDED: "возврат",
}


@router.message(F.text == kb.BTN_PROFILE)
@router.message(Command("profile"))
async def profile(message: Message, bot: Bot, session: AsyncSession, user: User):
    orders_count = (await session.execute(select(func.count()).where(Order.user_id == user.id))).scalar_one()
    ref_count, ref_earned = await referrals.stats(session, user.id)
    me = await bot.me()
    percent = await cfg.get_int(session, "referral_percent")
    await message.answer(
        texts.profile(user, orders_count, ref_count, ref_earned, referrals.ref_link(me.username, user.id), percent),
        disable_web_page_preview=True,
    )


@router.message(F.text == kb.BTN_ORDERS)
@router.message(Command("orders"))
async def my_orders(message: Message, session: AsyncSession, user: User):
    rows = await orders.user_orders(session, user.id, limit=10)
    if not rows:
        await message.answer("📦 Заказов пока нет. Самое время купить звёзды ⭐")
        return
    lines = ["📦 <b>Последние заказы</b>\n"]
    for o in rows:
        lines.append(
            f"{STATUS_ICON[o.status]} #{o.id} · {o.title} → @{o.recipient_username}\n"
            f"    {fmt_uzs(o.price)} · {STATUS_TEXT[o.status]} · {o.created_at:%d.%m %H:%M}"
        )
    await message.answer("\n".join(lines))


@router.message(F.text == kb.BTN_PROMO)
@router.message(Command("promo"))
async def promo_start(message: Message, state: FSMContext):
    await state.set_state(Promo.code)
    await message.answer("🎟 Введи промокод:", reply_markup=kb.cancel_kb())


@router.message(Promo.code)
async def promo_input(message: Message, session: AsyncSession, user: User, state: FSMContext):
    code = (message.text or "").strip()
    try:
        p = await promo.activate(session, user.id, code)
    except TayzoError as e:
        await message.answer(f"❌ {e.message}", reply_markup=kb.cancel_kb())
        return
    await state.clear()
    await session.refresh(user)
    await message.answer(f"🎉 Промокод активирован! +{fmt_uzs(p.amount)}\n💰 Баланс: <b>{fmt_uzs(user.balance)}</b>")
