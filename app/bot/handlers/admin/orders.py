"""Очередь проблемных заказов: повторить / выполнено вручную / вернуть деньги."""
from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot import texts
from app.bot.notify import notify_user
from app.core import orders as orders_svc
from app.core.enums import OrderStatus
from app.core.money import fmt_uzs
from app.db.models import AuditLog, Order, User

router = Router(name="admin_orders")


def order_card(o: Order) -> str:
    return (
        f"📦 <b>Заказ #{o.id}</b> · {o.status}\n"
        f"{o.title} → @{o.recipient_username} ({o.recipient_name or '—'})\n"
        f"Покупатель: id{o.user_id} · {fmt_uzs(o.price)} · {o.created_at:%d.%m %H:%M}\n"
        f"Попыток: {o.attempts}\n"
        + (f"Ошибка: <code>{(o.last_error or '')[:300]}</code>" if o.last_error else "")
    )


@router.callback_query(F.data == "adm:queue")
async def queue(call: CallbackQuery, session: AsyncSession):
    rows = await orders_svc.manual_queue(session)
    await call.answer()
    if not rows:
        await call.message.edit_text("✅ Очередь пуста — проблемных заказов нет.", reply_markup=kb.admin_back_kb())
        return
    await call.message.edit_text(f"👨‍💻 Заказов, требующих внимания: <b>{len(rows)}</b>", reply_markup=kb.admin_back_kb())
    for o in rows:
        await call.message.answer(order_card(o), reply_markup=kb.order_admin_kb(o.id))


@router.callback_query(F.data.startswith("adm:order:"))
async def order_action(call: CallbackQuery, session: AsyncSession):
    _, _, action, oid = call.data.split(":")
    order = await session.get(Order, int(oid), with_for_update=True)
    if not order:
        await call.answer("Заказ не найден", show_alert=True)
        return
    if order.status in (OrderStatus.DELIVERED, OrderStatus.REFUNDED):
        await call.answer(f"Заказ уже {order.status}", show_alert=True)
        await call.message.edit_text(order_card(order))
        return

    buyer = await session.get(User, order.user_id)
    lang = buyer.language if buyer else "ru"
    if action == "retry":
        order.status = OrderStatus.PENDING
        order.attempts = 0
        msg = "🔁 Отправлен на повтор"
    elif action == "done":
        await orders_svc.mark_done_manually(session, order, call.from_user.id)
        await notify_user(order.user_id, texts.order_delivered(lang, order))
        msg = "✅ Отмечен выполненным"
    elif action == "refund":
        await orders_svc.refund(session, order, comment=f"возврат админом {call.from_user.id}")
        await notify_user(order.user_id, texts.order_refunded(lang, order))
        msg = "↩️ Деньги возвращены"
    else:
        await call.answer("Неизвестное действие", show_alert=True)
        return

    session.add(AuditLog(admin_id=call.from_user.id, action=f"order_{action}", details={"order_id": order.id}))
    await session.commit()
    await call.answer(msg)
    await call.message.edit_text(order_card(order) + f"\n\n{msg}")
