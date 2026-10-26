"""Поиск пользователя, начисление/списание, бан."""
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot.notify import notify_user
from app.bot.states import Admin
from app.core import wallet
from app.core.enums import LedgerType
from app.core.exceptions import InsufficientBalance
from app.core.money import fmt_uzs
from app.db.models import AuditLog, Order, User

router = Router(name="admin_users")


def user_card(u: User, orders_count: int) -> str:
    return (
        f"👤 <b>{u.first_name or ''}</b> {u.display}\n"
        f"ID: <code>{u.id}</code>\n"
        f"Баланс: <b>{fmt_uzs(u.balance)}</b>\n"
        f"Пополнено: {fmt_uzs(u.total_topup)} · Потрачено: {fmt_uzs(u.total_spent)}\n"
        f"Звёзд куплено: ⭐{u.total_stars} · Заказов: {orders_count}\n"
        f"Реферер: {u.referrer_id or '—'} · Бан: {'да' if u.is_banned else 'нет'}\n"
        f"Регистрация: {u.created_at:%d.%m.%Y}"
    )


async def find_user(session: AsyncSession, query: str) -> User | None:
    query = query.strip().lstrip("@")
    if query.isdigit():
        return await session.get(User, int(query))
    return (await session.execute(select(User).where(func.lower(User.username) == query.lower()))).scalar_one_or_none()


async def show_user(message: Message, session: AsyncSession, u: User):
    cnt = (await session.execute(select(func.count()).where(Order.user_id == u.id))).scalar_one()
    await message.answer(user_card(u, cnt), reply_markup=kb.user_admin_kb(u.id, u.is_banned))


@router.callback_query(F.data == "adm:user")
async def ask_user(call: CallbackQuery, state: FSMContext):
    await state.set_state(Admin.find_user)
    await call.answer()
    await call.message.edit_text("Введи ID или @username пользователя:", reply_markup=kb.admin_back_kb())


@router.message(Admin.find_user)
async def find_user_input(message: Message, session: AsyncSession, state: FSMContext):
    u = await find_user(session, message.text or "")
    if not u:
        await message.answer("Не найден. Попробуй ещё раз:", reply_markup=kb.admin_back_kb())
        return
    await state.clear()
    await show_user(message, session, u)


@router.callback_query(F.data.startswith("adm:ubal:"))
async def adjust_start(call: CallbackQuery, state: FSMContext):
    _, _, direction, uid = call.data.split(":")
    await state.set_state(Admin.adjust_balance)
    await state.update_data(uid=int(uid), direction=direction)
    await call.answer()
    verb = "начислить" if direction == "add" else "списать"
    await call.message.answer(f"Сколько сум {verb} пользователю {uid}? Можно с комментарием: <code>50000 бонус за отзыв</code>")


@router.message(Admin.adjust_balance)
async def adjust_input(message: Message, session: AsyncSession, state: FSMContext):
    data = await state.get_data()
    parts = (message.text or "").split(maxsplit=1)
    if not parts or not parts[0].isdigit():
        await message.answer("Нужно число. Пример: <code>50000 комментарий</code>")
        return
    amount = int(parts[0])
    comment = parts[1] if len(parts) > 1 else None
    signed = amount if data["direction"] == "add" else -amount
    try:
        await wallet.apply(session, data["uid"], signed, LedgerType.ADMIN_ADJUST, ref_type="user", ref_id=message.from_user.id, comment=comment)
    except InsufficientBalance as e:
        await message.answer(f"У пользователя только {fmt_uzs(e.have)}")
        return
    session.add(AuditLog(admin_id=message.from_user.id, action="adjust_balance", details={"user_id": data["uid"], "amount": signed, "comment": comment}))
    await state.clear()
    u = await session.get(User, data["uid"])
    await session.commit()
    sign = "+" if signed > 0 else "−"
    await notify_user(u.id, f"🛠 Администратор изменил твой баланс: {sign}{fmt_uzs(abs(signed))}" + (f"\n💬 {comment}" if comment else "") + f"\n💰 Баланс: {fmt_uzs(u.balance)}")
    await show_user(message, session, u)


@router.callback_query(F.data.startswith("adm:uban:"))
async def toggle_ban(call: CallbackQuery, session: AsyncSession):
    u = await session.get(User, int(call.data.split(":")[2]))
    if not u:
        await call.answer("Не найден", show_alert=True)
        return
    u.is_banned = not u.is_banned
    session.add(AuditLog(admin_id=call.from_user.id, action="ban" if u.is_banned else "unban", details={"user_id": u.id}))
    await session.commit()
    await call.answer("Забанен" if u.is_banned else "Разбанен")
    cnt = (await session.execute(select(func.count()).where(Order.user_id == u.id))).scalar_one()
    await call.message.edit_text(user_card(u, cnt), reply_markup=kb.user_admin_kb(u.id, u.is_banned))
