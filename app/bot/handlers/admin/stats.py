from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.core import stats as stats_svc
from app.core.money import fmt_uzs

router = Router(name="admin_stats")


async def render(session: AsyncSession, period: str) -> str:
    s = await stats_svc.collect(session, period)
    top = await stats_svc.top_buyers(session, 5)
    lines = [
        f"📊 <b>Статистика — {stats_svc.PERIODS[period]}</b>\n",
        f"⭐ Звёзд продано: <b>{s.stars_sold:,}</b> ({s.stars_orders} зак.)",
        f"💎 Premium продано: <b>{s.premium_orders}</b>",
        "",
        f"💵 Выручка: <b>{fmt_uzs(s.revenue)}</b>",
        f"📉 Себестоимость: {fmt_uzs(s.cost)}",
        f"📈 Прибыль: <b>{fmt_uzs(s.profit)}</b> ({s.margin_pct:.1f}%)",
        f"↩️ Возвраты: {fmt_uzs(s.refunded_sum)}",
        "",
        f"💳 Пополнений: <b>{fmt_uzs(s.topup_sum)}</b> ({s.topup_count} шт.)",
        f"👤 Новых пользователей: <b>{s.new_users}</b>",
        "",
        f"⏳ В очереди сейчас: {s.pending} · 👨‍💻 Требуют внимания: <b>{s.manual}</b>",
    ]
    if top:
        lines += ["", "🏆 <b>Топ покупателей</b>"]
        for i, u in enumerate(top, 1):
            lines.append(f"{i}. {u.display} — {fmt_uzs(u.total_spent)} · ⭐{u.total_stars}")
    return "\n".join(lines).replace(",", " ")


@router.message(Command("stats"))
async def stats_cmd(message: Message, session: AsyncSession):
    await message.answer(await render(session, "today"), reply_markup=kb.stats_period_kb("today"))


@router.callback_query(F.data.startswith("adm:stats:"))
async def stats_cb(call: CallbackQuery, session: AsyncSession):
    period = call.data.split(":")[2]
    if period not in stats_svc.PERIODS:
        period = "today"
    await call.answer()
    try:
        await call.message.edit_text(await render(session, period), reply_markup=kb.stats_period_kb(period))
    except Exception:  # noqa: BLE001 — "message is not modified"
        pass
