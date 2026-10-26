"""Жизненный цикл заказа.

create()  — списали деньги с баланса, заказ PENDING
process() — воркер: PROCESSING -> DELIVERED | FAILED (ретрай) | MANUAL (после N ошибок / auth-ошибки)
refund()  — вернуть деньги (из MANUAL/FAILED), статус REFUNDED
mark_done_manually() — админ выполнил руками
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import wallet
from app.core.enums import OrderStatus, ProductType
from app.core.exceptions import InsufficientBalance, ProviderAuthError, ProviderError
from app.core.pricing import Quote
from app.db.models import Order, User
from app.providers.base import Recipient
from app.providers.registry import get_provider, is_manual_mode

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3


async def create(session: AsyncSession, user: User, quote: Quote, recipient: Recipient) -> Order:
    # Сначала лочим пользователя — это сериализует параллельные покупки одного юзера и исключает deadlock
    user = await wallet.lock_user(session, user.id)
    if user.balance < quote.price_uzs:
        raise InsufficientBalance(need=quote.price_uzs, have=user.balance)
    order = Order(
        user_id=user.id,
        product=quote.product,
        recipient_username=recipient.username,
        recipient_name=recipient.name,
        recipient_token=recipient.token or None,
        quantity=quote.quantity,
        price=quote.price_uzs,
        cost_ton=quote.cost_ton,
        cost_uzs=quote.cost_uzs,
        status=OrderStatus.MANUAL if is_manual_mode() else OrderStatus.PENDING,
    )
    session.add(order)
    await session.flush()
    await wallet.charge(session, user.id, quote.price_uzs, order.id)
    if quote.product == ProductType.STARS:
        user.total_stars += quote.quantity
    log.info("order %s created: user=%s %s x%s price=%s", order.id, user.id, order.product, order.quantity, order.price)
    return order


async def claim_next(session: AsyncSession) -> Order | None:
    """Взять следующий PENDING/FAILED заказ в работу (с блокировкой строки, чтобы два воркера не взяли один)."""
    q = (
        select(Order)
        .where(Order.status.in_([OrderStatus.PENDING, OrderStatus.FAILED]))
        .order_by(Order.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    order = (await session.execute(q)).scalar_one_or_none()
    if order:
        order.status = OrderStatus.PROCESSING
        order.attempts += 1
        await session.flush()
    return order


async def process(session: AsyncSession, order: Order) -> Order:
    """Выполнить заказ через провайдера. Вызывается воркером после claim_next()."""
    provider = get_provider(ProductType(order.product))
    recipient = Recipient(username=order.recipient_username, name=order.recipient_name or "", token=order.recipient_token or "")
    try:
        if not recipient.token:
            recipient = await provider.resolve_recipient(recipient.username, order.quantity)
            order.recipient_token = recipient.token
            order.recipient_name = recipient.name
        result = await provider.fulfill(recipient, order.quantity)
    except ProviderAuthError as e:
        order.status = OrderStatus.MANUAL
        order.last_error = str(e)
        log.error("order %s -> MANUAL (auth): %s", order.id, e)
        return order
    except ProviderError as e:
        order.last_error = str(e)
        order.status = OrderStatus.MANUAL if order.attempts >= MAX_ATTEMPTS else OrderStatus.FAILED
        log.warning("order %s attempt %s failed: %s", order.id, order.attempts, e)
        return order
    except Exception as e:  # noqa: BLE001 — любая неожиданная ошибка не должна убить воркер
        order.last_error = f"{type(e).__name__}: {e}"
        order.status = OrderStatus.MANUAL if order.attempts >= MAX_ATTEMPTS else OrderStatus.FAILED
        log.exception("order %s unexpected error", order.id)
        return order

    order.status = OrderStatus.DELIVERED
    order.delivered_at = datetime.now(timezone.utc)
    order.fragment_req_id = result.external_id
    if result.cost_ton is not None:
        order.cost_ton = result.cost_ton
    return order


async def refund(session: AsyncSession, order: Order, comment: str | None = None) -> Order:
    if order.status == OrderStatus.REFUNDED:
        return order
    await wallet.refund(session, order.user_id, order.price, order.id, comment=comment)
    if order.product == ProductType.STARS:
        await session.execute(update(User).where(User.id == order.user_id).values(total_stars=User.total_stars - order.quantity))
    order.status = OrderStatus.REFUNDED
    return order


async def mark_done_manually(session: AsyncSession, order: Order, admin_id: int) -> Order:
    order.status = OrderStatus.DELIVERED
    order.delivered_at = datetime.now(timezone.utc)
    order.last_error = f"выполнено вручную админом {admin_id}"
    return order


async def user_orders(session: AsyncSession, user_id: int, limit: int = 10) -> list[Order]:
    q = select(Order).where(Order.user_id == user_id).order_by(Order.id.desc()).limit(limit)
    return list((await session.execute(q)).scalars())


async def manual_queue(session: AsyncSession, limit: int = 20) -> list[Order]:
    q = select(Order).where(Order.status.in_([OrderStatus.MANUAL, OrderStatus.FAILED])).order_by(Order.created_at).limit(limit)
    return list((await session.execute(q)).scalars())
