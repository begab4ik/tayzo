"""Воркер доставки: берёт заказы из очереди и выполняет через провайдера.

Один заказ за раз (у TON-кошелька последовательный seqno). Между ошибочными попытками — пауза.
"""
from __future__ import annotations

import asyncio
import logging

from app.bot import keyboards as kb
from app.bot import texts
from app.bot.notify import notify_admins, notify_user
from app.core import orders as orders_svc
from app.core.enums import OrderStatus
from app.core.money import fmt_uzs
from app.db.base import get_session
from app.providers.registry import is_manual_mode

log = logging.getLogger(__name__)

POLL_INTERVAL = 3
RETRY_DELAY = 20


async def run_forever(stop: asyncio.Event) -> None:
    if is_manual_mode():
        log.warning("Fulfillment worker: MANUAL mode — заказы выполняются админом вручную")
        return
    log.info("Fulfillment worker started")
    while not stop.is_set():
        try:
            processed = await _tick()
        except Exception:  # noqa: BLE001
            log.exception("fulfillment tick failed")
            processed = False
        try:
            await asyncio.wait_for(stop.wait(), timeout=0.5 if processed else POLL_INTERVAL)
        except asyncio.TimeoutError:
            pass


async def _tick() -> bool:
    async with get_session() as session:
        order = await orders_svc.claim_next(session)
        if not order:
            return False
        await session.commit()  # фиксируем PROCESSING, чтобы другой воркер не взял

    async with get_session() as session:
        order = await session.get(orders_svc.Order, order.id)
        order = await orders_svc.process(session, order)
        await session.commit()

    if order.status == OrderStatus.DELIVERED:
        await notify_user(order.user_id, texts.order_delivered(order))
        log.info("order %s delivered", order.id)
    elif order.status == OrderStatus.MANUAL:
        await notify_admins(
            f"🚨 Заказ <b>#{order.id}</b> ({order.title} → @{order.recipient_username}, {fmt_uzs(order.price)}) "
            f"не выполнился автоматически.\nОшибка: <code>{(order.last_error or '')[:300]}</code>",
            reply_markup=kb.order_admin_kb(order.id),
        )
    elif order.status == OrderStatus.FAILED:
        await asyncio.sleep(RETRY_DELAY)
    return True
