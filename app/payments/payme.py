"""Payme Business — Merchant API (JSON-RPC 2.0).

Поток: бот создаёт Payment -> даёт ссылку checkout.paycom.uz -> Payme вызывает наш URL:
  CheckPerformTransaction -> CreateTransaction -> PerformTransaction (зачисляем баланс) / CancelTransaction.
Суммы у Payme в тийинах (сум × 100), время — unix ms. Поле счёта: account.payment_id.

Коды ошибок Payme: -32504 нет прав, -32600 неверный запрос, -32601 метод не найден,
  -31001 неверная сумма, -31050 счёт не найден, -31003 транзакция не найдена,
  -31008 нельзя выполнить, -31007 нельзя отменить.
"""
from __future__ import annotations

import base64
import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core import referrals, wallet
from app.core.enums import PaymentStatus
from app.db.models import Payment, User

log = logging.getLogger(__name__)

CHECKOUT = "https://checkout.paycom.uz/"
ACCOUNT_FIELD = "payment_id"
STATE_CREATED, STATE_PERFORMED, STATE_CANCELLED, STATE_CANCELLED_AFTER = 1, 2, -1, -2
TIMEOUT_MS = 12 * 3600 * 1000  # Payme: транзакция без Perform дольше 12 часов считается просроченной


def pay_url(payment: Payment, return_url: str | None = None, lang: str = "ru") -> str:
    parts = [f"m={settings.payme_merchant_id}", f"ac.{ACCOUNT_FIELD}={payment.id}", f"a={payment.amount * 100}", f"l={lang}"]
    if return_url:
        parts.append(f"c={return_url}")
    return CHECKOUT + base64.b64encode(";".join(parts).encode()).decode()


async def create_payment(session: AsyncSession, user_id: int, amount: int) -> Payment:
    p = Payment(user_id=user_id, amount=amount, provider="payme")
    session.add(p)
    await session.flush()
    return p


def check_auth(authorization: str | None) -> bool:
    if not authorization or not authorization.startswith("Basic "):
        return False
    try:
        raw = base64.b64decode(authorization[6:]).decode()
    except Exception:  # noqa: BLE001
        return False
    login, _, key = raw.partition(":")
    return login == "Paycom" and key in {settings.payme_key, settings.payme_test_key} - {""}


def _err(code: int, msg: str, data: str | None = None) -> dict:
    e: dict[str, Any] = {"code": code, "message": {"ru": msg, "uz": msg, "en": msg}}
    if data:
        e["data"] = data
    return {"error": e}


def _ms(dt: datetime | None) -> int:
    return int(dt.timestamp() * 1000) if dt else 0


def _meta(p: Payment) -> dict:
    return (p.raw or {}).get("payme", {}) if isinstance(p.raw, dict) else {}


def _set_meta(p: Payment, **kw) -> None:
    raw = dict(p.raw or {})
    meta = dict(raw.get("payme", {}))
    meta.update(kw)
    raw["payme"] = meta
    p.raw = raw


def _state(p: Payment) -> int:
    m = _meta(p)
    if p.status == PaymentStatus.PAID:
        return STATE_PERFORMED
    if p.status == PaymentStatus.CANCELLED:
        return int(m.get("state", STATE_CANCELLED))
    return STATE_CREATED


def _tx_json(p: Payment) -> dict:
    m = _meta(p)
    return {
        "create_time": int(m.get("create_time", 0)),
        "perform_time": _ms(p.paid_at),
        "cancel_time": int(m.get("cancel_time", 0)),
        "transaction": str(p.id),
        "state": _state(p),
        "reason": m.get("reason"),
    }


async def _payment_by_account(session: AsyncSession, params: dict, lock: bool = False) -> Payment | None:
    pid = str((params.get("account") or {}).get(ACCOUNT_FIELD, "")).strip()
    if not pid.isdigit():
        return None
    q = select(Payment).where(Payment.id == int(pid), Payment.provider == "payme")
    if lock:
        q = q.with_for_update()
    return (await session.execute(q)).scalar_one_or_none()


async def _payment_by_trans(session: AsyncSession, trans_id: str, lock: bool = False) -> Payment | None:
    q = select(Payment).where(Payment.click_trans_id == str(trans_id), Payment.provider == "payme")
    if lock:
        q = q.with_for_update()
    return (await session.execute(q)).scalar_one_or_none()


async def handle(session: AsyncSession, method: str, params: dict) -> tuple[dict, Payment | None]:
    """Возвращает (result|error, платёж если только что оплачен — для уведомления)."""
    if method == "CheckPerformTransaction":
        p = await _payment_by_account(session, params)
        if not p or p.status == PaymentStatus.CANCELLED:
            return _err(-31050, "Платёж не найден", ACCOUNT_FIELD), None
        if int(params.get("amount", 0)) != p.amount * 100:
            return _err(-31001, "Неверная сумма"), None
        if p.status == PaymentStatus.PAID:
            return _err(-31050, "Платёж уже оплачен", ACCOUNT_FIELD), None
        return {"result": {"allow": True}}, None

    if method == "CreateTransaction":
        trans_id = str(params.get("id", ""))
        existing = await _payment_by_trans(session, trans_id, lock=True)
        if existing:
            if _state(existing) == STATE_CREATED and time.time() * 1000 - int(_meta(existing).get("create_time", 0)) > TIMEOUT_MS:
                existing.status = PaymentStatus.CANCELLED
                _set_meta(existing, state=STATE_CANCELLED, cancel_time=int(time.time() * 1000), reason=4)
            if _state(existing) != STATE_CREATED:
                return _err(-31008, "Транзакцию нельзя выполнить"), None
            return {"result": {"create_time": _meta(existing).get("create_time", 0), "transaction": str(existing.id), "state": STATE_CREATED}}, None
        p = await _payment_by_account(session, params, lock=True)
        if not p or p.status == PaymentStatus.CANCELLED:
            return _err(-31050, "Платёж не найден", ACCOUNT_FIELD), None
        if int(params.get("amount", 0)) != p.amount * 100:
            return _err(-31001, "Неверная сумма"), None
        if p.status == PaymentStatus.PAID or (p.click_trans_id and p.click_trans_id != trans_id):
            return _err(-31050, "По этому счёту уже есть транзакция", ACCOUNT_FIELD), None
        p.click_trans_id = trans_id
        p.status = PaymentStatus.PREPARED
        _set_meta(p, create_time=int(params.get("time") or time.time() * 1000), state=STATE_CREATED)
        return {"result": {"create_time": _meta(p)["create_time"], "transaction": str(p.id), "state": STATE_CREATED}}, None

    if method == "PerformTransaction":
        p = await _payment_by_trans(session, str(params.get("id", "")), lock=True)
        if not p:
            return _err(-31003, "Транзакция не найдена"), None
        if p.status == PaymentStatus.PAID:
            return {"result": {"transaction": str(p.id), "perform_time": _ms(p.paid_at), "state": STATE_PERFORMED}}, None
        if p.status == PaymentStatus.CANCELLED:
            return _err(-31008, "Транзакция отменена"), None
        p.status = PaymentStatus.PAID
        p.paid_at = datetime.now(timezone.utc)
        _set_meta(p, state=STATE_PERFORMED)
        await wallet.topup(session, p.user_id, p.amount, p.id)
        user = await session.get(User, p.user_id)
        if user:
            await referrals.reward_for_topup(session, user, p.amount, p.id)
        log.info("Payme payment %s PAID: user=%s amount=%s", p.id, p.user_id, p.amount)
        return {"result": {"transaction": str(p.id), "perform_time": _ms(p.paid_at), "state": STATE_PERFORMED}}, p

    if method == "CancelTransaction":
        p = await _payment_by_trans(session, str(params.get("id", "")), lock=True)
        if not p:
            return _err(-31003, "Транзакция не найдена"), None
        if p.status == PaymentStatus.PAID:
            # услуга уже оказана (баланс зачислен) — отмену не принимаем
            return _err(-31007, "Невозможно отменить: платёж уже выполнен"), None
        if p.status != PaymentStatus.CANCELLED:
            p.status = PaymentStatus.CANCELLED
            _set_meta(p, state=STATE_CANCELLED, cancel_time=int(time.time() * 1000), reason=params.get("reason"))
        m = _meta(p)
        return {"result": {"transaction": str(p.id), "cancel_time": int(m.get("cancel_time", 0)), "state": _state(p)}}, None

    if method == "CheckTransaction":
        p = await _payment_by_trans(session, str(params.get("id", "")))
        if not p:
            return _err(-31003, "Транзакция не найдена"), None
        return {"result": _tx_json(p)}, None

    if method == "GetStatement":
        frm, to = int(params.get("from", 0)), int(params.get("to", 0))
        q = select(Payment).where(Payment.provider == "payme", Payment.click_trans_id.is_not(None)).order_by(Payment.id)
        rows = [p for p in (await session.execute(q)).scalars() if frm <= int(_meta(p).get("create_time", 0)) <= to]
        return {
            "result": {
                "transactions": [
                    {"id": p.click_trans_id, "time": int(_meta(p).get("create_time", 0)), "amount": p.amount * 100, "account": {ACCOUNT_FIELD: str(p.id)}, **_tx_json(p)}
                    for p in rows
                ]
            }
        }, None

    return _err(-32601, "Метод не найден"), None
