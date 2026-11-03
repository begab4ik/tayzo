"""Общее для платёжных провайдеров: создать платёж по имени метода и дать ссылку на оплату."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Payment
from app.payments import click, payme

TITLES = {"click": "Click", "payme": "Payme"}


def available() -> list[str]:
    return settings.payment_methods


async def create(session: AsyncSession, user_id: int, amount: int, method: str) -> Payment:
    if method == "payme":
        return await payme.create_payment(session, user_id, amount)
    return await click.create_payment(session, user_id, amount)


def pay_url(payment: Payment, return_url: str, lang: str = "ru") -> str:
    if payment.provider == "payme":
        return payme.pay_url(payment, return_url=return_url, lang=lang)
    return click.pay_url(payment, return_url=return_url)
