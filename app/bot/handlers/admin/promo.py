from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot.states import Admin
from app.core import promo as promo_svc
from app.core.money import fmt_uzs
from app.db.models import AuditLog

router = Router(name="admin_promo")


@router.callback_query(F.data == "adm:promo")
async def promo_menu(call: CallbackQuery, session: AsyncSession, state: FSMContext):
    rows = await promo_svc.list_active(session)
    lines = ["🎟 <b>Промокоды</b>\n"]
    for p in rows:
        lines.append(f"<code>{p.code}</code> — {fmt_uzs(p.amount)} · {p.used_count}/{p.max_uses}")
    if not rows:
        lines.append("Активных нет.")
    lines.append("\nСоздать: отправь <code>сумма кол-во [КОД]</code>\nПример: <code>10000 50 WELCOME</code>")
    await state.set_state(Admin.promo_create)
    await call.answer()
    await call.message.edit_text("\n".join(lines), reply_markup=kb.admin_back_kb())


@router.message(Admin.promo_create)
async def promo_create(message: Message, session: AsyncSession, state: FSMContext):
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
        await message.answer("Формат: <code>сумма кол-во [КОД]</code>")
        return
    code = parts[2] if len(parts) > 2 else None
    try:
        p = await promo_svc.create(session, int(parts[0]), int(parts[1]), code)
        session.add(AuditLog(admin_id=message.from_user.id, action="promo_create", details={"code": p.code, "amount": p.amount, "max_uses": p.max_uses}))
        await session.commit()
    except Exception as e:  # noqa: BLE001 — дубликат кода и т.п.
        await session.rollback()
        await message.answer(f"❌ Не удалось создать: {e}")
        return
    await state.clear()
    await message.answer(f"✅ Промокод <code>{p.code}</code> на {fmt_uzs(p.amount)}, использований: {p.max_uses}", reply_markup=kb.admin_back_kb())
