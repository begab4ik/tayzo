from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot import texts
from app.bot.i18n import t
from app.bot.states import TopUp
from app.core import settings_store as cfg
from app.core import wallet
from app.core.enums import LedgerType, PaymentStatus
from app.core.money import fmt_uzs
from app.db.models import Payment, User
from app.payments import common as pay

router = Router(name="balance")

LEDGER_ICONS = {
    LedgerType.TOPUP: "💳",
    LedgerType.PURCHASE: "🛒",
    LedgerType.REFUND: "↩️",
    LedgerType.REFERRAL_BONUS: "👥",
    LedgerType.PROMO_BONUS: "🎟",
    LedgerType.ADMIN_ADJUST: "🛠",
}


@router.message(F.text.in_(kb.L("btn_balance")))
async def balance(message: Message, user: User):
    await message.answer(texts.menu_balance(user.language, user.balance), reply_markup=kb.balance_kb(user.language))


@router.callback_query(F.data == "balance")
async def balance_cb(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    await state.clear()
    await session.refresh(user)
    await call.answer()
    await call.message.edit_text(texts.menu_balance(user.language, user.balance), reply_markup=kb.balance_kb(user.language))


@router.callback_query(F.data == "ledger")
async def ledger(call: CallbackQuery, session: AsyncSession, user: User):
    rows = await wallet.history(session, user.id, limit=15)
    if not rows:
        await call.answer(t(user.language, "no_ops"), show_alert=True)
        return
    lines = [t(user.language, "history_title") + "\n"]
    for r in rows:
        sign = "+" if r.amount > 0 else "−"
        lines.append(f"{LEDGER_ICONS.get(r.type, '•')} {sign}{fmt_uzs(abs(r.amount))} — {r.created_at:%d.%m %H:%M}")
    await call.answer()
    await call.message.edit_text("\n".join(lines), reply_markup=kb.back_kb(user.language, "balance"))


@router.callback_query(F.data == "topup")
async def topup_start(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    await state.clear()
    mn, mx = await cfg.get_int(session, "min_topup"), await cfg.get_int(session, "max_topup")
    await call.answer()
    await call.message.edit_text(texts.topup_prompt(user.language, mn, mx), reply_markup=kb.topup_amounts_kb(user.language))


@router.callback_query(F.data == "topup:custom")
async def topup_custom(call: CallbackQuery, user: User, state: FSMContext):
    await state.set_state(TopUp.amount)
    await call.answer()
    await call.message.edit_text(t(user.language, "topup_custom"), reply_markup=kb.cancel_kb(user.language))


@router.callback_query(F.data.startswith("topup:"))
async def topup_preset(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    amount = int(call.data.split(":")[1])
    await _create_and_send(call.message, session, user, amount, edit=True)
    await call.answer()


@router.message(TopUp.amount)
async def topup_amount_input(message: Message, session: AsyncSession, user: User, state: FSMContext):
    raw = (message.text or "").replace(" ", "").replace(",", "")
    if not raw.isdigit():
        await message.answer(t(user.language, "need_number"), reply_markup=kb.cancel_kb(user.language))
        return
    await state.clear()
    await _create_and_send(message, session, user, int(raw), edit=False)


async def _create_and_send(message: Message, session: AsyncSession, user: User, amount: int, edit: bool, method: str | None = None):
    lang = user.language
    mn, mx = await cfg.get_int(session, "min_topup"), await cfg.get_int(session, "max_topup")
    amount = max(amount, mn)
    if amount > mx:
        await message.answer(t(lang, "topup_max", max=fmt_uzs(mx)))
        return
    methods = pay.available()
    if not methods:
        await message.answer(t(lang, "topup_unavailable"))
        return
    if method not in methods:
        if len(methods) > 1:
            text, markup = texts.topup_choose_method(lang, amount), kb.pay_method_kb(lang, amount, methods)
            await (message.edit_text(text, reply_markup=markup) if edit else message.answer(text, reply_markup=markup))
            return
        method = methods[0]
    payment = await pay.create(session, user.id, amount, method)
    await session.commit()
    url = pay.pay_url(payment, return_url=f"https://t.me/{(await message.bot.me()).username}", lang=lang)
    text = texts.topup_link(lang, amount, pay.TITLES[method])
    markup = kb.pay_kb(lang, url, payment.id, method)
    if edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("paymeth:"))
async def pay_method_chosen(call: CallbackQuery, session: AsyncSession, user: User):
    _, method, amount = call.data.split(":")
    await call.answer()
    await _create_and_send(call.message, session, user, int(amount), edit=True, method=method)


@router.callback_query(F.data.startswith("paycheck:"))
async def paycheck(call: CallbackQuery, session: AsyncSession, user: User):
    lang = user.language
    payment = await session.get(Payment, int(call.data.split(":")[1]))
    if not payment or payment.user_id != user.id:
        await call.answer(t(lang, "pay_not_found"), show_alert=True)
        return
    if payment.status == PaymentStatus.PAID:
        await call.answer(t(lang, "pay_received"), show_alert=True)
        await call.message.edit_text(texts.topup_success(lang, payment.amount, user.balance))
    elif payment.status == PaymentStatus.CANCELLED:
        await call.answer(t(lang, "pay_cancelled"), show_alert=True)
    else:
        await call.answer(t(lang, "pay_pending"), show_alert=True)
