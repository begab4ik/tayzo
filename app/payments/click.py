"""Click SHOP-API (Click Business).

Поток: бот создаёт Payment -> даёт ссылку на оплату -> Click вызывает наш URL дважды:
  action=0 Prepare  — проверяем подпись, сумму, статус; отвечаем merchant_prepare_id
  action=1 Complete — проверяем подпись; зачисляем баланс (идемпотентно по click_trans_id)

Коды ошибок Click:
  0 ok, -1 подпись, -2 сумма, -3 action, -4 уже оплачено, -5 юзер/платёж не найден,
  -6 транзакция не найдена, -7 ошибка обновления, -8 ошибка запроса, -9 транзакция отменена
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core import referrals, wallet
from app.core.enums import PaymentStatus
from app.db.models import Payment, User

log = logging.getLogger(__name__)

PREPARE, COMPLETE = 0, 1


def pay_url(payment: Payment, return_url: str | None = None) -> str:
    params = {
        "service_id": settings.click_service_id,
        "merchant_id": settings.click_merchant_id,
        "amount": f"{payment.amount:.2f}",
        "transaction_param": str(payment.id),
    }
    if return_url:
        params["return_url"] = return_url
    return "https://my.click.uz/services/pay?" + urlencode(params)


def _sign(d: dict, action: int) -> str:
    parts = [
        str(d["click_trans_id"]),
        str(d["service_id"]),
        settings.click_secret_key,
        str(d["merchant_trans_id"]),
    ]
    if action == COMPLETE:
        parts.append(str(d.get("merchant_prepare_id", "")))
    parts += [str(d["amount"]), str(d["action"]), str(d["sign_time"])]
    return hashlib.md5("".join(parts).encode()).hexdigest()


def _resp(d: dict, error: int, note: str, **extra) -> dict:
    return {
        "click_trans_id": d.get("click_trans_id"),
        "merchant_trans_id": d.get("merchant_trans_id"),
        "error": error,
        "error_note": note,
        **extra,
    }


async def create_payment(session: AsyncSession, user_id: int, amount: int) -> Payment:
    p = Payment(user_id=user_id, amount=amount, provider="click")
    session.add(p)
    await session.flush()
    return p


async def handle_webhook(session: AsyncSession, d: dict) -> tuple[dict, Payment | None]:
    """Возвращает (ответ для Click, платёж если он только что стал PAID — чтобы уведомить юзера)."""
    try:
        action = int(d.get("action", -1))
    except ValueError:
        return _resp(d, -3, "Action not found"), None

    if action not in (PREPARE, COMPLETE):
        return _resp(d, -3, "Action not found"), None
    if _sign(d, action) != str(d.get("sign_string", "")).lower():
        log.warning("Click bad sign: %s", d)
        return _resp(d, -1, "SIGN CHECK FAILED!"), None

    merchant_trans_id = str(d.get("merchant_trans_id", ""))
    if not merchant_trans_id.isdigit():
        return _resp(d, -5, "Payment not found"), None

    payment = (
        await session.execute(select(Payment).where(Payment.id == int(merchant_trans_id)).with_for_update())
    ).scalar_one_or_none()
    if not payment:
        return _resp(d, -5, "Payment not found"), None

    try:
        amount = Decimal(str(d.get("amount", "0")))
    except Exception:
        return _resp(d, -2, "Incorrect parameter amount"), None
    if amount != Decimal(payment.amount):
        return _resp(d, -2, "Incorrect parameter amount"), None

    if int(d.get("error", 0)) < 0:
        if payment.status != PaymentStatus.PAID:
            payment.status = PaymentStatus.CANCELLED
            payment.raw = d
        return _resp(d, -9, "Transaction cancelled"), None

    if action == PREPARE:
        if payment.status == PaymentStatus.PAID:
            return _resp(d, -4, "Already paid"), None
        payment.status = PaymentStatus.PREPARED
        payment.click_trans_id = str(d["click_trans_id"])
        payment.click_paydoc_id = str(d.get("click_paydoc_id", ""))
        payment.raw = d
        return _resp(d, 0, "Success", merchant_prepare_id=payment.id), None

    # COMPLETE
    if str(d.get("merchant_prepare_id")) != str(payment.id):
        return _resp(d, -6, "Transaction not found"), None
    if payment.status == PaymentStatus.PAID:
        return _resp(d, -4, "Already paid", merchant_confirm_id=payment.id), None
    if payment.status == PaymentStatus.CANCELLED:
        return _resp(d, -9, "Transaction cancelled"), None

    payment.status = PaymentStatus.PAID
    payment.paid_at = datetime.now(timezone.utc)
    payment.click_trans_id = str(d["click_trans_id"])
    payment.raw = d
    await wallet.topup(session, payment.user_id, payment.amount, payment.id)

    user = await session.get(User, payment.user_id)
    if user:
        await referrals.reward_for_topup(session, user, payment.amount, payment.id)

    log.info("Click payment %s PAID: user=%s amount=%s", payment.id, payment.user_id, payment.amount)
    return _resp(d, 0, "Success", merchant_confirm_id=payment.id), payment
